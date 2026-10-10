"""The onset: when did the failures begin, and between which commits?

Every run of the agent carries the commit it ran on. Ordinary traffic therefore already says
a good deal about the culprit before any replay is spent: this module reads those runs from
neatroots, and uses the same change-point model as the lineup to find where the failures start.
"""

import json
from dataclasses import asdict, dataclass, field

from .lineup import ChangePoint
from .neat import Mcp


@dataclass
class Onset:
    workflow: str
    commits: list[dict]  # in order of first appearance: {"sha", "first_seen_ms", "runs", "bad"}
    good: str | None = None  # last commit that is very unlikely to be at or after the change
    bad: str | None = None  # newest commit seen
    likeliest: str | None = None  # the single most likely first bad commit, from traffic alone
    probability: float = 0.0
    first_failure_ms: float | None = None  # first bad run at or after the likeliest commit
    bad_runs: int = 0
    runs: int = 0
    failing_inputs: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def traffic(mcp: Mcp, workflow: str, limit: int = 5000) -> list[dict]:
    """The workflow's ordinary runs, oldest first, each with its commit. Whodunit's own replays are left out."""
    safe = workflow.replace("'", "''")
    rows = mcp.call("query_sql", sql=(
        "select r.trace_id, r.started_ms, r.input_preview, s.output_preview as info, "
        "(r.status = 'error' or r.error_count > 0 or r.finding_count > 0) as bad "
        "from runs r join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where r.workflow = '{safe}' and r.doctor = 0 and s.attributes not like '%case:%' order by r.started_ms limit {int(limit)}"
    ))["rows"]
    out = []
    for row in rows:
        try:
            tags = json.loads(row.pop("info") or "{}").get("tags", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        commit = next((t.split(":", 1)[1] for t in tags if t.startswith("commit:")), None)
        if commit and commit != "unknown":
            out.append({**row, "commit": commit, "bad": bool(row["bad"])})
    return out


def find_onset(workflow: str, runs: list[dict], floor: float = 0.01) -> Onset:
    """Where the failures begin, given runs as {"commit", "started_ms", "bad", "input_preview"}, oldest first.

    Commits are ordered by when they were first seen. The oldest commit is taken as the baseline.
    The good ref is the last commit before the change point's posterior reaches `floor`, so the
    range handed to the lineup is wide enough to hold the culprit.
    """
    order: dict[str, dict] = {}
    for run in runs:
        seen = order.setdefault(run["commit"], {"sha": run["commit"], "first_seen_ms": run["started_ms"], "runs": 0, "bad": 0})
        seen["runs"] += 1
        seen["bad"] += run["bad"]
    commits = list(order.values())
    onset = Onset(workflow=workflow, commits=commits, runs=len(runs), bad_runs=sum(r["bad"] for r in runs))
    if len(commits) < 2:
        onset.note = "Runs from at least two commits are needed to place the onset."
        return onset
    if onset.bad_runs == 0:
        onset.note = "No bad runs in the traffic."
        return onset
    state = ChangePoint(len(commits) - 1)  # the oldest commit plays the good ref
    for position, commit in enumerate(commits):
        for _ in range(commit["bad"]):
            state.observe(position - 1, True)
        for _ in range(commit["runs"] - commit["bad"]):
            state.observe(position - 1, False)
    posterior = state.posterior()
    top = max(range(len(posterior)), key=posterior.__getitem__)
    mass, start = 0.0, 0
    for i, share in enumerate(posterior):
        mass += share
        if mass >= floor:
            start = i
            break
    onset.good = commits[start]["sha"]  # suspect i is commits[i + 1], so the commit before suspect `start` is commits[start]
    onset.bad = commits[-1]["sha"]
    onset.likeliest, onset.probability = commits[top + 1]["sha"], round(posterior[top], 4)
    since = commits[top + 1]["first_seen_ms"]
    later_bad = [r for r in runs if r["bad"] and r["started_ms"] >= since]
    onset.first_failure_ms = later_bad[0]["started_ms"] if later_bad else None
    inputs: dict[str, int] = {}
    for run in later_bad:
        if run.get("input_preview"):
            inputs[run["input_preview"]] = inputs.get(run["input_preview"], 0) + 1
    onset.failing_inputs = sorted(inputs, key=lambda text: -inputs[text])[:5]
    return onset


def cloud_trend(detection: str = "Execution Failed") -> dict:
    """Ask neatlogs cloud when a detection started firing. Needs NEATLOGS_API_KEY in .env.

    Returns {"detection", "first_seen", "total", "points"}, where first_seen is the start of the
    first bucket with any occurrences, or None if the detection has not fired in the period.
    """
    import os

    from .env import load_env
    from .neat import NEATLOGS

    load_env()
    key = os.environ.get("NEATLOGS_API_KEY", "")
    if not key:
        raise RuntimeError("NEATLOGS_API_KEY is not in .env")
    trend = Mcp(NEATLOGS, token=key).call("get_detection_trend", detection_name=detection)
    points = trend.get("data_points", [])
    first = next((p["date"] for p in points if p.get("count", 0) > 0), None)
    return {"detection": trend.get("detection_name", detection), "first_seen": first, "total": trend.get("total_occurrences", 0), "points": points}


def witness(mcp: Mcp, workflow: str, positions: dict[str, int], inputs: list[tuple[str, list[dict]]]) -> list[tuple[int, bool]]:
    """What ordinary traffic already says about a case, as (position, failed) pairs for the lineup.

    `positions` maps a commit to its place in the lineup (-1 for the good ref). A run counts when
    it asked exactly what one of the case's inputs asks, and it failed if what it refunded is not
    what the case expects. These runs were already paid for, so they cost the lineup nothing.
    """
    expected = {text: {str(r["order_id"]): float(r["refunded"]) for r in refunds} for text, refunds in inputs}
    safe = workflow.replace("'", "''")
    asked = ", ".join("'" + text.replace("'", "''") + "'" for text in expected) or "''"
    rows = mcp.call("query_sql", sql=(
        "select r.trace_id, r.input_preview, s.output_preview as info from runs r "
        "join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where r.workflow = '{safe}' and r.doctor = 0 and r.input_preview in ({asked}) and s.attributes not like '%case:%' "
        "order by r.started_ms desc limit 200"
    ))["rows"]
    runs = []
    for row in rows:
        try:
            tags = json.loads(row["info"] or "{}").get("tags", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        commit = next((t.split(":", 1)[1] for t in tags if t.startswith("commit:")), None)
        if commit in positions:
            runs.append((row["trace_id"], row["input_preview"], positions[commit]))
    if not runs:
        return []
    ids = ", ".join("'" + trace + "'" for trace, _, _ in runs)
    paid: dict[str, dict[str, float]] = {trace: {} for trace, _, _ in runs}
    for span in mcp.call("query_sql", sql=f"select trace_id, output_preview from spans where name = 'issue_refund' and status_code != 2 and trace_id in ({ids}) limit 200")["rows"]:
        try:
            out = json.loads(span["output_preview"] or "{}")
            order, amount = str(out["order_id"]), float(out["refunded"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        paid[span["trace_id"]][order] = paid[span["trace_id"]].get(order, 0.0) + amount
    evidence = []
    for trace, text, position in runs:
        want, got = expected[text], paid[trace]
        wrong = any(abs(got.get(o, 0.0) - want.get(o, 0.0)) > 0.005 for o in set(got) | set(want))
        evidence.append((position, wrong))
    return evidence

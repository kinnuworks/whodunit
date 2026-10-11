"""The onset: when did the failures begin, and between which commits?

Every run of the agent carries the commit it ran on. Ordinary traffic therefore already says
a good deal about the culprit before any replay is spent: this module reads those runs from
neatroots, and uses the same change-point model as the lineup to find where the failures start.
"""

import json
from dataclasses import asdict, dataclass, field

from .lineup import ChangePoint
from .neat import Mcp, select_all


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
    rows = select_all(mcp, (
        "select r.trace_id, r.started_ms, r.input_preview, s.output_preview as info, "
        "(r.status = 'error' or r.error_count > 0 or r.finding_count > 0) as bad "
        "from runs r join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where r.workflow = '{safe}' and r.doctor = 0 and s.attributes not like '%case:%' order by r.started_ms"
    ), cap=limit)
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
    rows = select_all(mcp, (
        "select r.trace_id, r.input_preview, s.output_preview as info from runs r "
        "join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where r.workflow = '{safe}' and r.doctor = 0 and r.input_preview in ({asked}) and s.attributes not like '%case:%' "
        "order by r.started_ms desc"
    ), cap=1000)
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
    for span in select_all(mcp, f"select trace_id, output_preview from spans where name = 'issue_refund' and status_code != 2 and trace_id in ({ids})"):
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


def environment_then(mcp: Mcp, workflow: str, good: str, inputs: list[tuple[str, list[dict]]]) -> list[dict]:
    """What old passing runs at the good ref ran with: [{"model", "lock", "version"}], one per run.

    These are ordinary runs of the case's inputs, on the good ref, that paid what the case
    expects. `model` is a fingerprint of the id in the run's run_info and not the id, because a
    case record names no model. `lock` is there only if the agent recorded a lockfile hash.
    """
    import hashlib

    expected = {text: {str(r["order_id"]): float(r["refunded"]) for r in refunds} for text, refunds in inputs}
    safe = workflow.replace("'", "''")
    asked = ", ".join("'" + text.replace("'", "''") + "'" for text in expected) or "''"
    rows = select_all(mcp, (
        "select r.trace_id, r.input_preview, s.output_preview as info from runs r "
        "join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where r.workflow = '{safe}' and r.doctor = 0 and r.input_preview in ({asked}) and s.attributes not like '%case:%' "
        f"and s.attributes like '%commit:{''.join(c for c in good if c.isalnum())}%'"
    ), cap=500)
    if not rows:
        return []
    ids = ", ".join("'" + row["trace_id"] + "'" for row in rows)
    paid: dict[str, dict[str, float]] = {row["trace_id"]: {} for row in rows}
    for span in select_all(mcp, f"select trace_id, output_preview from spans where name = 'issue_refund' and status_code != 2 and trace_id in ({ids})"):
        try:
            out = json.loads(span["output_preview"] or "{}")
            order, amount = str(out["order_id"]), float(out["refunded"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        paid[span["trace_id"]][order] = paid[span["trace_id"]].get(order, 0.0) + amount
    then = []
    for row in rows:
        want, got = expected[row["input_preview"]], paid[row["trace_id"]]
        if any(abs(got.get(o, 0.0) - want.get(o, 0.0)) > 0.005 for o in set(got) | set(want)):
            continue  # this old run did not pass, so it says nothing about a healthy environment
        try:
            info = json.loads(row["info"] or "{}")
        except json.JSONDecodeError:
            info = {}
        model = str(info.get("model") or "")
        then.append({"model": hashlib.sha256(model.encode()).hexdigest()[:8] if model else "", "lock": str(info.get("lock") or "")[:12], "version": str(info.get("version") or "")})
    return then


def what_differs(then: list[dict], now: list[dict]) -> list[str]:
    """Sentences on how today's replays of the good ref differ from old runs of it that passed.

    `then` and `now` are [{"model", "lock"}]. Model ids appear as fingerprints only.
    """
    if not then:
        return ["No ordinary run of these requests that passed on the good ref is on record, so today's environment has nothing to be compared with."]
    out = []
    for key, name, what in (("model", "model id", "a model id"), ("lock", "lockfile", "a lockfile hash")):
        before, today = sorted({run[key] for run in then if run.get(key)}), sorted({run[key] for run in now if run.get(key)})
        if not before:
            out.append(f"The old passing runs did not record {what}" + (f", so it cannot be compared. Today's replays ran with {name} {', '.join(today)}." if today else "."))
        elif not today:
            out.append(f"Today's replays did not report {what}, so it cannot be compared.")
        elif before == today:
            out.append(f"The {name} is the same as in the old passing runs.")
        else:
            out.append(f"The {name} differs. The old passing runs had {', '.join(before)} and today's replays have {', '.join(today)}."
                       + (" Those are fingerprints of the ids, which are in the traces. A case file names no model." if key == "model" else ""))
    return out

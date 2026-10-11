"""Opening a case from one failing trace.

Someone hands over a trace id and says "this run was wrong". That is enough to write most of a
case file. The input is in the run's root span. The commit it ran on is in its run_info tags,
and that is the bad ref. What the run should have produced is taken from the nearest earlier run
of the same input that passed, and where the trouble began is found from every run of that input
with the change-point model in `whodunit/onset.py`. If no earlier run passed, the owner is asked
what the request should have produced. That is the one question.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .neat import Mcp, NeatError, select_all
from .onset import find_onset
from .suspects import git


@dataclass
class FailingRun:
    trace_id: str
    source: str  # neatroots or neatlogs cloud
    workflow: str
    request: str  # the input from the root span
    commit: str  # from the run_info tags
    paid: dict[str, float] = field(default_factory=dict)  # what it refunded, order id to amount


def _request(root_input: str) -> str:
    """The request inside a root span's input. An agent usually wraps it: {"request": "...", "max_steps": 3}."""
    try:
        given = json.loads(root_input)
    except (json.JSONDecodeError, TypeError):
        return (root_input or "").strip()
    if isinstance(given, dict):
        for key in ("request", "input", "query", "question", "prompt", "text", "message"):
            if isinstance(given.get(key), str):
                return given[key]
    return given if isinstance(given, str) else (root_input or "").strip()


def _commit(run_info: str) -> str:
    found = re.search(r"commit:([0-9a-f]{7,40})", run_info or "")
    return found.group(1) if found else ""


def _refunds(outputs: list[str]) -> dict[str, float]:
    """What a run paid, from the outputs of its issue_refund spans."""
    paid: dict[str, float] = {}
    for text in outputs:
        try:
            out = json.loads(text or "{}")
            order, amount = str(out["order_id"]), float(out["refunded"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        paid[order] = paid.get(order, 0.0) + amount
    return paid


def read_failing_run(trace_id: str, local: Mcp | None, cloud: Mcp | None) -> FailingRun:
    """Find the run in neatroots, or failing that in neatlogs cloud. Raises LookupError if neither has it."""
    safe = "".join(c for c in trace_id.lower() if c in "0123456789abcdef")
    problems = []
    if local is not None and safe:
        try:
            rows = local.call("query_sql", sql=(
                "select r.trace_id, r.workflow, r.input_preview, s.name, s.parent_span_id, s.input_preview as given, s.output_preview as said "
                f"from runs r join spans s on s.trace_id = r.trace_id where r.trace_id like '{safe}%' and (s.parent_span_id is null or s.name in ('run_info', 'issue_refund'))"
            ))["rows"]
        except (NeatError, KeyError, TypeError) as exc:
            rows, _ = [], problems.append(f"neatroots could not be asked: {exc}")
        if len({row["trace_id"] for row in rows}) > 1:
            raise LookupError(f"{trace_id} is the start of more than one trace id in neatroots. Give more of it.")
        if rows:
            root = next((row for row in rows if row["parent_span_id"] is None), None)
            info = next((row["said"] for row in rows if row["name"] == "run_info"), "")
            return FailingRun(
                trace_id=rows[0]["trace_id"], source="neatroots", workflow=rows[0]["workflow"],
                request=_request(root["given"]) if root and root["given"] else rows[0]["input_preview"] or "",
                commit=_commit(info), paid=_refunds([row["said"] for row in rows if row["name"] == "issue_refund"]),
            )
    if cloud is not None:
        try:
            trace = cloud.call("get_trace_context", trace_id=trace_id)
        except NeatError as exc:
            trace, _ = None, problems.append(f"neatlogs cloud could not be asked: {exc}")
        if isinstance(trace, dict) and trace.get("spans"):
            spans = trace["spans"]
            root = next((s for s in spans if s.get("is_root") or not s.get("parent_span_id")), spans[0])
            info = next((s.get("output_value", "") for s in spans if s.get("name") == "run_info"), "")
            return FailingRun(
                trace_id=trace.get("trace_id", trace_id), source="neatlogs cloud", workflow=trace.get("workflow", ""),
                request=_request(root.get("input_value", "")), commit=_commit(info),
                paid=_refunds([s.get("output_value", "") for s in spans if s.get("name") == "issue_refund"]),
            )
    raise LookupError(f"No run {trace_id} in neatroots" + ("" if cloud is None else " or in neatlogs cloud") + ("." if not problems else ". " + " ".join(problems)))


def history(mcp: Mcp, repo: str | Path, run: FailingRun) -> list[dict]:
    """Earlier ordinary runs of the same request, oldest commit first: {"trace_id", "commit", "paid", "flagged"}.

    Only runs on commits the bad ref descends from are kept, in the order git puts those commits.
    Whodunit's own replays are left out. `flagged` means the run errored or neatroots raised a
    finding on it.
    """
    safe_workflow, safe_request = run.workflow.replace("'", "''"), run.request.replace("'", "''")
    rows = select_all(mcp, (
        "select r.trace_id, s.output_preview as info, (r.status = 'error' or r.error_count > 0 or r.finding_count > 0) as flagged "
        "from runs r join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where r.workflow = '{safe_workflow}' and r.doctor = 0 and r.input_preview = '{safe_request}' and s.attributes not like '%case:%' and r.trace_id != '{run.trace_id}'"
    ), cap=2000)
    if not rows:
        return []
    order = {sha: n for n, sha in enumerate(git(repo, "rev-list", "--reverse", f"{run.commit}^").split())}
    kept = [{"trace_id": row["trace_id"], "commit": _commit(row["info"]), "flagged": bool(row["flagged"])} for row in rows]
    kept = [row for row in kept if row["commit"] in order]
    ids = ", ".join("'" + row["trace_id"] + "'" for row in kept) or "''"
    outputs: dict[str, list[str]] = {row["trace_id"]: [] for row in kept}
    for span in select_all(mcp, f"select trace_id, output_preview from spans where name = 'issue_refund' and status_code != 2 and trace_id in ({ids})"):
        outputs[span["trace_id"]].append(span["output_preview"])
    for row in kept:
        row["paid"] = _refunds(outputs[row["trace_id"]])
    return sorted(kept, key=lambda row: order[row["commit"]])


@dataclass
class Draft:
    """What could be worked out about a case from one failing run and the runs before it."""

    request: str
    bad: str
    expected: list[dict] | None = None  # what the request should have produced, or None if nobody knows yet
    expected_from: dict | None = None  # the earlier run it was taken from
    good: str | None = None
    notes: list[str] = field(default_factory=list)


def draft(run: FailingRun, earlier: list[dict]) -> Draft:
    """Work out the expected result and the last good ref from the runs before the failing one."""
    made = Draft(request=run.request, bad=run.commit)
    passed = [row for row in earlier if not row["flagged"] and row["paid"] != run.paid]
    if not passed:
        made.notes.append(f"{len(earlier)} earlier runs of this request are on record, and none of them both passed and paid something different from the failing run."
                          if earlier else "No earlier run of this request is on record.")
        return made
    source = passed[-1]  # the nearest one before the bad ref
    made.expected = [{"order_id": order, "refunded": amount} for order, amount in sorted(source["paid"].items())]
    made.expected_from = {"trace_id": source["trace_id"], "commit": source["commit"]}
    # Every run of the request, judged against that expectation, with the failing run last.
    judged = [{"commit": row["commit"], "started_ms": n, "bad": row["paid"] != source["paid"], "input_preview": run.request} for n, row in enumerate(earlier)]
    judged.append({"commit": run.commit, "started_ms": len(judged), "bad": True, "input_preview": run.request})
    onset = find_onset(run.workflow, judged)
    if onset.good:
        made.good = onset.good
        made.notes.append(f"{len(judged)} runs of this request across {len(onset.commits)} commits put the start of the trouble most likely at {onset.likeliest[:12]} ({onset.probability:.0%}).")
    else:
        made.good = source["commit"]
        made.notes.append(f"Too few runs of this request to place the start of the trouble ({onset.note}), so the last good ref is the commit of the run that passed.")
    return made


def case_toml(case_id: str, symptom: str, made: Draft, like: dict, comment: str) -> str:
    """The case file as text. `like` is another case's settings for running the same agent."""
    def value(v) -> str:
        return json.dumps(v)  # TOML and JSON agree on strings, numbers and lists of them

    lines = [f"# {line}" for line in comment.splitlines()] + [
        f"id = {value(case_id)}", f"symptom = {value(symptom)}", f"good = {value(made.good)}", f"bad = {value(made.bad)}",
    ]
    for key in ("target", "traffic_sent_by", "void_exit_codes", "void_stderr", "build", "run", "timeout"):
        if like.get(key) not in (None, "", [], ()):
            lines.append(f"{key} = {value(like[key])}")
    if like.get("check"):
        lines += ["", "[check]"] + [f"{key} = {value(v)}" for key, v in like["check"].items()]
    if like.get("env"):
        lines += ["", "[env]"] + [f"{key} = {value(v)}" for key, v in like["env"].items()]
    refunds = ", ".join("{ " + ", ".join(f"{key} = {value(v)}" for key, v in refund.items()) + " }" for refund in made.expected or [])
    lines += ["", "[[inputs]]", f"text = {value(made.request)}", f"refunds = [{refunds}]"]
    return "\n".join(lines) + "\n"

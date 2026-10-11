"""The root-cause brief.

It is written from three things: the culprit's diff, the part of the coding session that
produced it, and a failing run set against a passing one. Every sentence has to cite a span id,
a commit or a checkpoint that is actually in that evidence, and a sentence that does not is cut.

A second rule check sets the brief against what the lineup measured. A brief that says the bug
fails always, every time or deterministically, when the measured rate is under 95%, is rejected
and asked for again with the rates in view. So is one that gives a count of runs or replays
that the measurements do not.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import llm
from .motive import Motive
from .neat import Mcp, NeatError, replay_runs
from .suspects import git

MAX_DIFF = 6000
ALWAYS_NEEDS = 0.95  # a brief may say "always" only when the measured failure rate is at least this


@dataclass
class Evidence:
    culprit: str
    parent: str
    subject: str
    diff: str
    after: str = ""  # the changed code as it reads after the commit, with line numbers
    checkpoint: str | None = None
    request: str | None = None
    message: str = ""  # the body of the culprit's commit message
    steps: list[dict] = field(default_factory=list)
    failing_run: dict | None = None  # {"trace_id", "commit", "input", "outline"}
    passing_run: dict | None = None
    comparison: str | None = None
    measured: str = ""  # what the lineup measured, in words
    rate_from: float | None = None  # the failure rate from the culprit on, as the case file prints it
    notes: list[str] = field(default_factory=list)

    def citable(self) -> set[str]:
        """Every id a sentence may cite."""
        ids = {self.culprit[:12], self.parent[:12]}
        if self.checkpoint:
            ids.add(self.checkpoint)
        ids.update(step["id"] for step in self.steps if step.get("id"))
        for run in (self.failing_run, self.passing_run):
            if run:
                ids.add(run["trace_id"][:12])
                ids.update(re.findall(r"^\s*([0-9a-f]{8}) [A-Z_]+ ", run.get("outline", ""), flags=re.M))
        return ids


def _match_run(runs: list[dict], replay: dict, replays: list[dict] = ()) -> dict | None:
    """The neatroots run a replay produced, by the replay's own tag when it has one.

    Older records have no tags, and for those: same commit, same input, started while the replay
    ran. Replays that ran side by side on one commit and one input cannot be told apart by time. If
    they all ended the same way it does not matter which is which, and the closest one is taken.
    """
    if replay.get("tag"):
        return next((r for r in runs if r.get("case") == replay["tag"]), None)
    start, end = replay["started"] * 1000 - 1500, (replay["started"] + replay["seconds"]) * 1000 + 1500
    hits = [r for r in runs if r["commit"] == replay["sha"] and r["input_preview"] == replay["input"] and start <= r["started_ms"] <= end]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None
    beside = [
        r for r in replays
        if r["sha"] == replay["sha"] and r["input"] == replay["input"]
        and r["started"] < replay["started"] + replay["seconds"] and replay["started"] < r["started"] + r["seconds"]
    ]
    if all(r["verdict"] == replay["verdict"] for r in beside):
        return min(hits, key=lambda r: abs(r["started_ms"] - replay["started"] * 1000))
    return None


def gather(repo: str | Path, case_id: str, culprit: str, target: str, replays: list[dict], motive: Motive | None, mcp: Mcp | None, order: list[str] | None = None) -> Evidence:
    """Collect what the brief may draw on. `replays` are the lineup's replays, as dicts.

    `order` is the suspects' SHAs oldest first. A failing run is taken from the culprit or the
    nearest commit after it, and a passing run from the nearest commit before it, same input.
    """
    full = git(repo, "rev-parse", culprit).strip()
    parent = git(repo, "rev-parse", f"{full}^").strip()
    subject = git(repo, "show", "-s", "--format=%s", full).strip()
    diff = git(repo, "show", "--format=", "--unified=3", full, "--", target)
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n[diff cut here]\n"
    evidence = Evidence(culprit=full, parent=parent, subject=subject, diff=diff, after=code_after(repo, full, target))
    if motive:
        evidence.checkpoint, evidence.request, evidence.message = motive.checkpoint, motive.request, motive.message
        evidence.steps = [asdict(s) for s in motive.steps]
    if mcp is None:
        evidence.notes.append("neatroots was not asked for runs.")
        return evidence
    try:
        runs = replay_runs(mcp, case_id)
        order = order or [full]
        at = order.index(full) if full in order else 0
        rank = {sha: n for n, sha in enumerate(order)}
        rank.setdefault(parent, -1)
        failing = sorted((r for r in replays if r["verdict"] == "fail" and rank.get(r["sha"], -9) >= at), key=lambda r: rank[r["sha"]])
        for replay in failing:
            run = _match_run(runs, replay, replays)
            if run is None:
                continue
            passing = sorted(
                (r for r in replays if r["verdict"] == "pass" and r["input"] == replay["input"] and -1 <= rank.get(r["sha"], -9) < at),
                key=lambda r: -rank[r["sha"]],
            )
            other = next((m for m in (_match_run(runs, r, replays) for r in passing) if m), None)
            evidence.failing_run = {"trace_id": run["trace_id"], "commit": run["commit"], "input": replay["input"], "reason": replay["reason"],
                                    "outline": mcp.call("get_run_outline", trace_id=run["trace_id"])["outline"]}
            if other:
                evidence.passing_run = {"trace_id": other["trace_id"], "commit": other["commit"], "input": replay["input"],
                                        "outline": mcp.call("get_run_outline", trace_id=other["trace_id"])["outline"]}
                compared = mcp.call("compare_runs", a=other["trace_id"], b=run["trace_id"])
                evidence.comparison = compared if isinstance(compared, str) else json.dumps(compared, indent=1)[:3000]
            break
        if evidence.failing_run is None:
            evidence.notes.append("No failing replay could be matched to a run in neatroots.")
        elif evidence.passing_run is None:
            evidence.notes.append("No passing replay of the same input before the culprit could be matched to a run in neatroots.")
    except (NeatError, KeyError, TypeError) as exc:
        evidence.notes.append(f"neatroots could not supply runs: {exc}")
    return evidence


def code_after(repo: str | Path, sha: str, target: str, around: int = 10, limit: int = 4000) -> str:
    """The lines each hunk touched, as they read after the commit, numbered and with their indentation intact.

    A diff's leading + and - columns make indentation easy to misread, and indentation is often the bug.
    """
    out = []
    names = [f for f in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha, "--", target).split("\n") if f]
    for name in names:
        try:
            lines = git(repo, "show", f"{sha}:{name}").split("\n")
        except RuntimeError:
            continue  # the commit deleted this file
        for start, count in re.findall(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", git(repo, "show", "--format=", "--unified=0", sha, "--", name), flags=re.M):
            first = max(1, int(start) - around)
            last = min(len(lines), int(start) + int(count or 1) + around)
            out.append(f"{name}, lines {first} to {last} after the commit:\n" + "\n".join(f"{n:>4}  {lines[n - 1]}" for n in range(first, last + 1)))
    return "\n\n".join(out)[:limit]


SYSTEM = """You write the root-cause brief for a regression in an AI agent. You are given the commit that a bisect \
named as the culprit, what the coding agent was asked to do in that commit, and a failing run next to a passing run.

Rules:
- Say which commit did it and why first. Then say how the failure shows up in the failing run.
- Use only what the evidence shows. If the evidence does not show something, do not say it.
- Read the diff line by line before describing it, including its indentation. If the bug fails only some of the time, say what in the code or the run makes it intermittent, or say that the evidence does not show why.
- Every sentence must cite at least one id from the list of citable ids: a span id, a commit, a checkpoint or a session step.
- How often it fails is in "What the bisect measured". Do not say it fails always, every time or deterministically unless that rate is 95% or more. Give the measured rate, and say what in the evidence makes some runs come out right, or that the evidence does not show it. Use only the counts of runs and replays given there, and do not add them up into new ones.
- If the request behind the commit is on record, give one sentence that sets what was asked for against what the commit did, and says where the two part ways. Cite the checkpoint.
- Plain words, short sentences, no hype. Seven sentences at most.

Answer with JSON only, in this shape:
{"headline": "one line, under 90 characters", "sentences": [{"text": "...", "cites": ["id", "id"]}]}"""


def prompt_for(evidence: Evidence, symptom: str) -> str:
    parts = [
        f"Symptom: {symptom}",
        f"Culprit commit: {evidence.culprit[:12]} \"{evidence.subject}\" (parent {evidence.parent[:12]})",
        f"What the bisect measured: {evidence.measured or 'not recorded'}",
        f"Entire checkpoint: {evidence.checkpoint or 'none'}",
        f"What the coding agent was asked: {evidence.request or 'not recorded'}",
        f"What the commit message says: {evidence.message or 'nothing beyond the subject'}",
        "Session steps between that request and the commit:\n" + ("\n".join(
            f"[{s['id']}] {s['kind']}{' ' + s['file'] if s.get('file') else ''}: {s['text'][:400]}" for s in evidence.steps[-25:]) or "none recorded"),
        "Diff of the culprit commit:\n" + evidence.diff,
        "The changed code as it reads after the commit:\n" + (evidence.after or "not available"),
    ]
    for label, run in (("Failing run", evidence.failing_run), ("Passing run", evidence.passing_run)):
        if run:
            parts.append(f"{label} {run['trace_id'][:12]} at commit {run['commit'][:12]}, input: {run['input']}\n{run['outline']}")
    if evidence.comparison:
        parts.append("neatroots comparison, passing run first:\n" + evidence.comparison)
    parts.append("Citable ids: " + ", ".join(sorted(evidence.citable())))
    return "\n\n".join(parts)


def check_citations(brief: dict, evidence: Evidence) -> dict:
    """Keep only sentences whose citations are real. A cite matches by prefix in either direction."""
    allowed = evidence.citable()

    def real(cite: str) -> str | None:
        cite = str(cite).strip().strip("[]`")
        if len(cite) < 6:
            return None
        return next((a for a in allowed if a.startswith(cite) or cite.startswith(a)), None)

    kept, dropped = [], []
    for sentence in brief.get("sentences", []):
        cites = sorted({c for c in (real(c) for c in sentence.get("cites", [])) if c})
        (kept if cites and sentence.get("text", "").strip() else dropped).append({"text": sentence.get("text", "").strip(), "cites": cites})
    return {"headline": str(brief.get("headline", "")).strip(), "sentences": kept, "dropped": [d["text"] for d in dropped]}


ABSOLUTE = re.compile(r"(?<![Nn]on)(?<![Nn]on-)\b(always|every (?:single )?(?:time|run)|each time|deterministic(?:ally)?|invariably|without fail|100%)", re.I)
NEGATION = re.compile(r"\b(?:not|never|no|nor|rarely|seldom|hardly)\b|n't\b", re.I)


def absolute_claims(text: str) -> list[str]:
    """The words in a sentence that say something happens every time. "Does not always" is left out."""
    found = []
    for match in ABSOLUTE.finditer(text):
        before = " ".join(text[:match.start()].split()[-3:])
        if not NEGATION.search(before):
            found.append(match.group(1))
    return found


COUNT = re.compile(r"\b(?:(\d+) of (?:the )?)?(\d+)\s+(?:(?:total|ordinary|traffic|matching|other|more|clean|failing|failed|passing|post-culprit)\s+)?(?:runs?|replays?)\b")


def unbacked_claims(brief: dict, rate: float | None, measured: str = "") -> list[dict]:
    """Sentences that contradict what the lineup measured. The headline counts as a sentence.

    Two things are checked. A sentence may say always, every time or deterministic only when the
    measured failure rate is 95% or more. And a count of runs or replays ("26 runs", "4 of 6
    runs") has to be one the measurements give. Returns [{"text", "problem"}].
    """
    numbers = set(re.findall(r"\d+", measured))
    pairs = set(re.findall(r"\d+ of \d+", measured))
    out = []
    for text in [brief.get("headline", "")] + [s["text"] for s in brief.get("sentences", [])]:
        words = absolute_claims(text) if rate is not None and rate < ALWAYS_NEEDS else []
        if words:
            out.append({"text": text, "problem": f'says "{words[0]}", and the measured failure rate from the culprit on is {rate:.0%}'})
            continue
        for part, whole in COUNT.findall(text) if measured else []:
            said = f"{part} of {whole}" if part else whole
            if (said not in pairs) if part else (whole not in numbers):
                out.append({"text": text, "problem": f'gives a count, "{said}", that is not in the measurements'})
                break
    return out


def template_brief(evidence: Evidence, symptom: str) -> dict:
    """A brief with no model: the facts in fixed sentences, each with its citation."""
    culprit = evidence.culprit[:12]
    sentences = [{"text": f"The failures start at commit {culprit}, \"{evidence.subject}\".", "cites": [culprit]}]
    if evidence.request and evidence.checkpoint:
        asked = evidence.request.strip().splitlines()[0][:200]
        sentences.append({"text": f"That commit came from a coding session that was asked: \"{asked}\"", "cites": [evidence.checkpoint]})
    elif evidence.message:
        sentences.append({"text": f"No coding session could be read for that commit. Its own message says: \"{evidence.message.splitlines()[0][:200]}\"", "cites": [culprit]})
    else:
        sentences.append({"text": "No coding session is recorded for that commit, so the request behind it is unknown.", "cites": [culprit]})
    if evidence.failing_run:
        run = evidence.failing_run
        sentences.append({"text": f"In a failing replay of \"{run['input']}\", {run['reason']}.", "cites": [run["trace_id"][:12]]})
    if evidence.passing_run:
        run = evidence.passing_run
        sentences.append({"text": f"The same input passed one step earlier, at commit {run['commit'][:12]}.", "cites": [run["trace_id"][:12], run["commit"][:12]]})
    return {"headline": f"{evidence.subject}: {symptom}"[:90], "sentences": sentences, "dropped": [], "model": "none, fixed template"}


def _draft(evidence: Evidence, symptom: str, objections: list[dict] = ()) -> dict:
    """Ask the model once and check the citations. `objections` are what a rule check said about the draft before."""
    prompt = prompt_for(evidence, symptom)
    if objections:
        prompt += (
            "\n\nYour earlier answer was rejected by a rule check, for these sentences:\n"
            + "\n".join(f'- "{o["text"]}": it {o["problem"]}.' for o in objections)
            + f"\nWhat was measured: {evidence.measured or 'not recorded'}"
            + "\nWrite the whole brief again. Where it says how often the failure happens, give the measured rate, and use only counts that are in the measurements."
        )
    answer = llm.ask(SYSTEM, prompt)
    found = re.search(r"\{.*\}", answer, flags=re.S)
    return check_citations(json.loads(found.group(0)), evidence)


def write_brief(evidence: Evidence, symptom: str) -> dict:
    """Ask the model for the brief and check it. Falls back to the template, and says so.

    A draft that contradicts the measured failure rate is rejected and asked for once more. If
    the second draft still does, the sentences that say so are cut like any other unbacked one.
    """
    if llm.choice() == "none":
        return template_brief(evidence, symptom)
    try:
        brief = _draft(evidence, symptom)
        rejected = unbacked_claims(brief, evidence.rate_from, evidence.measured)
        if rejected:
            cut_before = brief["dropped"]
            brief = _draft(evidence, symptom, rejected)
            brief["dropped"] = cut_before + brief["dropped"]
            still = {o["text"] for o in unbacked_claims(brief, evidence.rate_from, evidence.measured)}
            brief["dropped"] += [s["text"] for s in brief["sentences"] if s["text"] in still]
            brief["sentences"] = [s for s in brief["sentences"] if s["text"] not in still]
            if brief["headline"] in still:
                brief["headline"] = f"{evidence.subject}: {symptom}"[:90]
    except (llm.LlmError, AttributeError, json.JSONDecodeError, KeyError) as exc:
        fallback = template_brief(evidence, symptom)
        fallback["model"] = f"none, fixed template (the model step failed: {exc})"
        return fallback
    if not brief["sentences"]:
        fallback = template_brief(evidence, symptom)
        fallback["model"] = "none, fixed template (the model's sentences had no valid citations)"
        fallback["dropped"] = brief["dropped"]
        return fallback
    brief["model"] = llm.model_name()
    brief["rejected"] = rejected  # what the rule check said about the first draft, if it was sent back
    return brief

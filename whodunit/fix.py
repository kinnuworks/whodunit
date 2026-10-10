"""The fix: apply it on a branch, replay the case until the evidence says it is fixed, and keep the case.

A revert is mechanical. A patch that keeps the culprit's intent is written by a model and
checked the same way. Nothing here pushes or opens a pull request. That stays with the owner.
"""

import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import llm
from .suspects import git


@dataclass
class Verification:
    fixed: bool
    probability: float  # P(the fix commit fails at the good rate and not the bad rate)
    replays: int
    failures: int
    note: str = ""


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def probability_fixed(failures: int, passes: int, good: tuple[int, int], bad: tuple[int, int], prior: float = 0.5) -> float:
    """P(fixed) from replays of the fix commit, against what the lineup saw on each side.

    `good` and `bad` are (failures, passes) from before the culprit and from it onward. Each
    side's failure rate is a Beta posterior, and the question is which side the fix commit's
    replays look like. This is the same closed form the lineup uses.
    """
    def evidence(side: tuple[int, int], a: float, b: float) -> float:
        a, b = a + side[0], b + side[1]
        return _log_beta(a + failures, b + passes) - _log_beta(a, b)

    log_good = evidence(good, 0.5, 9.5) + math.log(prior)
    log_bad = evidence(bad, 1.0, 1.0) + math.log(1 - prior)
    top = max(log_good, log_bad)
    return math.exp(log_good - top) / (math.exp(log_good - top) + math.exp(log_bad - top))


def verify(trial, good: tuple[int, int], bad: tuple[int, int], budget: int = 60, confidence: float = 0.95, parallel: int = 1) -> Verification:
    """Replay the fix commit until it is 95% likely fixed, 95% likely not, or the budget is spent."""
    from concurrent.futures import ThreadPoolExecutor

    failures = passes = 0
    probability = 0.5
    while failures + passes < budget:
        batch = min(max(1, parallel), budget - failures - passes)
        if batch > 1:
            with ThreadPoolExecutor(max_workers=batch) as pool:
                verdicts = list(pool.map(lambda _: trial(), range(batch)))
        else:
            verdicts = [trial()]
        if "skip" in verdicts:
            return Verification(False, 0.0, failures + passes, failures, "the fix commit will not build")
        failures += verdicts.count("fail")
        passes += verdicts.count("pass")
        probability = probability_fixed(failures, passes, good, bad)
        if probability >= confidence or probability <= 1 - confidence:
            break
    note = "" if probability >= confidence or probability <= 1 - confidence else "the replay budget ran out before the answer was clear"
    return Verification(probability >= confidence, probability, failures + passes, failures, note)


@dataclass
class Fix:
    branch: str
    kind: str  # revert or patch
    commit: str | None = None
    note: str = ""
    files: list[str] = field(default_factory=list)


def _commit(worktree: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True, capture_output=True)
    done = subprocess.run(["git", "-C", str(worktree), "commit", "-q", "-m", message], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"the fix could not be committed: {(done.stderr or done.stdout).strip()[:300]}")
    return git(worktree, "rev-parse", "HEAD").strip()


def fix_worktree(repo: Path, branch: str, base: str) -> Path:
    """A worktree for the fix branch, starting from the bad ref."""
    path = repo / ".whodunit" / "fix" / branch.replace("/", "-")
    if path.exists():
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(path)], capture_output=True)
        shutil.rmtree(path, ignore_errors=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "--force", "-B", branch, str(path), base)
    return path


def revert(repo: str | Path, culprit: str, base: str, case_id: str) -> Fix:
    """Revert the culprit on a new branch that starts at the bad ref."""
    repo = Path(repo).resolve()
    branch = f"whodunit/{case_id}"
    worktree = fix_worktree(repo, branch, base)
    subject = git(repo, "show", "-s", "--format=%s", culprit).strip()
    done = subprocess.run(["git", "-C", str(worktree), "revert", "--no-commit", culprit], capture_output=True, text=True)
    if done.returncode != 0:
        subprocess.run(["git", "-C", str(worktree), "revert", "--abort"], capture_output=True)
        return Fix(branch, "revert", note="The revert does not apply cleanly on top of the later commits: " + (done.stderr.strip().splitlines() or ["no detail"])[-1])
    files = [f for f in git(worktree, "diff", "--cached", "--name-only").split("\n") if f]
    sha = _commit(worktree, f"Revert \"{subject}\"\n\nWhodunit case {case_id} named {culprit[:12]} as the commit that broke the agent.")
    return Fix(branch, "revert", sha, files=files)


PATCH_SYSTEM = """You fix a regression in an AI agent without undoing what the change was for.
You get the request behind the culprit commit, its diff, the root-cause brief and the current content of each file it touched.
Keep the intent of the request. Remove only the behaviour that causes the failure.
Answer with the complete new content of each file you change, and nothing else, in this form:

=== path/to/file
<full file content>
=== end"""


def patch(repo: str | Path, culprit: str, base: str, case_id: str, target: str, request: str | None, brief: dict | None) -> Fix:
    """Ask a model for a patch that keeps the culprit's intent, and commit it on a new branch."""
    repo = Path(repo).resolve()
    branch = f"whodunit/{case_id}"
    worktree = fix_worktree(repo, branch, base)
    subject = git(repo, "show", "-s", "--format=%s", culprit).strip()
    files = [f for f in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", culprit, "--", target).split("\n") if f and (worktree / f).is_file()]
    if not files:
        return Fix(branch, "patch", note="None of the files the culprit touched exist at the bad ref.")
    parts = [
        f"Request behind the culprit commit: {request or 'not recorded'}",
        f"Culprit commit {culprit[:12]}: {subject}",
        "Its diff:\n" + git(repo, "show", "--format=", culprit, "--", target)[:6000],
        "Root-cause brief:\n" + "\n".join(s["text"] for s in (brief or {}).get("sentences", [])),
    ]
    parts += [f"Current content of {f}:\n{(worktree / f).read_text()}" for f in files]
    try:
        answer = llm.ask(PATCH_SYSTEM, "\n\n".join(parts), max_tokens=8000, timeout=300)
    except llm.LlmError as exc:
        return Fix(branch, "patch", note=f"No patch was written: {exc}")
    changed = []
    for block in answer.split("\n=== end"):
        head, _, body = block.partition("=== ")[2].partition("\n")
        name = head.strip()
        if name in files and body.strip():
            (worktree / name).write_text(body.rstrip("\n") + "\n")
            changed.append(name)
    if not changed or not git(worktree, "status", "--porcelain").strip():
        return Fix(branch, "patch", note="The model's answer changed none of the culprit's files.")
    sha = _commit(worktree, f"Patch the regression from \"{subject}\"\n\nWhodunit case {case_id} named {culprit[:12]}. This keeps what that commit was for and removes the failure.")
    return Fix(branch, "patch", sha, files=changed)

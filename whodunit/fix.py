"""The fix: apply it on a branch, replay the case until the evidence clears the bar for keeping it, and keep the case.

A revert is mechanical. A patch that keeps the culprit's intent is written by a model and
checked the same way. Nothing here pushes or opens a pull request. That stays with the owner.
"""

import math
import os
import random
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import llm
from .suspects import git


@dataclass
class Verification:
    fixed: bool  # the bar for keeping a fix was cleared; see verify()
    probability: float  # P(its failure rate is back within 5 points of the rate before the culprit)
    replays: int
    failures: int
    note: str = ""
    better: float = 0.0  # P(it looks like the good side and not the bad side), the weaker claim
    upper: float = 1.0  # 95% upper bound on the fix commit's failure rate, from the same posterior
    voided: int = 0  # replays that hit a provider or network error and were left out


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


@lru_cache(maxsize=None)  # the seed is fixed, so the same counts always give the same answer
def probability_back_to_baseline(failures: int, passes: int, good: tuple[int, int], margin: float = 0.05, samples: int = 20000) -> float:
    """P(the fix commit's failure rate is within `margin` of the rate before the culprit).

    "Better than broken" is too low a bar: a patch that takes a bug from failing 9 runs in 10 to
    1 in 10 would pass it. This asks whether the failure rate is back where it was. Both rates
    are Beta posteriors and the comparison is done by sampling, with a fixed seed.
    """
    rng = random.Random(0)
    fa, fb = 0.5 + failures, 0.5 + passes
    ga, gb = 0.5 + good[0], 9.5 + good[1]
    hits = sum(rng.betavariate(fa, fb) <= rng.betavariate(ga, gb) + margin for _ in range(samples))
    return hits / samples


def _beta_cdf(x: float, a: float, b: float) -> float:
    """The regularised incomplete beta function, by its continued fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _beta_cdf(1.0 - x, b, a)  # the fraction converges quickly only on this side
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        for numerator in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)), -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-12:
            break
    return math.exp(a * math.log(x) + b * math.log(1.0 - x) - _log_beta(a, b)) * h / a


def upper_bound(failures: int, passes: int, level: float = 0.95) -> float:
    """The failure rate the fix commit is `level` likely to be at or under, given its replays.

    This is a quantile of the posterior probability_back_to_baseline uses for the fix commit,
    Beta(0.5 + failures, 0.5 + passes). It is what the case file prints next to the count,
    because "0 failures in 30" on its own sounds like more than it is: the bound is about 6%.
    """
    a, b = 0.5 + failures, 0.5 + passes
    low, high = 0.0, 1.0
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (middle, high) if _beta_cdf(middle, a, b) < level else (low, middle)
    return high


def observed(failures: int, replays: int) -> str:
    """What the replays of a fix showed, as the case file and the command line say it."""
    bound = upper_bound(failures, replays - failures)
    return f"{failures} {'failure' if failures == 1 else 'failures'} in {replays} replays. At most {bound:.1%} at 95%."


def verify(trial, good: tuple[int, int], bad: tuple[int, int], budget: int = 90, confidence: float = 0.95, parallel: int = 1, at_least: int = 12) -> Verification:
    """Replay the fix commit until its failure rate is 95% likely back to baseline, 95% likely not, or the budget is spent.

    With a clean baseline that takes about 30 replays without a failure. `better` records the
    weaker claim, that the fix commit looks like the good side and not the bad side.

    Clearing this bar is the reason to keep a fix. It is not proof that the bug is gone. In
    simulation a fix that still fails 4 runs in 100 clears it about one time in three, so what
    gets reported is the count and `upper`, the 95% bound on the failure rate after the fix.
    """
    from concurrent.futures import ThreadPoolExecutor

    failures = passes = voided = void_batches = 0
    probability = 0.5
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        while failures + passes < budget:
            batch = min(max(1, parallel), budget - failures - passes)
            verdicts = list(pool.map(lambda _: trial(), range(batch))) if batch > 1 else [trial()]
            if "skip" in verdicts:
                return Verification(False, 0.0, failures + passes, failures, "the fix commit will not build", upper=upper_bound(failures, passes), voided=voided)
            failures += verdicts.count("fail")
            passes += verdicts.count("pass")
            # A voided replay hit a provider or network error. It counts neither for the fix nor against it.
            voided += verdicts.count("void")
            void_batches = void_batches + 1 if all(v == "void" for v in verdicts) else 0
            if void_batches >= 3:
                return Verification(False, probability, failures + passes, failures, "the model provider or the network kept failing, so the fix could not be checked",
                                    upper=upper_bound(failures, passes), voided=voided)
            probability = probability_back_to_baseline(failures, passes, good)
            if failures + passes >= min(at_least, budget) and (probability >= confidence or probability <= 1 - confidence):
                break
    better = probability_fixed(failures, passes, good, bad)
    if probability >= confidence:
        note = ""
    elif probability <= 1 - confidence:
        note = "it still fails more often than before the culprit" + (", though less often than the broken commits do" if better >= confidence else "")
    else:
        note = "the replay budget ran out before the answer was clear"
    return Verification(probability >= confidence, probability, failures + passes, failures, note, better, upper_bound(failures, passes), voided)


@dataclass
class Fix:
    branch: str
    kind: str  # revert or patch
    commit: str | None = None
    note: str = ""
    files: list[str] = field(default_factory=list)


BOT = {"user.name": "whodunit", "user.email": "whodunit@whodunit.invalid"}  # .invalid is reserved, so this can never be someone's address


def _identity(worktree: Path) -> list[str]:
    """Git options that sign the commit as a bot, for whichever of name and address the machine has not set.

    A clean CI runner has no git identity, and `git commit` refuses to guess one there. An
    identity that is set, in git's config or in the environment, is always left alone.
    """
    options = []
    for key, variables in (("user.name", ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")), ("user.email", ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"))):
        configured = subprocess.run(["git", "-C", str(worktree), "config", "--get", key], capture_output=True, text=True).stdout.strip()
        if not configured and not all(os.environ.get(name) for name in variables):
            options += ["-c", f"{key}={BOT[key]}"]
    return options


def _commit(worktree: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True, capture_output=True)
    done = subprocess.run(["git", "-C", str(worktree), *_identity(worktree), "commit", "-q", "-m", message], capture_output=True, text=True)
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
    note = ""
    if done.returncode != 0:
        clashing = [f for f in git(worktree, "diff", "--name-only", "--diff-filter=U").split("\n") if f]
        if clashing and all(f.lower().endswith((".md", ".txt", ".rst")) for f in clashing):
            # The clash is in documents the agent does not run. Keep them as they are and revert the rest.
            for name in clashing:
                subprocess.run(["git", "-C", str(worktree), "checkout", "--ours", "--", name], capture_output=True)
                subprocess.run(["git", "-C", str(worktree), "add", "--", name], capture_output=True)
            note = f"The revert clashed with later edits to {', '.join(clashing)}, which the agent does not run, so those were left as they are."
        else:
            said = (done.stdout + "\n" + done.stderr).splitlines()
            why = next((line.strip() for line in said if line.startswith(("CONFLICT", "error:"))), "git gave no detail")
            subprocess.run(["git", "-C", str(worktree), "revert", "--abort"], capture_output=True)
            return Fix(branch, "revert", note="The revert does not apply cleanly on top of the later commits. " + why)
    files = [f for f in git(worktree, "diff", "--cached", "--name-only").split("\n") if f]
    sha = _commit(worktree, f"Revert \"{subject}\"\n\nWhodunit case {case_id} named {culprit[:12]} as the commit that broke the agent.")
    return Fix(branch, "revert", sha, note=note, files=files)


PATCH_SYSTEM = """You fix a regression in an AI agent without undoing what the change was for.
You get the request behind the culprit commit, its diff, the root-cause brief and the current content of each file it touched.
Keep the intent of the request. Remove only the behaviour that causes the failure. Change as little as you can.
Answer with edits and nothing else, in this form, one block per place you change:

=== path/to/file
<<<<<<< SEARCH
lines exactly as they are in the file now, enough of them to be unique
=======
the lines that replace them
>>>>>>> REPLACE
=== end"""

EDIT = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n?>>>>>>> REPLACE", re.S)


def apply_edits(answer: str, worktree: Path, allowed: list[str]) -> tuple[list[str], str]:
    """Apply the model's edits. Returns (files changed, what went wrong, if anything)."""
    changed, problems = [], []
    for block in answer.split("\n=== end"):
        head, _, body = block.partition("=== ")[2].partition("\n")
        name = head.strip()
        if not name:
            continue
        if name not in allowed:
            problems.append(f"{name} is not one of the files the culprit touched")
            continue
        text = original = (worktree / name).read_text()
        edits = EDIT.findall(body)
        if not edits and body.strip() and "<<<<<<<" not in body:
            text = body.rstrip("\n") + "\n"  # a whole file, which is also accepted
        for search, replace in edits:
            if text.count(search) != 1:
                problems.append(f"an edit to {name} matched {text.count(search)} places and needs to match exactly one")
                continue
            text = text.replace(search, replace)
        if text != original:
            (worktree / name).write_text(text)
            changed.append(name)
    return changed, "; ".join(problems)


def patch(repo: str | Path, culprit: str, base: str, case_id: str, target: str, request: str | None, brief: dict | None, feedback: str = "") -> Fix:
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
    if feedback:
        parts.append("An earlier patch was tried and the failure is still there. What happened:\n" + feedback)
    parts += [f"Current content of {f}:\n{(worktree / f).read_text()}" for f in files]
    try:
        answer = llm.ask(PATCH_SYSTEM, "\n\n".join(parts), max_tokens=3000, timeout=300)
    except llm.LlmError as exc:
        return Fix(branch, "patch", note=f"No patch was written: {exc}")
    changed, problems = apply_edits(answer, worktree, files)
    if not changed or not git(worktree, "status", "--porcelain").strip():
        return Fix(branch, "patch", note="The model's answer changed none of the culprit's files." + (f" {problems}." if problems else ""))
    sha = _commit(worktree, f"Patch the regression from \"{subject}\"\n\nWhodunit case {case_id} named {culprit[:12]}. This keeps what that commit was for and removes the failure.")
    return Fix(branch, "patch", sha, files=changed)

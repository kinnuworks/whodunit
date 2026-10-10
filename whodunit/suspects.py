"""The suspects: every commit after the last good ref, up to and including the first bad one."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

# A commit that never touched the agent's folder can still be guilty (a shared file, a
# lockfile higher up), so it keeps a small prior. Plain bisect ignores priors.
PRIOR_TOUCHES_TARGET = 1.0
PRIOR_ELSEWHERE = 0.05


@dataclass(frozen=True)
class Suspect:
    sha: str
    subject: str
    files: tuple[str, ...]
    checkpoint: str | None  # Entire checkpoint id from the commit trailer
    touches_target: bool
    prior: float
    alibi: str = ""  # why this commit starts with less suspicion, when entire-graph gives a reason

    @property
    def short(self) -> str:
        return self.sha[:12]


def git(repo: str | Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def resolve(repo: str | Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def list_suspects(repo: str | Path, good: str, bad: str, target: str = ".", graph: bool = False) -> list[Suspect]:
    """Commits in good..bad, oldest first. The last one is the bad ref itself.

    The path filter gives the first prior: a commit that never touched the agent's folder keeps
    a small one. With `graph`, entire-graph refines it for the commits that did, by asking
    whether what they changed is something the agent runs.
    """
    shas = git(repo, "rev-list", "--reverse", "--ancestry-path", f"{good}..{bad}").split()
    prefix = "" if target in (".", "") else target.rstrip("/") + "/"
    suspects = []
    for sha in shas:
        subject, _, trailer = git(
            repo, "show", "-s", "--format=%s%x00%(trailers:key=Entire-Checkpoint,valueonly,separator=%x20)", sha
        ).strip().partition("\x00")
        files = tuple(git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--first-parent", sha).split("\n"))
        files = tuple(f for f in files if f)
        touches = any(f.startswith(prefix) for f in files)
        prior, alibi = (PRIOR_TOUCHES_TARGET, "") if touches else (PRIOR_ELSEWHERE, "never touched the agent's folder")
        if graph and touches:
            from .graph import alibi as graph_alibi  # imported here because graph.py uses git() from this module

            prior, reason = graph_alibi(repo, sha, target)
            alibi = reason if prior < 1.0 else ""
        suspects.append(Suspect(
            sha=sha, subject=subject, files=files, checkpoint=trailer.split()[0] if trailer.strip() else None,
            touches_target=touches, prior=prior, alibi=alibi,
        ))
    return suspects

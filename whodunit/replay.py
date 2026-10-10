"""Replay a case's inputs against a commit, in a git worktree of its own."""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .case import Case, CaseInput, judge
from .suspects import git, resolve

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass(frozen=True)
class Replay:
    sha: str
    input: str
    verdict: str  # pass, fail or skip
    reason: str
    seconds: float


class Runner:
    """Keeps one worktree per commit under .whodunit/worktrees and counts every replay it runs."""

    def __init__(self, repo: str | Path, case: Case, keep: bool = False):
        self.repo = Path(repo).resolve()
        self.case = case
        self.keep = keep
        self.root = self.repo / ".whodunit" / "worktrees"
        self.built: dict[str, str | None] = {}  # sha -> None if the build worked, else why it did not
        self.replays: list[Replay] = []
        subprocess.run(["git", "-C", str(self.repo), "worktree", "prune"], capture_output=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if not self.keep:
            self.clean()

    def worktree(self, sha: str) -> Path:
        path = self.root / sha[:12]
        if not path.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            git(self.repo, "worktree", "add", "--detach", "--force", str(path), sha)
        return path

    def clean(self) -> None:
        for sha in list(self.built):
            path = self.root / sha[:12]
            if path.exists():
                subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(path)], capture_output=True)
        self.built.clear()

    def _env(self, sha: str) -> dict:
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env.update(self.case.env)
        env["WHODUNIT_COMMIT"] = sha
        env["WHODUNIT_CASE"] = self.case.id
        dotenv = self.repo / ".env"
        if dotenv.is_file():
            env.setdefault("WHODUNIT_ENV", str(dotenv))  # a path only; the agent reads the keys itself
        return env

    def build(self, sha: str) -> str | None:
        """Check the commit out and build it once. Returns why it failed, or None."""
        if sha in self.built:
            return self.built[sha]
        problem = None
        cwd = self.worktree(sha) / self.case.target
        if not cwd.is_dir():
            problem = f"{self.case.target} does not exist at this commit"
        elif self.case.build:
            try:
                done = subprocess.run(list(self.case.build), cwd=cwd, env=self._env(sha), capture_output=True, text=True, timeout=self.case.timeout)
                if done.returncode != 0:
                    problem = "build failed: " + ((done.stderr.strip() or done.stdout.strip()).splitlines() or ["no output"])[-1]
            except (OSError, subprocess.TimeoutExpired) as exc:
                problem = f"build failed: {exc}"
        self.built[sha] = problem
        return problem

    def replay(self, ref: str, case_input: CaseInput) -> Replay:
        """Run the agent once at this commit with this input and judge the result."""
        sha = resolve(self.repo, ref)
        started = time.monotonic()
        problem = self.build(sha)
        if problem:
            verdict, reason = SKIP, problem
        else:
            cwd = self.worktree(sha) / self.case.target
            command = [part.replace("{input}", case_input.text) for part in self.case.run]
            try:
                done = subprocess.run(command, cwd=cwd, env=self._env(sha), capture_output=True, text=True, timeout=self.case.timeout)
                passed, reason = judge(self.case, case_input, done.stdout, cwd)
                if not passed and done.returncode != 0:
                    reason = f"exit {done.returncode}: " + ((done.stderr.strip().splitlines() or [reason])[-1])
                verdict = PASS if passed else FAIL
            except subprocess.TimeoutExpired:
                verdict, reason = FAIL, f"timed out after {self.case.timeout:.0f}s"
        result = Replay(sha=sha, input=case_input.text, verdict=verdict, reason=reason, seconds=time.monotonic() - started)
        self.replays.append(result)
        return result

    def test_commit(self, ref: str) -> tuple[str, list[Replay]]:
        """Every input once. The commit fails if any input fails, and is skipped if it will not build."""
        results = []
        for case_input in self.case.inputs:
            result = self.replay(ref, case_input)
            results.append(result)
            if result.verdict != PASS:
                return result.verdict, results
        return PASS, results

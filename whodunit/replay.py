"""Replay a case's inputs against a commit, in a git worktree of its own."""

import hashlib
import os
import signal
import subprocess
import threading
import time
from collections import defaultdict
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
    started: float = 0.0  # wall clock, seconds since the epoch
    tag: str = ""  # the case tag this replay's run carries in its trace, unique to the replay


def run_command(command: list[str], cwd: Path, env: dict, timeout: float) -> subprocess.CompletedProcess:
    """Like subprocess.run, but a timeout stops the whole process group.

    The replay command is usually `uv run ...`, which starts the agent as a child. Killing only
    `uv` would leave the agent running.
    """
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


class Runner:
    """Keeps one worktree per commit under .whodunit/worktrees and counts every replay it runs."""

    def __init__(self, repo: str | Path, case: Case, keep: bool = False):
        self.repo = Path(repo).resolve()
        self.case = case
        self.keep = keep
        # One folder per runner, so two runs in the same repo never remove each other's worktrees.
        self.root = self.repo / ".whodunit" / "worktrees" / str(os.getpid())
        self.built: dict[str, str | None] = {}  # sha -> None if the build worked, else why it did not
        self.replays: list[Replay] = []
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)  # one build at a time per commit
        self._turn: dict[str, int] = defaultdict(int)  # which input a commit gets next
        self._count = 0
        self._first = int(time.time()) % 100000 * 1000  # so tags from separate runs of one case never collide
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
        try:
            self.root.rmdir()
        except OSError:
            pass

    def _env(self, sha: str, tag: str = "") -> dict:
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env.update(self.case.env)
        env["WHODUNIT_COMMIT"] = sha
        if self.case.id:
            env["WHODUNIT_CASE"] = tag or self.case.id
        else:
            env.pop("WHODUNIT_CASE", None)  # ordinary traffic carries no case tag
        lock = self.root / sha[:12] / self.case.target / "uv.lock"
        if lock.is_file():
            # Worktrees with the same lockfile share one environment, so a new commit does not
            # mean a new install. A commit that changes the lockfile gets its own.
            digest = hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
            env.setdefault("UV_PROJECT_ENVIRONMENT", str(self.repo / ".whodunit" / "envs" / digest))
        dotenv = self.repo / ".env"
        if dotenv.is_file():
            env.setdefault("WHODUNIT_ENV", str(dotenv))  # a path only; the agent reads the keys itself
        return env

    def build(self, sha: str) -> str | None:
        """Check the commit out and build it once. Returns why it failed, or None."""
        with self._locks[sha]:
            return self._build(sha)

    def _build(self, sha: str) -> str | None:
        if sha in self.built:
            return self.built[sha]
        problem = None
        cwd = self.worktree(sha) / self.case.target
        if not cwd.is_dir():
            problem = f"{self.case.target} does not exist at this commit"
        elif self.case.build:
            try:
                done = run_command(list(self.case.build), cwd, self._env(sha), self.case.timeout)
                if done.returncode != 0:
                    problem = "build failed: " + ((done.stderr.strip() or done.stdout.strip()).splitlines() or ["no output"])[-1]
            except (OSError, subprocess.TimeoutExpired) as exc:
                problem = f"build failed: {exc}"
        self.built[sha] = problem
        return problem

    def replay(self, ref: str, case_input: CaseInput) -> Replay:
        """Run the agent once at this commit with this input and judge the result."""
        sha = resolve(self.repo, ref)
        started, clock = time.monotonic(), time.time()
        with self._locks["#"]:
            self._count += 1
            # The agent writes WHODUNIT_CASE into its trace, so a number after the case id lets
            # one replay be matched to exactly one run afterwards.
            tag = f"{self.case.id}/{self._first + self._count}" if self.case.id else ""
        problem = self.build(sha)
        if problem:
            verdict, reason = SKIP, problem
        else:
            cwd = self.worktree(sha) / self.case.target
            command = [part.replace("{input}", case_input.text) for part in self.case.run]
            try:
                done = run_command(command, cwd, self._env(sha, tag), self.case.timeout)
                passed, reason = judge(self.case, case_input, done.stdout, cwd)
                if not passed and done.returncode != 0:
                    reason = f"exit {done.returncode}: " + ((done.stderr.strip().splitlines() or [reason])[-1])
                verdict = PASS if passed else FAIL
            except subprocess.TimeoutExpired:
                verdict, reason = FAIL, f"timed out after {self.case.timeout:.0f}s"
        result = Replay(sha=sha, input=case_input.text, verdict=verdict, reason=reason, seconds=time.monotonic() - started, started=clock, tag=tag)
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

    def trial(self, ref: str) -> str:
        """One replay at this commit, taking the case inputs in turn. This is what the statistical bisect calls."""
        sha = resolve(self.repo, ref)
        with self._locks[sha]:
            turn = self._turn[sha]
            self._turn[sha] += 1
        return self.replay(sha, self.case.inputs[turn % len(self.case.inputs)]).verdict

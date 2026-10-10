"""A case: a symptom, the failing inputs, a good ref, a bad ref and a check."""

import json
import math
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CaseInput:
    text: str
    expect: dict = field(default_factory=dict)  # what the check compares against, e.g. {"refunds": [...]}


@dataclass(frozen=True)
class Case:
    id: str
    symptom: str
    good: str
    bad: str
    inputs: tuple[CaseInput, ...]
    target: str = "."  # folder inside the repo that holds the agent
    build: tuple[str, ...] = ()  # run once per worktree; a failure skips the commit
    run: tuple[str, ...] = ()  # "{input}" is replaced with the input text
    check: dict = field(default_factory=lambda: {"kind": "refunds"})
    env: dict = field(default_factory=dict)
    timeout: float = 120.0

    @classmethod
    def load(cls, path: str | Path) -> "Case":
        data = tomllib.loads(Path(path).read_text())
        inputs = tuple(
            CaseInput(text=i["text"], expect={k: v for k, v in i.items() if k != "text"}) for i in data.pop("inputs")
        )
        for key in ("build", "run"):
            data[key] = tuple(data.get(key, ()))
        return cls(inputs=inputs, **data)


def last_json_line(stdout: str) -> dict | None:
    """The agent prints its result as one JSON object on the last line that parses."""
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _same_refunds(got: list[dict], want: list[dict]) -> bool:
    def key(r):
        return (str(r.get("order_id")), float(r.get("refunded", 0)))

    got, want = sorted(map(key, got)), sorted(map(key, want))
    return len(got) == len(want) and all(g[0] == w[0] and math.isclose(g[1], w[1], abs_tol=0.005) for g, w in zip(got, want))


def judge(case: Case, case_input: CaseInput, stdout: str, cwd: Path) -> tuple[bool, str]:
    """Return (passed, reason) for one run of the agent."""
    kind = case.check.get("kind", "refunds")
    result = last_json_line(stdout)
    if kind == "refunds":
        if result is None:
            return False, "the agent printed no JSON result"
        want = case_input.expect.get("refunds", [])
        got = result.get("refunds", [])
        if _same_refunds(got, want):
            return True, f"refunds match: {json.dumps(got)}"
        return False, f"refunds were {json.dumps(got)}, expected {json.dumps(want)}"
    if kind == "command":
        # The command gets the agent's stdout on stdin and the expectation in WHODUNIT_EXPECT. Exit 0 is a pass.
        done = subprocess.run(
            case.check["command"], input=stdout, capture_output=True, text=True, cwd=cwd, timeout=case.timeout,
            env={**os.environ, "WHODUNIT_EXPECT": json.dumps(case_input.expect)},
        )
        reason = (done.stdout.strip() or done.stderr.strip()).splitlines()[-1:] or [f"exit {done.returncode}"]
        return done.returncode == 0, reason[0]
    raise ValueError(f"check kind {kind!r} is not one of refunds, command")

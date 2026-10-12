"""A case: a symptom, the failing inputs, a good ref, a bad ref and a check."""

import json
import math
import os
import re
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
    # Keys the agent needs under names of its own: the agent's name for each, and the name it has in the
    # environment or the .env of whoever runs the case. Only names are written here, never a value.
    env_from: dict = field(default_factory=dict)
    timeout: float = 120.0
    fixed: str = ""  # the commit that fixed it, once the case is closed and kept as a regression test
    traffic_sent_by: str = ""  # who sent the agent's ordinary runs, when it was a script and not real users
    # How the agent says "the model provider or the network failed, and my own code did not". A replay
    # that ends this way is voided and run again, and is never evidence about the commit.
    void_exit_codes: tuple[int, ...] = ()  # exit codes the agent keeps for that
    void_stderr: tuple[str, ...] = ()  # for commits from before it had one: text on the last line of stderr, with a non-zero exit

    @classmethod
    def load(cls, path: str | Path) -> "Case":
        data = tomllib.loads(Path(path).read_text())
        inputs = tuple(
            CaseInput(text=i["text"], expect={k: v for k, v in i.items() if k != "text"}) for i in data.pop("inputs")
        )
        for key in ("build", "run", "void_exit_codes", "void_stderr"):
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


def printed_json(stdout: str) -> dict | None:
    """The result an agent printed, whether on one line or pretty-printed over many.

    Tried in turn: the whole output, the last line that parses, and the last block that opens
    with a brace at the start of a line and runs to the end.
    """
    text = stdout.strip()
    try:
        whole = json.loads(text)
        if isinstance(whole, dict):
            return whole
    except json.JSONDecodeError:
        pass
    lines = text.splitlines()
    if lines and lines[-1].lstrip().startswith("{"):
        found = last_json_line(text)
        if found is not None:
            return found
    for start in range(len(lines) - 1, -1, -1):
        if lines[start].startswith("{"):
            try:
                block = json.loads("\n".join(lines[start:]))
            except json.JSONDecodeError:
                continue
            if isinstance(block, dict):
                return block
    return None


def _at(result: dict, path: str):
    """A value inside the printed result, by a dotted path such as "output.tool_calls"."""
    for key in path.split("."):
        if not isinstance(result, dict) or key not in result:
            return None
        result = result[key]
    return result


def _holds(got, how: str, value) -> bool:
    if how == "in":
        return any(_fits(got, one) for one in value)
    if how == "contains":
        return got is not None and str(value).lower() in str(got).lower()
    if how == "regex":
        return got is not None and re.search(value, str(got), re.IGNORECASE) is not None
    if how in ("gte", "lte"):
        number = isinstance(got, (int, float)) and not isinstance(got, bool)
        return number and (got >= value if how == "gte" else got <= value)
    raise ValueError(f"argument matcher {how!r} is not one of in, contains, regex, gte, lte")


def _fits(got, want) -> bool:
    """Whether an argument has the wanted value.

    A plain value has to be equal, with numbers compared to half a cent and strings without
    their outer spaces. A table asks for something looser, and every entry in it has to hold:
    `in` (any of these), `contains` and `regex` (both ignoring case), `gte` and `lte`.
    """
    if isinstance(want, dict):
        return bool(want) and all(_holds(got, how, value) for how, value in want.items())
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        return isinstance(got, (int, float)) and not isinstance(got, bool) and math.isclose(got, want, abs_tol=0.005)
    if isinstance(want, str) and isinstance(got, str):
        return got.strip() == want.strip()
    return got == want


# What an input of a "calls" case may expect. Anything else in the input is a mistake and is refused,
# so a misspelt expectation cannot pass by being ignored.
CALLS_EXPECT = ("must_call", "must_not_call", "first_call", "call_counts", "call_sequence", "call_args",
                "reply_contains", "reply_not_contains", "reply_regex", "reply_not_regex")


def _calls_verdict(check: dict, expect: dict, result: dict) -> tuple[bool, str]:
    """Judge a run by the tools it called and what it said, read from the JSON it printed."""
    unknown = sorted(set(expect) - set(CALLS_EXPECT))
    if unknown:
        raise ValueError(f"a calls check does not know {unknown}. It knows {', '.join(CALLS_EXPECT)}.")
    name_key, args_key = check.get("name", "name"), check.get("args", "args")
    calls = _at(result, check.get("calls", "tool_calls"))
    calls = [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
    names = [str(c.get(name_key)) for c in calls]
    reply = _at(result, check.get("reply", "reply"))
    reply = reply if isinstance(reply, str) else ""
    said = f"called {', '.join(names) or 'nothing'}"

    missing = [tool for tool in expect.get("must_call", []) if tool not in names]
    if missing:
        return False, f"never called {', '.join(missing)} ({said})"
    made = [tool for tool in expect.get("must_not_call", []) if tool in names]
    if made:
        return False, f"called {', '.join(made)}, which it should not have"
    first = expect.get("first_call")
    if first and names[:1] != [first]:
        return False, f"the first call was {names[0] if names else 'none'}, expected {first}"
    for tool, times in (expect.get("call_counts") or {}).items():
        if names.count(tool) != times:
            return False, f"called {tool} {names.count(tool)} times, expected {times}"
    rest = iter(names)
    if not all(any(name == tool for name in rest) for tool in expect.get("call_sequence", [])):
        return False, f"the calls were not in the order {', '.join(expect['call_sequence'])} ({said})"
    for wanted in expect.get("call_args", []):
        tool, args = wanted["tool"], wanted.get("args", {})
        tried = [c.get(args_key) if isinstance(c.get(args_key), dict) else {} for c in calls if c.get(name_key) == tool]
        if not any(all(_fits(given.get(key), value) for key, value in args.items()) for given in tried):
            return False, f"no call to {tool} had {json.dumps(args)}. It was called with {json.dumps(tried)}"
    low = reply.lower()
    absent = [text for text in expect.get("reply_contains", []) if text.lower() not in low]
    if absent:
        return False, f"the reply does not say {json.dumps(absent)}"
    present = [text for text in expect.get("reply_not_contains", []) if text.lower() in low]
    if present:
        return False, f"the reply says {json.dumps(present)}, which it should not"
    unmatched = [pattern for pattern in expect.get("reply_regex", []) if not re.search(pattern, reply, re.IGNORECASE)]
    if unmatched:
        return False, f"the reply does not match {json.dumps(unmatched)}"
    matched = [pattern for pattern in expect.get("reply_not_regex", []) if re.search(pattern, reply, re.IGNORECASE)]
    if matched:
        return False, f"the reply matches {json.dumps(matched)}, which it should not"
    return True, f"{said}, and the reply holds what it should"


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
    if kind == "calls":
        # For any agent that prints its tool calls and its reply as JSON. The case says where in that
        # JSON they are (calls, name, args, reply), and each input says what a right run looks like.
        result = printed_json(stdout)
        if result is None:
            return False, "the agent printed no JSON result"
        return _calls_verdict(case.check, case_input.expect, result)
    if kind == "command":
        # The command gets the agent's stdout on stdin and the expectation in WHODUNIT_EXPECT. Exit 0 is a pass.
        done = subprocess.run(
            case.check["command"], input=stdout, capture_output=True, text=True, cwd=cwd, timeout=case.timeout,
            env={**os.environ, "WHODUNIT_EXPECT": json.dumps(case_input.expect)},
        )
        reason = (done.stdout.strip() or done.stderr.strip()).splitlines()[-1:] or [f"exit {done.returncode}"]
        return done.returncode == 0, reason[0]
    raise ValueError(f"check kind {kind!r} is not one of refunds, calls, command")

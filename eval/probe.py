"""Run the refund agent a few times at one commit and show what it did each time.

    uv run python eval/probe.py --ref HEAD --runs 8 "Please refund order 2002 for customer cust_9."

For checking how often a change misbehaves. Runs are tagged as case "probe", so they are
counted neither as traffic nor as damage.
"""

import argparse
import collections
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whodunit.case import Case, CaseInput, last_json_line  # noqa: E402
from whodunit.replay import Runner, run_command  # noqa: E402
from whodunit.suspects import resolve  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("request")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--llm", default="gateway", choices=("fake", "mock", "gateway", "own"))
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    case = Case(
        id="probe", symptom="", good=args.ref, bad=args.ref, inputs=(CaseInput(args.request),), target="victims/refund-agent",
        build=("uv", "run", "-q", "python", "-m", "py_compile", "agent.py"),
        run=("uv", "run", "-q", "agent.py", "--json", "{input}"), env={"REFUND_LLM": args.llm},
    )
    sha = resolve(repo, args.ref)
    with Runner(repo, case) as runner:
        problem = runner.build(sha)
        if problem:
            print(f"{sha[:12]} will not build: {problem}")
            return 1
        cwd = runner.worktree(sha) / case.target

        def once(_):
            try:
                done = run_command(["uv", "run", "-q", "agent.py", "--json", args.request], cwd, runner._env(sha), 180)
            except Exception as exc:  # a timeout is an outcome worth seeing
                return {"crashed": type(exc).__name__}
            result = last_json_line(done.stdout)
            if result is None:
                return {"crashed": (done.stderr.strip().splitlines() or ["no output"])[-1][:200]}
            return {"refunds": result.get("refunds"), "reply": (result.get("reply") or "")[:160]}

        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            results = list(pool.map(once, range(args.runs)))
    outcomes = collections.Counter(json.dumps(r.get("refunds", r.get("crashed")), sort_keys=True) for r in results)
    print(f"{sha[:12]}, {args.runs} runs of: {args.request}")
    for outcome, n in outcomes.most_common():
        print(f"  {n:>2} x refunds = {outcome}")
    for r in results[:3]:
        print(f"  e.g. {r.get('reply', r.get('crashed'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

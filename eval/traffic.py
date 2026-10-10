"""Send ordinary traffic through the refund agent, commit by commit.

    uv run python eval/traffic.py --good <ref> --bad <ref> --runs 6 --llm gateway

A real agent serves requests while its code changes underneath it. This walks the commits in
good..bad, oldest first, and at each one runs the agent on a few everyday requests, so the
traces carry the history that `whodunit onset` and `whodunit damages` read. The runs are not
tagged with a case, which is how Whodunit tells traffic from its own replays.

Nothing here knows which commit is the culprit.
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whodunit.case import Case, CaseInput  # noqa: E402
from whodunit.replay import Runner  # noqa: E402
from whodunit.suspects import list_suspects, resolve  # noqa: E402

REQUESTS = [
    "Please refund order 1001 for customer cust_9.",
    "Please refund order 1002 for customer cust_9.",
    "Please refund order 2002 for customer cust_4.",
    "Please refund order 3003 for customer cust_7.",
    "Please refund order 2002 for customer cust_9.",
    "Please refund order 4512 for customer cust_9.",
    "Hi, order 1001 arrived broken and I would like my money back. I am cust_9.",
    "I am cust_7. Can you refund order 3003? It never showed up.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--target", default="victims/refund-agent")
    parser.add_argument("--good", required=True)
    parser.add_argument("--bad", default="HEAD")
    parser.add_argument("--runs", type=int, default=6, help="requests per commit")
    parser.add_argument("--llm", default="fake", choices=("fake", "mock", "gateway", "own"))
    parser.add_argument("--trace-to", default="neatroots", choices=("neatroots", "neatlogs"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--cases", help="a folder of case files whose inputs join the mix, as the requests customers were sending when things went wrong")
    parser.add_argument("--only-cases", action="store_true", help="send only the requests from --cases")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    rng = random.Random(args.seed)
    case = Case(
        id="", symptom="", good=args.good, bad=args.bad, inputs=(), target=args.target,
        build=("uv", "run", "-q", "python", "-m", "py_compile", "agent.py"),
        run=("uv", "run", "-q", "agent.py", "--json", "{input}"),
        env={"REFUND_LLM": args.llm, "TRACE_TO": args.trace_to},
    )
    requests = [] if args.only_cases else list(REQUESTS)
    if args.cases:
        import tomllib

        for path in sorted(Path(args.cases).glob("*.toml")):
            requests += [i["text"] for i in tomllib.loads(path.read_text()).get("inputs", [])]
    requests = list(dict.fromkeys(requests))
    commits = [resolve(repo, args.good)] + [s.sha for s in list_suspects(repo, args.good, args.bad, args.target)]
    sent = skipped = 0
    with Runner(repo, case) as runner:
        for sha in commits:
            for request in rng.sample(requests, k=min(args.runs, len(requests))):
                result = runner.replay(sha, CaseInput(request))  # with no expectation the verdict means nothing here
                if result.verdict == "skip":
                    skipped += 1
                    break
                sent += 1
            print(f"{sha[:12]}  sent {sent} so far")
    print(f"{sent} runs across {len(commits)} commits. {skipped} commits would not build and got none.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

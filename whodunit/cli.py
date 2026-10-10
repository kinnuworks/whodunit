"""The whodunit command."""

import argparse
import json
import sys
from pathlib import Path

from .case import Case
from .lineup import linear_scan_cost, plain_bisect
from .replay import FAIL, PASS, Runner
from .suspects import list_suspects, resolve


def lineup(args) -> int:
    case = Case.load(args.case)
    repo = Path(args.repo).resolve()
    suspects = list_suspects(repo, case.good, case.bad, case.target)
    if not suspects:
        print(f"No commits between {case.good} and {case.bad}. Nothing to investigate.")
        return 2
    say = print if not args.json else (lambda *a, **k: print(*a, **k, file=sys.stderr))
    say(f"Case {case.id}: {case.symptom}")
    say(f"Suspects: {len(suspects)}, of which {sum(s.touches_target for s in suspects)} touched {case.target}.")

    with Runner(repo, case, keep=args.keep) as runner:
        # Check the alibis first. If the good ref fails or the bad ref passes, the case is wrong.
        verdict, results = runner.test_commit(case.good)
        say(f"  last good  {resolve(repo, case.good)[:12]}  {verdict}  {results[-1].reason}")
        if verdict != PASS:
            say("The good ref does not pass, so there is no clean starting point.")
            return 2
        verdict, results = runner.test_commit(case.bad)
        say(f"  first bad  {suspects[-1].short}  {verdict}  {results[-1].reason}")
        if verdict != FAIL:
            say("The bad ref does not fail, so there is nothing to find.")
            return 2

        def test(index: int) -> str:
            verdict, results = runner.test_commit(suspects[index].sha)
            say(f"  suspect {index + 1:>2}  {suspects[index].short}  {verdict}  {results[-1].reason}")
            return verdict

        found = plain_bisect(len(suspects), test)
        replays = len(runner.replays)
        seconds = sum(r.seconds for r in runner.replays)

    report = {
        "case": case.id,
        "suspects": len(suspects),
        "commits_tested": len(found.tested) + 2,
        "replays": replays,
        "seconds": round(seconds, 1),
        "culprit": None,
        "remaining": [suspects[i].sha for i in found.remaining],
    }
    if found.culprit is not None:
        culprit = suspects[found.culprit]
        report["culprit"] = {"sha": culprit.sha, "subject": culprit.subject, "checkpoint": culprit.checkpoint, "files": list(culprit.files)}
        report["linear_scan_commits"] = linear_scan_cost(found.culprit)
        say("")
        say(f"Suspects: {len(suspects)}. Cleared: {len(suspects) - 1}.")
        say(f"Culprit: {culprit.short}  {culprit.subject}")
        say(f"Checkpoint: {culprit.checkpoint or 'none on this commit'}")
        say(f"Tested {report['commits_tested']} commits with {replays} replays in {seconds:.0f}s. A scan from the oldest suspect would have tested {report['linear_scan_commits']}.")
    else:
        say("")
        say(f"Could not get it down to one. {len(found.remaining)} suspects remain because the commits between them would not build:")
        for i in found.remaining:
            say(f"  {suspects[i].short}  {suspects[i].subject}")
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if found.culprit is not None else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whodunit", description="Find the commit that broke an AI agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("lineup", help="replay a case against the suspect commits and name the culprit")
    p.add_argument("case", help="path to a case file (TOML)")
    p.add_argument("--repo", default=".", help="the git repo that holds the agent (default: here)")
    p.add_argument("--keep", action="store_true", help="leave the worktrees in .whodunit/worktrees")
    p.add_argument("--json", action="store_true", help="print the result as JSON on stdout")
    p.set_defaults(func=lineup)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

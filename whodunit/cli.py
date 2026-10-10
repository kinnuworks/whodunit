"""The whodunit command."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .case import Case
from . import brief as briefs
from . import casefile
from . import damages as damage
from . import fix as fixes
from . import ruling as rulings
from .motive import find_motive
from .neat import NeatError, neatroots
from .lineup import linear_scan_cost, plain_bisect, statistical_bisect
from .replay import FAIL, PASS, Runner
from .suspects import git, list_suspects, resolve


def record_path(args) -> Path:
    """The case record sits next to the case file unless --record says otherwise."""
    if getattr(args, "record", None):
        return Path(args.record)
    case = Path(args.case)
    return case.with_name(case.stem + ".record.json")


def load_record(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


def save_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1) + "\n")


def _plain(args, case, repo, suspects, runner, say):
    # Check the alibis first. If the good ref fails or the bad ref passes, the case is wrong.
    verdict, results = runner.test_commit(case.good)
    say(f"  last good  {resolve(repo, case.good)[:12]}  {verdict}  {results[-1].reason}")
    if verdict != PASS:
        say("The good ref does not pass, so there is no clean starting point.")
        return None
    verdict, results = runner.test_commit(case.bad)
    say(f"  first bad  {suspects[-1].short}  {verdict}  {results[-1].reason}")
    if verdict != FAIL:
        say("The bad ref does not fail, so there is nothing to find.")
        return None

    def test(index: int) -> str:
        verdict, results = runner.test_commit(suspects[index].sha)
        say(f"  suspect {index + 1:>2}  {suspects[index].short}  {verdict}  {results[-1].reason}")
        return verdict

    return plain_bisect(len(suspects), test)


def _statistical(args, case, suspects, runner, say):
    def trial(position: int) -> str:
        return runner.trial(case.good if position < 0 else suspects[position].sha)

    def on_round(positions: list[int], verdicts: list[str], posterior: list[float]) -> None:
        top = max(range(len(posterior)), key=posterior.__getitem__)
        for position in dict.fromkeys(positions):
            who = "last good " if position < 0 else f"suspect {position + 1:>2}"
            marks = "".join("F" if v == FAIL else "." if v == PASS else "s" for p, v in zip(positions, verdicts) if p == position)
            say(f"  {who}  {marks:<8}  top suspect {top + 1:>2} at {posterior[top]:5.1%}")

    priors = None if args.no_priors else [s.prior for s in suspects]
    say(f"Statistical bisect, at most {args.budget} replays, {args.parallel} at a time. F is a failed replay, a dot is a pass.")
    return statistical_bisect(
        len(suspects), trial, args.budget, priors=priors, confidence=args.confidence, parallel=args.parallel, on_round=on_round,
    )


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
        found = _plain(args, case, repo, suspects, runner, say) if args.method == "plain" else _statistical(args, case, suspects, runner, say)
        replays = sum(r.verdict != "skip" for r in runner.replays)
        seconds = sum(r.seconds for r in runner.replays)
        commits = len({r.sha for r in runner.replays})
        every_replay = [asdict(r) for r in runner.replays]
    if found is None:
        return 2

    report = {
        "case": case.id,
        "method": args.method,
        "suspects": len(suspects),
        "commits_tested": commits,
        "replays": replays,
        "seconds": round(seconds, 1),
        "culprit": None,
        "remaining": [{"sha": suspects[i].sha, "subject": suspects[i].subject, **({"probability": round(found.posterior[i], 4)} if found.posterior else {})} for i in found.remaining],
    }
    if found.rates:
        report["failure_rate_before"], report["failure_rate_from"] = (round(r, 3) for r in found.rates)
    say("")
    if found.culprit is not None:
        culprit = suspects[found.culprit]
        report["culprit"] = {"sha": culprit.sha, "subject": culprit.subject, "checkpoint": culprit.checkpoint, "files": list(culprit.files)}
        report["linear_scan_commits"] = linear_scan_cost(found.culprit)
        if found.posterior:
            report["culprit"]["probability"] = round(found.posterior[found.culprit], 4)
        say(f"Suspects: {len(suspects)}. Cleared: {len(suspects) - 1}.")
        say(f"Culprit: {culprit.short}  {culprit.subject}")
        if found.posterior:
            say(f"Confidence: {found.posterior[found.culprit]:.1%}. It fails about {found.rates[1]:.0%} of the time from this commit on, and {found.rates[0]:.0%} before it.")
        say(f"Checkpoint: {culprit.checkpoint or 'none on this commit'}")
        say(f"Tested {commits} commits with {replays} replays in {seconds:.0f}s of replay time. A scan from the oldest suspect would have tested {report['linear_scan_commits']} commits.")
    elif found.note:
        report["note"] = found.note
        say(f"Nobody named: {found.note}.")
    elif found.posterior:
        say(f"Nobody named. The replay budget of {args.budget} ran out before any suspect reached {args.confidence:.0%}. Still in the lineup:")
        for i in found.remaining:
            say(f"  {found.posterior[i]:6.1%}  {suspects[i].short}  {suspects[i].subject}")
    else:
        say(f"Could not get it down to one. {len(found.remaining)} suspects remain because the commits between them would not build:")
        for i in found.remaining:
            say(f"  {suspects[i].short}  {suspects[i].subject}")
    record = load_record(record_path(args))
    record["case"] = {"id": case.id, "symptom": case.symptom, "good": resolve(repo, case.good), "bad": resolve(repo, case.bad), "target": case.target, "file": str(Path(args.case).resolve()), "repo": str(repo)}
    record["suspects"] = [
        {"sha": s.sha, "subject": s.subject, "checkpoint": s.checkpoint, "touches_target": s.touches_target,
         **({"probability": round(found.posterior[i], 5)} if found.posterior else {})}
        for i, s in enumerate(suspects)
    ]
    record["lineup"] = report
    record["replays"] = every_replay
    save_record(record_path(args), record)
    say(f"Record: {record_path(args)}")
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if found.culprit is not None else 1


def motive(args) -> int:
    found = find_motive(Path(args.repo).resolve(), args.commit)
    if args.json:
        print(json.dumps(found.to_dict(), indent=2))
        return 0 if found.request else 1
    print(f"Commit {found.sha[:12]}  {found.subject}")
    print(f"Checkpoint: {found.checkpoint or 'none'}" + (f"  {found.link}" if found.link and found.checkpoint else ""))
    if found.note:
        print(found.note)
    if not found.request:
        return 1
    print(f"Asked of {found.agent or 'the coding agent'} ({found.model or 'model unknown'}) at {found.request_time}:")
    print()
    for line in found.request.splitlines():
        print(f"    {line}")
    print()
    if found.earlier_requests:
        print("Earlier in the same session:")
        for text in found.earlier_requests:
            print(f"    {text.splitlines()[0][:110]}")
        print()
    print(f"What the agent did next ({len(found.steps)} steps kept):")
    for step in found.steps[-args.steps:]:
        text = step.text.strip().splitlines()[0][:120] if step.text.strip() else ""
        print(f"  [{step.id}] {step.kind:<6} {(step.file + ': ') if step.file and step.kind == 'edited' else ''}{text}")
    return 0


def _need_culprit(args) -> tuple[Case, Path, dict, Path] | None:
    case = Case.load(args.case)
    path = record_path(args)
    record = load_record(path)
    if not (record.get("lineup") or {}).get("culprit"):
        print(f"No culprit in {path} yet. Run `whodunit lineup {args.case}` first.")
        return None
    return case, Path(record["case"]["repo"]), record, path


def brief(args) -> int:
    """Motive, evidence and the root-cause brief for a case that has a culprit."""
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    culprit = record["lineup"]["culprit"]["sha"]
    found = find_motive(repo, culprit)
    evidence = briefs.gather(
        repo, case.id, culprit, case.target, record.get("replays", []), found,
        None if args.no_runs else neatroots(), order=[s["sha"] for s in record["suspects"]],
    )
    written = briefs.write_brief(evidence, case.symptom)
    record["motive"] = found.to_dict()
    record["evidence"] = asdict(evidence)
    record["brief"] = written
    save_record(path, record)
    print(written["headline"])
    print()
    for sentence in written["sentences"]:
        print(f"  {sentence['text']}  [{', '.join(sentence['cites'])}]")
    print()
    print(f"Written by: {written['model']}. Sentences cut for missing citations: {len(written.get('dropped', []))}.")
    for note in evidence.notes:
        print(f"Note: {note}")
    return 0


def ruling(args) -> int:
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    culprit = record["lineup"]["culprit"]
    diff = git(repo, "show", "--format=", culprit["sha"], "--", case.target)
    kind = rulings.classify(diff, culprit.get("files", []))
    request = (record.get("motive") or {}).get("request")
    try:
        decided, asked = rulings.decide(Path.cwd(), kind, case.id, culprit["sha"], culprit["subject"], request, answer=args.answer)
    except (ValueError, EOFError) as exc:
        print(f"No ruling recorded: {exc}")
        return 2
    record["ruling"] = {**asdict(decided), "asked_now": asked}
    save_record(path, record)
    print(f"Kind of change: {kind}. Ruling: {decided.ruling}." + ("" if asked else f" Decided on {decided.decided_on} in case {decided.first_case}, so nobody was asked again."))
    return 0


def _sides(record: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    """(failures, passes) the lineup saw before the culprit, and from it onward."""
    order = {s["sha"]: n for n, s in enumerate(record["suspects"])}
    at = order[record["lineup"]["culprit"]["sha"]]
    good, bad = [0, 0], [0, 0]
    for replay in record.get("replays", []):
        if replay["verdict"] in ("pass", "fail"):
            side = bad if order.get(replay["sha"], -1) >= at else good
            side[0 if replay["verdict"] == "fail" else 1] += 1
    return tuple(good), tuple(bad)


def fix(args) -> int:
    """Apply the ruling on a branch, replay until the evidence says fixed, and keep the case as a regression test."""
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    if not record.get("ruling"):
        print(f"No ruling yet. Run `whodunit ruling {args.case}` first.")
        return 2
    culprit = record["lineup"]["culprit"]["sha"]
    if record["ruling"]["ruling"] == rulings.REVERT:
        made = fixes.revert(repo, culprit, record["case"]["bad"], case.id)
    else:
        made = fixes.patch(repo, culprit, record["case"]["bad"], case.id, case.target, (record.get("motive") or {}).get("request"), record.get("brief"))
    record["fix"] = asdict(made)
    if made.commit is None:
        save_record(path, record)
        print(f"No fix was made. {made.note}")
        return 1
    print(f"{made.kind.capitalize()} committed as {made.commit[:12]} on branch {made.branch}. Replaying to check it.")
    good, bad = _sides(record)
    with Runner(repo, case, keep=args.keep) as runner:
        checked = fixes.verify(lambda: runner.trial(made.commit), good, bad, budget=args.budget, parallel=args.parallel)
    record["fix"]["verification"] = asdict(checked)
    if checked.fixed:
        kept = Path.cwd() / "cases" / f"{case.id}.toml"
        kept.parent.mkdir(exist_ok=True)
        text = Path(args.case).read_text().rstrip("\n")
        if "\nfixed = " not in text:
            # Top-level keys have to come before the first table in TOML, so the line goes at the top.
            text = f'# Closed by Whodunit. Replay with `whodunit check cases/{case.id}.toml`.\nfixed = "{made.commit}"\n' + text
        kept.write_text(text + "\n")
        record["fix"]["regression_case"] = str(kept)
    save_record(path, record)
    print(f"{checked.failures} failures in {checked.replays} replays of the fix. Probability it is fixed: {checked.probability:.1%}." + (f" {checked.note}." if checked.note else ""))
    if checked.fixed:
        print(f"Kept as a regression test: {record['fix']['regression_case']}")
        print(f"The branch {made.branch} is local. Pushing it and opening a pull request is the owner's call.")
    return 0 if checked.fixed else 1


def check(args) -> int:
    """Replay a kept case against a ref. This is the regression test."""
    case = Case.load(args.case)
    repo = Path(args.repo).resolve()
    with Runner(repo, case) as runner:
        verdicts = [runner.trial(args.ref) for _ in range(args.runs)]
    failures = verdicts.count("fail")
    print(f"{case.id} at {resolve(repo, args.ref)[:12]}: {failures} failures in {len(verdicts)} replays.")
    return 0 if failures == 0 and "skip" not in verdicts else 1


def damages(args) -> int:
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    try:
        counted = damage.count(neatroots(), args.workflow, since_ms=args.since_ms, case_id=case.id)
    except NeatError as exc:
        print(f"neatroots could not be asked: {exc}")
        return 1
    record["damages"] = counted.to_dict()
    save_record(path, record)
    print(f"{counted.bad_runs} of {counted.runs} {args.workflow} runs went bad ({counted.bad_share:.0%}), about ${counted.wasted_usd:.4f} of ${counted.cost_usd:.4f} spent.")
    print(f"The investigation itself used {counted.replay_runs} replays, about ${counted.replay_usd:.4f}. {counted.note}")
    return 0


def open_case(args) -> int:
    path = record_path(args)
    record = load_record(path)
    if not record:
        print("No cases yet. Lucky you." if not Path(args.case).is_file() else f"No record for this case yet. Run `whodunit lineup {args.case}` first.")
        return 2
    page = casefile.write(record, path.with_name(path.name.replace(".record.json", "") + ".casefile.html"))
    print(page)
    if not args.no_open:
        import webbrowser

        webbrowser.open(page.resolve().as_uri())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whodunit", description="Find the commit that broke an AI agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("lineup", help="replay a case against the suspect commits and name the culprit")
    p.add_argument("case", help="path to a case file (TOML)")
    p.add_argument("--repo", default=".", help="the git repo that holds the agent (default: here)")
    p.add_argument("--method", choices=("statistical", "plain"), default="statistical", help="plain is for bugs that fail every time")
    p.add_argument("--budget", type=int, default=120, help="most replays the statistical bisect may spend (default 120)")
    p.add_argument("--confidence", type=float, default=0.95, help="posterior needed to name a culprit (default 0.95)")
    p.add_argument("--parallel", type=int, default=1, help="replays to run at once")
    p.add_argument("--no-priors", action="store_true", help="suspect every commit equally, even ones that never touched the agent")
    p.add_argument("--record", help="where to write the case record (default: next to the case file)")
    p.add_argument("--keep", action="store_true", help="leave the worktrees in .whodunit/worktrees")
    p.add_argument("--json", action="store_true", help="print the result as JSON on stdout")
    p.set_defaults(func=lineup)
    for name, func, text in (
        ("brief", brief, "write the root-cause brief for a case that has a culprit"),
        ("ruling", ruling, "ask the owner once per kind of change: revert, or keep the intent and patch"),
        ("fix", fix, "apply the ruling on a branch and replay until the fix is proven"),
        ("damages", damages, "count the bad runs and what they cost"),
    ):
        p = commands.add_parser(name, help=text)
        p.add_argument("case", help="path to the case file")
        p.add_argument("--record", help="the case record (default: next to the case file)")
        p.set_defaults(func=func)
        if name == "brief":
            p.add_argument("--no-runs", action="store_true", help="do not ask neatroots for a failing and a passing run")
        if name == "ruling":
            p.add_argument("--answer", choices=("revert", "patch"), help="give the ruling here instead of being asked")
        if name == "fix":
            p.add_argument("--budget", type=int, default=60)
            p.add_argument("--parallel", type=int, default=1)
            p.add_argument("--keep", action="store_true")
        if name == "damages":
            p.add_argument("--workflow", default="refund-agent")
            p.add_argument("--since-ms", type=float, help="count runs from this time, in ms since the epoch")
    p = commands.add_parser("open-case", help="write the case file page and open it")
    p.add_argument("case")
    p.add_argument("--record")
    p.add_argument("--no-open", action="store_true", help="write the page without opening a browser")
    p.set_defaults(func=open_case)
    p = commands.add_parser("check", help="replay a kept case against a ref, as a regression test")
    p.add_argument("case")
    p.add_argument("--repo", default=".")
    p.add_argument("--ref", default="HEAD")
    p.add_argument("--runs", type=int, default=5)
    p.set_defaults(func=check)
    p = commands.add_parser("motive", help="show what a commit was asked to do, from its Entire checkpoint")
    p.add_argument("commit", help="commit SHA or ref")
    p.add_argument("--repo", default=".")
    p.add_argument("--steps", type=int, default=12, help="how many of the agent's steps to print")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=motive)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

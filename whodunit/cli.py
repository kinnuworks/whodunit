"""The whodunit command."""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields
from pathlib import Path

from .case import Case
from . import brief as briefs
from . import casefile
from . import damages as damage
from . import fix as fixes
from . import ruling as rulings
from .motive import find_motive
from .neat import NeatError, neatroots
from .onset import cloud_trend, find_onset, traffic, witness
from .lineup import linear_scan_cost, plain_bisect, statistical_bisect
from .replay import FAIL, PASS, Replay, Runner
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
    for _ in range(max(1, args.repeats)):  # a bad ref that fails only sometimes gets the same number of chances
        verdict, results = runner.test_commit(case.bad)
        if verdict != PASS:
            break
    say(f"  first bad  {suspects[-1].short}  {verdict}  {results[-1].reason}")
    if verdict != FAIL:
        say("The bad ref does not fail, so there is nothing to find.")
        return None

    def test(index: int) -> str:
        # With --repeats, a commit is called good only after passing that many times over.
        for _ in range(max(1, args.repeats)):
            verdict, results = runner.test_commit(suspects[index].sha)
            if verdict != PASS:
                break
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
    evidence = []
    if args.resume:
        # Carry on from the replays an earlier run of this case already paid for.
        position = {s.sha: n for n, s in enumerate(suspects)}
        position[resolve(runner.repo, case.good)] = -1
        runner.replays.extend(Replay(**r) for r in load_record(record_path(args)).get("replays", []) if r["sha"] in position)
        evidence = [(position[r.sha], r.verdict == FAIL) for r in runner.replays if r.verdict != "skip"]
        say(f"Resuming with {len(evidence)} replays already on record.")
    if getattr(args, "from_traffic", None):
        # Ordinary runs that asked what this case asks are evidence that is already paid for.
        position = {s.sha: n for n, s in enumerate(suspects)}
        position[resolve(runner.repo, case.good)] = -1
        try:
            seen = witness(neatroots(), args.from_traffic, position, [(i.text, i.expect.get("refunds", [])) for i in case.inputs])
        except NeatError as exc:
            seen = []
            say(f"neatroots could not be asked for traffic: {exc}")
        evidence += seen
        runner.witnessed = seen
        if seen:
            at = sorted({p for p, _ in seen})
            say(f"Traffic: {len(seen)} ordinary runs across {len(at)} of these commits had already asked this, and {sum(f for _, f in seen)} of them went wrong.")
    say(f"Statistical bisect, at most {args.budget} replays, {args.parallel} at a time. F is a failed replay, a dot is a pass.")
    return statistical_bisect(
        len(suspects), trial, args.budget, priors=priors, confidence=args.confidence, parallel=args.parallel, on_round=on_round,
        evidence=evidence,
    )


def lineup(args) -> int:
    case = Case.load(args.case)
    repo = Path(args.repo).resolve()
    suspects = list_suspects(repo, case.good, case.bad, case.target, graph=not getattr(args, "no_graph", False))
    if not suspects:
        print(f"No commits between {case.good} and {case.bad}. Nothing to investigate.")
        return 2
    say = print if not args.json else (lambda *a, **k: print(*a, **k, file=sys.stderr))
    say(f"Case {case.id}: {case.symptom}")
    say(f"Suspects: {len(suspects)}, of which {sum(s.touches_target for s in suspects)} touched {case.target}.")
    with_alibi = [s for s in suspects if s.alibi]
    if with_alibi:
        say(f"Alibis: {len(with_alibi)} of them start with less suspicion, for example {with_alibi[0].short} ({with_alibi[0].alibi}).")

    with Runner(repo, case, keep=args.keep) as runner:
        found = _plain(args, case, repo, suspects, runner, say) if args.method == "plain" else _statistical(args, case, suspects, runner, say)
        replays = sum(r.verdict != "skip" for r in runner.replays)
        seconds = sum(r.seconds for r in runner.replays)
        commits = len({r.sha for r in runner.replays})
        every_replay = [asdict(r) for r in runner.replays]
        witnessed = getattr(runner, "witnessed", [])
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
    record["case"] = {"id": case.id, "symptom": case.symptom, "good": resolve(repo, case.good), "bad": resolve(repo, case.bad), "target": case.target, "file": os.path.relpath(Path(args.case).resolve()), "repo": os.path.relpath(repo)}
    record["suspects"] = [
        {"sha": s.sha, "subject": s.subject, "checkpoint": s.checkpoint, "touches_target": s.touches_target, "alibi": s.alibi,
         **({"probability": round(found.posterior[i], 5)} if found.posterior else {})}
        for i, s in enumerate(suspects)
    ]
    if witnessed:
        report["traffic_runs"] = len(witnessed)
        report["traffic_failures"] = sum(failed for _, failed in witnessed)
        # Which commit each ordinary run was on, so later steps can say how they fall around the culprit.
        record["witnessed"] = [{"sha": record["case"]["good"] if position < 0 else suspects[position].sha, "failed": bool(failed)} for position, failed in witnessed]
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
    if getattr(args, "from_record", False):
        # Write the brief again from the evidence already collected. Nothing is asked of neatroots and nothing is replayed.
        if not record.get("evidence"):
            print(f"No evidence in {path} yet. Run `whodunit brief {args.case}` without --from-record first.")
            return 2
        known = {f.name for f in fields(briefs.Evidence)}
        evidence = briefs.Evidence(**{k: v for k, v in record["evidence"].items() if k in known})
        evidence.measured, evidence.rate_from = _measured(record)
        written = briefs.write_brief(evidence, case.symptom)
        record["evidence"], record["brief"] = asdict(evidence), written
        save_record(path, record)
        _print_brief(written, evidence)
        return 0
    found = find_motive(repo, culprit)
    evidence = briefs.gather(
        repo, case.id, culprit, case.target, record.get("replays", []), found,
        None if args.no_runs else neatroots(), order=[s["sha"] for s in record["suspects"]],
    )
    if evidence.failing_run is None and not args.no_runs:
        # No failing run could be tied to a replay on record. Make a few more, tagged one by one.
        with Runner(repo, case) as runner:
            parent = evidence.parent
            for batch in range(6):
                with ThreadPoolExecutor(max_workers=3) as pool:
                    verdicts = list(pool.map(lambda _: runner.trial(culprit), range(3)))
                if FAIL in verdicts:
                    break
            for _ in range(3):
                if runner.trial(parent) == PASS:
                    break
            record.setdefault("replays", []).extend(asdict(r) for r in runner.replays)
        order = [s["sha"] for s in record["suspects"]]
        evidence = briefs.gather(repo, case.id, culprit, case.target, record["replays"], found, neatroots(), order=order)
    evidence.measured, evidence.rate_from = _measured(record)
    written = briefs.write_brief(evidence, case.symptom)
    record["motive"] = found.to_dict()
    record["evidence"] = asdict(evidence)
    record["brief"] = written
    save_record(path, record)
    _print_brief(written, evidence)
    return 0


def _measured(record: dict) -> tuple[str, float | None]:
    """What the lineup measured, in words for the brief, and the failure rate from the culprit on."""
    report = record["lineup"]
    if "failure_rate_from" not in report:
        return "", None
    (good_f, good_p), (bad_f, bad_p) = _sides(record)
    text = (f"{report['replays']} replays across {report['commits_tested']} commits. From the culprit on, {bad_f} of {bad_f + bad_p} replays failed. "
            f"Before it, {good_f} of {good_f + good_p} replays failed.")
    seen = record.get("witnessed") or []
    order = {s["sha"]: n for n, s in enumerate(record["suspects"])}
    at = order[report["culprit"]["sha"]]
    if seen:
        after = [w["failed"] for w in seen if order.get(w["sha"], -1) >= at]
        before = [w["failed"] for w in seen if order.get(w["sha"], -1) < at]
        text += (f" Ordinary runs that asked the same thing were counted as well: {sum(after)} of {len(after)} runs went wrong from the culprit on, "
                 f"and {sum(before)} of {len(before)} runs before it. Replays and ordinary runs together: {bad_f + sum(after)} of {bad_f + bad_p + len(after)} "
                 f"went wrong from the culprit on, and {good_f + sum(before)} of {good_f + good_p + len(before)} before it.")
    elif report.get("traffic_runs"):
        text += (f" {report['traffic_runs']} ordinary runs that asked the same thing, on commits across the range, were counted as well, "
                 f"and {report['traffic_failures']} of them went wrong.")
    text += f" The estimated failure rate is {report['failure_rate_from']:.0%} from the culprit on and {report['failure_rate_before']:.0%} before it."
    if bad_p == 0 and not any(not w["failed"] for w in seen if order.get(w["sha"], -1) >= at):
        # Nothing passed on the bad side. The estimate still sits under 100%, and a brief should not read a pass into that.
        text += (f" No run from the culprit on has been seen to pass. The estimate is below 100% only because {bad_f + bad_p} replays are too few to rule a pass out, "
                 "so say that it failed in all of them and leave it there.")
    return text, report["failure_rate_from"]


def _print_brief(written: dict, evidence) -> None:
    print(written["headline"])
    print()
    for sentence in written["sentences"]:
        print(f"  {sentence['text']}  [{', '.join(sentence['cites'])}]")
    print()
    for objection in written.get("rejected") or []:
        print(f"A first draft was sent back: \"{objection['text']}\" {objection['problem']}.")
    print(f"Written by: {written['model']}. Sentences cut by the rule checks: {len(written.get('dropped', []))}.")
    for note in evidence.notes:
        print(f"Note: {note}")


def ruling(args) -> int:
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    culprit = record["lineup"]["culprit"]
    diff = git(repo, "show", "--format=", culprit["sha"], "--", case.target)
    kind = rulings.classify(diff, culprit.get("files", []))
    request = (record.get("motive") or {}).get("request")
    if args.answer is None and rulings.recall(Path.cwd(), kind) is None and not sys.stdin.isatty():
        # Nobody is at the keyboard. Put the question on the page and stop.
        print(rulings.question(kind, culprit["subject"], request))
        record["ruling_question"] = {"kind": kind, "question": rulings.question(kind, culprit["subject"], request)}
        save_record(path, record)
        return 2
    try:
        decided, asked = rulings.decide(Path.cwd(), kind, case.id, culprit["sha"], culprit["subject"], request, answer=args.answer)
    except (ValueError, EOFError, OSError) as exc:
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


def _attempt(kind: str, case, repo: Path, record: dict, args, feedback: str = "") -> dict:
    """Make one fix and replay it. Returns what was tried and how it went."""
    culprit = record["lineup"]["culprit"]["sha"]
    if kind == rulings.REVERT:
        made = fixes.revert(repo, culprit, record["case"]["bad"], case.id)
    else:
        made = fixes.patch(repo, culprit, record["case"]["bad"], case.id, case.target, (record.get("motive") or {}).get("request"), record.get("brief"), feedback)
    attempt = asdict(made)
    if made.commit is None:
        print(f"  {kind}: no fix was made. {made.note}")
        return attempt
    print(f"  {kind}: committed as {made.commit[:12]} on branch {made.branch}. Replaying to check it.")
    good, bad = _sides(record)
    with Runner(repo, case, keep=getattr(args, "keep", False)) as runner:
        checked = fixes.verify(lambda: runner.trial(made.commit), good, bad, budget=args.fix_budget, parallel=args.parallel)
        attempt["failed_replays"] = [f"{r.input} -> {r.reason}" for r in runner.replays if r.verdict == FAIL][:4]
    attempt["verification"] = asdict(checked)
    attempt["diff"] = git(repo, "show", "--format=", made.commit)[:4000]
    print(f"  {kind}: {checked.failures} failures in {checked.replays} replays. Probability the failure rate is back to where it was: {checked.probability:.1%}." + (f" Not proven: {checked.note}." if checked.note else ""))
    return attempt


def _proven(attempt: dict) -> bool:
    return bool((attempt.get("verification") or {}).get("fixed"))


def fix(args) -> int:
    """Apply the ruling on a branch and replay until the evidence says fixed. If it is not, try again.

    A patch that is not proven gets one more try, with the first patch and its failing replays
    in front of the model. If that is not proven either, the culprit is reverted, which is the
    safe answer and loses what the commit was for. Every try is kept in the record.
    """
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    if not record.get("ruling"):
        print(f"No ruling yet. Run `whodunit ruling {args.case}` first.")
        return 2
    wanted = record["ruling"]["ruling"]
    attempts = [_attempt(wanted, case, repo, record, args)]
    if wanted == rulings.PATCH and not _proven(attempts[-1]):
        first = attempts[-1]
        feedback = (first.get("note") or "") + "\nThe first patch:\n" + first.get("diff", "none was made") + "\nReplays of it that still failed:\n" + "\n".join(first.get("failed_replays", []) or ["none recorded"])
        print("  The patch is not proven. Trying once more, with the first patch and its failures in view.")
        attempts.append(_attempt(rulings.PATCH, case, repo, record, args, feedback))
    if wanted == rulings.PATCH and not _proven(attempts[-1]):
        print("  Still not proven. Falling back to a revert, which loses what the commit was for.")
        attempts.append(_attempt(rulings.REVERT, case, repo, record, args))
        attempts[-1]["note"] = ((attempts[-1].get("note") or "") + " This is a fallback: the ruling was to patch, and two patches were not proven.").strip()
    final = next((a for a in reversed(attempts) if _proven(a)), attempts[-1])
    record["fix"] = final
    record["attempts"] = attempts
    if _proven(final):
        kept = Path.cwd() / "cases" / f"{case.id}.toml"
        kept.parent.mkdir(exist_ok=True)
        text = Path(args.case).read_text().rstrip("\n")
        if "\nfixed = " in "\n" + text:
            text = "\n".join(line for line in text.splitlines() if not line.startswith(("fixed = ", "# Closed by Whodunit")))
        # Top-level keys have to come before the first table in TOML, so the line goes at the top.
        text = f'# Closed by Whodunit. Replay with `whodunit check cases/{case.id}.toml`.\nfixed = "{final["commit"]}"\n' + text
        kept.write_text(text + "\n")
        record["fix"]["regression_case"] = os.path.relpath(kept)
    save_record(path, record)
    if _proven(final):
        print(f"Fixed by {final['kind']} {final['commit'][:12]} after {len(attempts)} {'try' if len(attempts) == 1 else 'tries'}. Kept as a regression test: {record['fix']['regression_case']}")
        print(f"The branch {final['branch']} is local. Pushing it and opening a pull request is the owner's call.")
    else:
        print(f"Not fixed after {len(attempts)} {'try' if len(attempts) == 1 else 'tries'}. The record has each one.")
    return 0 if _proven(final) else 1


def investigate(args) -> int:
    """Run a whole case: lineup, motive and brief, ruling, fix, damages, case file. Stops only for the owner's ruling."""
    import time

    path = record_path(args)

    def note(step: str, outcome: str) -> None:
        record = load_record(path)
        record.setdefault("log", []).append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "step": step, "outcome": outcome})
        save_record(path, record)
        print(f"[{step}] {outcome}")

    def finish(code: int) -> int:
        open_case(argparse.Namespace(case=args.case, record=args.record, no_open=True))
        return code

    if getattr(args, "fresh", False) and path.is_file():
        path.rename(path.with_name(path.name + time.strftime(".%H%M%S.old")))
    record = load_record(path)
    args.method, args.confidence, args.no_priors, args.keep, args.json = "statistical", 0.95, False, False, False
    args.repeats = 1
    args.no_runs, args.from_record, args.since_ms = False, False, None
    if not (record.get("lineup") or {}).get("culprit"):
        args.resume = bool(record.get("replays"))
        code = lineup(args)
        if code == 1:
            note("lineup", f"Nobody could be named inside {args.budget} replays. Carrying on from those replays with {args.budget} more.")
            args.resume = True
            code = lineup(args)
        if code != 0:
            note("lineup", "No culprit named. The case file lists the suspects that remain." if code == 1 else "The case could not be run: its good ref fails or its bad ref passes.")
            return finish(1)
        found = load_record(path)["lineup"]
        note("lineup", f"Named {found['culprit']['sha'][:12]} ({found['culprit']['subject']}) after {found['replays']} replays across {found['commits_tested']} commits.")
    else:
        note("lineup", f"Already named: {record['lineup']['culprit']['sha'][:12]}.")
    if not load_record(path).get("brief") or args.redo_brief:
        brief(args)
        written = load_record(path)
        note("brief", f"Written by {written['brief']['model']}. Motive: {'on record' if written['motive'].get('request') else written['motive'].get('note') or 'none'}")
    code = ruling(args)
    if code != 0:
        note("ruling", "Waiting for the owner. Give it with `whodunit ruling <case> --answer revert` or `--answer patch`, then run investigate again.")
        return finish(3)
    decided = load_record(path)["ruling"]
    note("ruling", f"{decided['ruling']} for a {decided['kind']} change" + ("" if decided.get("asked_now") else ", from the standing rule"))
    code = fix(args)
    done = load_record(path)
    tries = done.get("attempts", [])
    note("fix", (f"Proven with a {done['fix']['kind']} after {len(tries)} {'try' if len(tries) == 1 else 'tries'}." if code == 0 else f"Not proven after {len(tries)} tries."))
    damages(args)
    return finish(code)


def check(args) -> int:
    """Replay a kept case against a ref. This is the regression test."""
    import time

    case = Case.load(args.case)
    repo = Path(args.repo).resolve()
    ref = args.ref or case.fixed or "HEAD"
    with Runner(repo, case) as runner:
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
            verdicts = list(pool.map(lambda _: runner.trial(ref), range(args.runs)))
    failures = verdicts.count(FAIL)
    sha = resolve(repo, ref)
    print(f"{case.id} at {sha[:12]}: {failures} failures in {len(verdicts)} replays.")
    path = record_path(args)
    record = load_record(path)
    if record:
        record.setdefault("checks", []).append({"at": time.strftime("%Y-%m-%d %H:%M"), "ref": sha, "runs": len(verdicts), "failures": failures})
        save_record(path, record)
    return 0 if failures == 0 and "skip" not in verdicts else 1


def damages(args) -> int:
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    try:
        order = [s["sha"] for s in record["suspects"]]
        since_culprit = order[order.index(record["lineup"]["culprit"]["sha"]):]
        counted = damage.count(neatroots(), args.workflow, commits=since_culprit, since_ms=args.since_ms, case_id=case.id)
        counted = damage.count_case(neatroots(), counted, args.workflow, since_culprit, [(i.text, i.expect.get("refunds", [])) for i in case.inputs])
    except NeatError as exc:
        print(f"neatroots could not be asked: {exc}")
        return 1
    record["damages"] = counted.to_dict()
    save_record(path, record)
    if counted.runs:
        print(f"{counted.bad_runs} of {counted.runs} {args.workflow} runs on the culprit or later went bad ({counted.bad_share:.0%}), about ${counted.wasted_usd:.4f} of ${counted.cost_usd:.4f} spent.")
    else:
        print("No ordinary runs are recorded on the culprit or the commits after it, so there is no damage to count.")
    if counted.case_runs:
        print(f"Of {counted.case_runs} ordinary runs that asked what this case asks, {counted.case_bad} paid out wrongly: "
              f"{counted.wrongly_paid:.2f} refunded that should not have been, and {counted.withheld:.2f} owed and not refunded.")
    print(f"The investigation itself used {counted.replay_runs} replays, about ${counted.replay_usd:.4f}. {counted.note}")
    return 0


def onset(args) -> int:
    """Where the failures begin, from the agent's ordinary runs in neatroots."""
    try:
        runs = traffic(neatroots(), args.workflow)
    except NeatError as exc:
        print(f"neatroots could not be asked: {exc}")
        return 1
    found = find_onset(args.workflow, runs)
    if args.cloud:
        try:
            trend = cloud_trend(args.cloud)
            print(f"neatlogs cloud, detection \"{trend['detection']}\": {trend['total']} occurrences, first seen {trend['first_seen'] or 'never in this period'}.")
        except (NeatError, RuntimeError) as exc:
            print(f"neatlogs cloud could not be asked: {exc}")
    if args.json:
        print(json.dumps(found.to_dict(), indent=2))
        return 0 if found.good else 1
    print(f"{found.bad_runs} of {found.runs} {args.workflow} runs went bad, across {len(found.commits)} commits.")
    if found.note:
        print(found.note)
        return 1
    from datetime import datetime, timezone

    when = datetime.fromtimestamp(found.first_failure_ms / 1000, timezone.utc).strftime("%d %B %H:%M UTC") if found.first_failure_ms else "unknown"
    between = [c["sha"] for c in found.commits]
    print(f"The failures begin around {when}.")
    print(f"Last good ref: {found.good[:12]}. First bad ref: {found.bad[:12]}. That leaves {len(between) - 1 - between.index(found.good)} suspects seen in traffic.")
    print(f"From traffic alone the likeliest culprit is {found.likeliest[:12]}, at {found.probability:.0%}.")
    for text in found.failing_inputs:
        print(f"  failing input: {text}")
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


def casebook(args) -> int:
    """Write every case file in a folder, and an index page that lists them."""
    folder = Path(args.folder)
    records = []
    for path in sorted(folder.glob("*.record.json")):
        record = load_record(path)
        page = casefile.write(record, path.with_name(path.name.replace(".record.json", "") + ".casefile.html"))
        records.append((page.name, record))
    records.sort(key=lambda item: -len(item[1].get("suspects", [])))
    index = folder / "index.html"
    index.write_text(casefile.render_index(records))
    print(f"{index}: {len(records)} cases")
    if args.open:
        import webbrowser

        webbrowser.open(index.resolve().as_uri())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whodunit", description="Find the commit that broke an AI agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("lineup", help="replay a case against the suspect commits and name the culprit")
    p.add_argument("case", help="path to a case file (TOML)")
    p.add_argument("--repo", default=".", help="the git repo that holds the agent (default: here)")
    p.add_argument("--method", choices=("statistical", "plain"), default="statistical", help="plain is for bugs that fail every time")
    p.add_argument("--repeats", type=int, default=1, help="with --method plain, how many times a commit must pass all inputs to be called good")
    p.add_argument("--budget", type=int, default=120, help="most replays the statistical bisect may spend (default 120)")
    p.add_argument("--confidence", type=float, default=0.95, help="posterior needed to name a culprit (default 0.95)")
    p.add_argument("--parallel", type=int, default=1, help="replays to run at once")
    p.add_argument("--resume", action="store_true", help="start from the replays already in the case record; --budget is then how many more to spend")
    p.add_argument("--from-traffic", metavar="WORKFLOW", help="start from ordinary runs of this workflow that already asked what the case asks")
    p.add_argument("--no-graph", action="store_true", help="do not ask entire-graph which commits could reach the agent")
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
            p.add_argument("--from-record", action="store_true", help="write the brief again from the evidence already in the record")
        if name == "ruling":
            p.add_argument("--answer", choices=("revert", "patch"), help="give the ruling here instead of being asked")
        if name == "fix":
            p.add_argument("--fix-budget", type=int, default=90, help="most replays to spend checking one fix")
            p.add_argument("--parallel", type=int, default=1)
            p.add_argument("--keep", action="store_true")
        if name == "damages":
            p.add_argument("--workflow", default="refund-agent")
            p.add_argument("--since-ms", type=float, help="count runs from this time, in ms since the epoch")
    p = commands.add_parser("investigate", help="run a whole case from lineup to case file, stopping only for the owner's ruling")
    p.add_argument("case", help="path to the case file")
    p.add_argument("--repo", default=".")
    p.add_argument("--record")
    p.add_argument("--budget", type=int, default=120, help="replays the lineup may spend before it stops to think again")
    p.add_argument("--fix-budget", type=int, default=90, help="most replays to spend checking one fix")
    p.add_argument("--parallel", type=int, default=3)
    p.add_argument("--answer", choices=("revert", "patch"), help="the owner's ruling, if there is no standing rule yet")
    p.add_argument("--workflow", default="refund-agent")
    p.add_argument("--redo-brief", action="store_true")
    p.add_argument("--fresh", action="store_true", help="set aside any earlier record for this case and start over")
    p.add_argument("--from-traffic", metavar="WORKFLOW", help="start the lineup from ordinary runs of this workflow")
    p.add_argument("--no-graph", action="store_true")
    p.set_defaults(func=investigate)
    p = commands.add_parser("casebook", help="write every case file in a folder and an index page")
    p.add_argument("folder", nargs="?", default="cases")
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=casebook)
    p = commands.add_parser("onset", help="find when the failures began and between which commits, from ordinary runs")
    p.add_argument("--workflow", default="refund-agent")
    p.add_argument("--cloud", metavar="DETECTION", help="also ask neatlogs cloud when this detection started firing")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=onset)
    p = commands.add_parser("open-case", help="write the case file page and open it")
    p.add_argument("case")
    p.add_argument("--record")
    p.add_argument("--no-open", action="store_true", help="write the page without opening a browser")
    p.set_defaults(func=open_case)
    p = commands.add_parser("check", help="replay a kept case against a ref, as a regression test")
    p.add_argument("case")
    p.add_argument("--repo", default=".")
    p.add_argument("--ref", help="the commit to replay against (default: the case's fix, or HEAD if it has none)")
    p.add_argument("--runs", type=int, default=6)
    p.add_argument("--parallel", type=int, default=3)
    p.add_argument("--record")
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

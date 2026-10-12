"""The whodunit command."""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields
from pathlib import Path

from .case import Case, CaseInput
from . import brief as briefs
from . import casefile
from . import damages as damage
from . import fix as fixes
from . import opening
from . import ruling as rulings
from .motive import checkpoint_link, find_motive
from .neat import NeatError, forward_to_cloud, neatroots
from .onset import cloud_trend, environment_then, find_onset, traffic, what_differs, witness
from .lineup import ChangePoint, linear_scan_cost, plain_bisect, statistical_bisect
from .replay import FAIL, PASS, VOID, Replay, Runner
from .suspects import git, list_suspects, resolve
from .trace import OFF, Trace


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


def ablation_path(record_file: Path) -> Path:
    """Where a case keeps the result of a lineup run with its head start taken away: next to the record."""
    return record_file.with_name(record_file.name.replace(".record.json", "") + ".ablation.json")


def for_page(record: dict, record_file: Path) -> dict:
    """The record as the page needs it, with two things added that are looked up fresh and never saved.

    One is the ablation run, if there is one on disk. The other is the link to the culprit's
    Entire checkpoint, which depends on the repo's remote and so can change after the record
    was written.
    """
    shown = dict(record)
    path = ablation_path(record_file)
    if path.is_file():
        shown["ablation"] = json.loads(path.read_text())
    # A case's number is its place among the cases in its folder, by when each was opened.
    opened = {}
    for other in record_file.parent.glob("*.record.json"):
        try:
            starts = [r["started"] for r in json.loads(other.read_text()).get("replays", []) if r.get("started")]
        except (OSError, json.JSONDecodeError):
            continue
        opened[other.resolve()] = min(starts) if starts else float("inf")
    if record_file.resolve() in opened and record.get("case"):
        order = sorted(opened, key=lambda found: (opened[found], found.name))
        shown["case"] = {**record["case"], "number": order.index(record_file.resolve()) + 1}
    motive = record.get("motive") or {}
    if motive.get("checkpoint") and motive.get("sha"):
        repo = Path((record.get("case") or {}).get("repo") or ".")
        shown["motive"] = {**motive, "link": checkpoint_link(repo if repo.is_dir() else Path.cwd(), motive["sha"])}
    # A link to a trace in neatlogs cloud needs the address of the dashboard, which is the owner's to give:
    # NEATLOGS_TRACE_URL, with {trace_id} where the id goes. Without it the page prints the ids and no link.
    template = os.environ.get("NEATLOGS_TRACE_URL", "")
    if "{trace_id}" in template:
        traced = record.get("trace") or {}
        if traced.get("where") == "cloud" and traced.get("trace_id"):
            shown["trace"] = {**traced, "link": template.replace("{trace_id}", traced["trace_id"])}
        cloud = (record.get("evidence") or {}).get("cloud") or {}
        if cloud.get("sent"):
            shown["evidence"] = {**record["evidence"], "cloud": {**cloud, "links": {key: template.replace("{trace_id}", value) for key, value in cloud["trace_ids"].items()}}}
    return shown


def _now_ms() -> int:
    import time

    return round(time.time() * 1000)


def _replayed(record: dict, since_ms: int) -> None:
    """Note that one of this record's own steps was replaying from `since_ms` until now.

    The damages bill an investigation for the replays inside these stretches and no others. One
    stretch from the first replay to the last is not enough: an experiment run in between under
    the same case id would be billed to the case.
    """
    record["replays_until_ms"] = _now_ms()
    record.setdefault("replay_windows", []).append([since_ms - 2000, record["replays_until_ms"]])


def _plain(args, case, repo, suspects, runner, say):
    # Check the alibis first. If the good ref fails or the bad ref passes, the case is wrong.
    verdict, results = runner.test_commit(case.good)
    say(f"  last good  {resolve(repo, case.good)[:12]}  {verdict}  {results[-1].reason}")
    if verdict == VOID:
        say("The good ref could not be judged, because the model provider or the network kept failing.")
        return None
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

    good_sha = resolve(runner.repo, case.good)
    tracer = getattr(args, "tracer", OFF)
    runner.rounds = []  # what each round replayed and what the suspects looked like after it, kept in the record

    def on_round(positions: list[int], verdicts: list[str], posterior: list[float]) -> None:
        top = max(range(len(posterior)), key=posterior.__getitem__)
        for position in dict.fromkeys(positions):
            who = "last good " if position < 0 else f"suspect {position + 1:>2}"
            marks = "".join("F" if v == FAIL else "." if v == PASS else "v" if v == VOID else "s" for p, v in zip(positions, verdicts) if p == position)
            say(f"  {who}  {marks:<8}  top suspect {top + 1:>2} at {posterior[top]:5.1%}")
        ranked = sorted(range(len(posterior)), key=lambda i: -posterior[i])[:3]
        runner.rounds.append({
            "commits": [good_sha if p < 0 else suspects[p].sha for p in positions], "verdicts": list(verdicts),
            "top": [[suspects[i].sha, round(posterior[i], 4)] for i in ranked], "posterior": [round(share, 4) for share in posterior],
        })

    def around(positions: list[int], go) -> list[str]:
        # One span per round in the investigation's trace: what was replayed, how it came out, who leads now.
        seen: dict = {}
        replayed = [f"{'last good' if p < 0 else f'suspect {p + 1}'} ({(good_sha if p < 0 else suspects[p].sha)[:12]})" for p in positions]

        def work() -> dict:
            seen["verdicts"] = go()
            last = runner.rounds[-1]
            return {"verdicts": seen["verdicts"], "top_three": [{"commit": sha[:12], "probability": share} for sha, share in last["top"]]}
        tracer.step(f"lineup round {len(runner.rounds) + 1}", {"replayed": replayed}, work)
        return seen["verdicts"]

    priors = None if args.no_priors else [s.prior for s in suspects]
    evidence = []
    if args.resume:
        # Carry on from the replays an earlier run of this case already paid for.
        position = {s.sha: n for n, s in enumerate(suspects)}
        position[resolve(runner.repo, case.good)] = -1
        runner.replays.extend(Replay(**r) for r in load_record(record_path(args)).get("replays", []) if r["sha"] in position)
        evidence = [(position[r.sha], r.verdict == FAIL) for r in runner.replays if r.verdict in (PASS, FAIL)]  # a skipped or voided replay is not evidence
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
    say(f"Statistical bisect, at most {args.budget} replays, {args.parallel} at a time. F is a failed replay, a dot is a pass, and v was voided by a provider error.")
    return statistical_bisect(
        len(suspects), trial, args.budget, priors=priors, confidence=args.confidence, parallel=args.parallel, on_round=on_round,
        evidence=evidence, around=around,
    )


def _per_input(case, suspects, good_sha: str, replays: list[dict], priors) -> tuple[list[dict], dict | None]:
    """What each input says by itself about where the trouble starts, and whether two of them disagree.

    The lineup pools every input's replays, which is right when one commit broke them all. Two
    regressions in one range often break different inputs. So each input gets a change-point
    posterior of its own, from its own replays. If two inputs that both fail are 95% sure to
    have different first bad commits, the case is flagged: there may be two culprits here.
    """
    position = {s.sha: n for n, s in enumerate(suspects)} | {good_sha: -1}
    told, posteriors = [], {}
    for one in case.inputs:
        state = ChangePoint(len(suspects), priors)
        mine = [r for r in replays if r["input"] == one.text and r["verdict"] in (PASS, FAIL) and r["sha"] in position]
        for replay in mine:
            state.observe(position[replay["sha"]], replay["verdict"] == FAIL)
        failures = sum(r["verdict"] == FAIL for r in mine)
        entry = {"input": one.text, "replays": len(mine), "failures": failures, "top": None, "probability": None}
        if failures:
            posterior = state.posterior()
            top = max(range(len(posterior)), key=posterior.__getitem__)
            entry["top"], entry["probability"] = suspects[top].sha, round(posterior[top], 4)
            posteriors[one.text] = posterior
        told.append(entry)
    worst = None
    texts = list(posteriors)
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            same = sum(x * y for x, y in zip(posteriors[a], posteriors[b]))  # P(both inputs broke at the same commit)
            if same <= 0.05 and (worst is None or same < worst["same"]):
                tops = {entry["input"]: entry["top"] for entry in told}
                worst = {"same": round(same, 4), "inputs": [a, b], "commits": [tops[a], tops[b]]}
    return told, worst


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

    began = _now_ms()
    with Runner(repo, case, keep=args.keep) as runner:
        found = _plain(args, case, repo, suspects, runner, say) if args.method == "plain" else _statistical(args, case, suspects, runner, say)
        replays = sum(r.verdict in (PASS, FAIL) for r in runner.replays)
        voided = sum(r.voided for r in runner.replays)  # attempts thrown away because the provider or the network failed
        timed_out = sum(r.timeouts for r in runner.replays)
        seconds = sum(r.seconds for r in runner.replays)
        commits = len({r.sha for r in runner.replays})
        every_replay = [asdict(r) for r in runner.replays]
        witnessed = getattr(runner, "witnessed", [])
        rounds = getattr(runner, "rounds", [])
    if found is None:
        return 2
    differs: list[str] = []
    if found.clear:
        # Nobody in the range did it. Say what is different about today, as far as the runs themselves say.
        good_sha = resolve(repo, case.good)
        now = [{"model": r["model"], "lock": r["lock"]} for r in every_replay if r["sha"] == good_sha and r["verdict"] in (PASS, FAIL)]
        workflow = getattr(args, "from_traffic", None) or getattr(args, "workflow", None)
        try:
            then = environment_then(neatroots(), workflow, good_sha, [(i.text, i.expect.get("refunds", [])) for i in case.inputs]) if workflow else []
        except (NeatError, KeyError, TypeError) as exc:
            then = []
            differs.append(f"neatroots could not be asked for old runs of the good ref: {exc}")
        differs += what_differs(then, now)

    report = {
        "case": case.id,
        "method": args.method,
        "suspects": len(suspects),
        "commits_tested": commits,
        "replays": replays,
        "voided": voided,
        "timeouts": timed_out,
        "seconds": round(seconds, 1),
        "culprit": None,
        "remaining": [{"sha": suspects[i].sha, "subject": suspects[i].subject, **({"probability": round(found.posterior[i], 4)} if found.posterior else {})} for i in found.remaining],
    }
    if found.rates and not found.clear:
        report["failure_rate_before"], report["failure_rate_from"] = (round(r, 3) for r in found.rates)
    if args.method == "statistical":
        report["per_input"], split = _per_input(case, suspects, resolve(repo, case.good), every_replay, None if args.no_priors else [s.prior for s in suspects])
        if split:
            report["inputs_disagree"] = split
    say("")
    if found.clear:
        report["clear"], report["note"], report["differs"] = True, found.note, differs
        say("No commit did it. " + found.note[0].upper() + found.note[1:] + ".")
        say("Something outside these commits changed. What the runs say about that:")
        for line in differs:
            say(f"  {line}")
    elif found.culprit is not None:
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
        if voided or timed_out:
            say(f"Voided and run again: {voided} attempts that hit a provider or network error. Timed out: {timed_out}. A voided attempt is never evidence.")
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
    if getattr(args, "ablation", False):
        # A run with some of the head start taken away, to see what it was worth. The case record is left alone.
        without = (["alibis from entire-graph"] if args.no_graph else []) + (["any prior on the suspects"] if args.no_priors else []) + \
                  ([] if getattr(args, "from_traffic", None) else ["ordinary runs as evidence"])
        kept = {"case": case.id, "without": without, "runs": 1, "replays": replays, "commits_tested": commits,
                "culprit": report["culprit"] and report["culprit"]["sha"], "probability": report["culprit"] and report["culprit"].get("probability")}
        ablation_path(record_path(args)).write_text(json.dumps(kept, indent=1) + "\n")
        say(f"Ablation: {ablation_path(record_path(args))}")
        return 0 if found.culprit is not None else 1
    if report.get("inputs_disagree"):
        split = report["inputs_disagree"]
        say(f"Careful: the inputs point at different commits. \"{split['inputs'][0]}\" points at {split['commits'][0][:12]} and \"{split['inputs'][1]}\" at {split['commits'][1][:12]}.")
        say("There may be two regressions in this range. A single culprit, if one was named, is at most one of them.")
    record = load_record(record_path(args))
    record["case"] = {"id": case.id, "symptom": case.symptom, "good": resolve(repo, case.good), "bad": resolve(repo, case.bad), "target": case.target, "file": os.path.relpath(Path(args.case).resolve()), "repo": os.path.relpath(repo),
                      "traffic_sent_by": case.traffic_sent_by}
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
    # A resumed lineup adds its rounds to the ones the earlier run made.
    record["rounds"] = (record.get("rounds", []) if getattr(args, "resume", False) else []) + rounds
    _replayed(record, began)
    save_record(record_path(args), record)
    say(f"Record: {record_path(args)}")
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if found.culprit is not None else 4 if found.clear else 1  # 4: the range is clear, and no amount of replaying will name anyone


def motive(args) -> int:
    if getattr(args, "case", None):
        # Look the motive up again for a case's culprit and put it in the record. Nothing is replayed and no model is asked.
        loaded = _need_culprit(args)
        if loaded is None:
            return 2
        _, repo, record, path = loaded
        found = find_motive(repo, record["lineup"]["culprit"]["sha"])
        changed = (record.get("motive") or {}).get("request") != found.request
        record["motive"] = found.to_dict()
        save_record(path, record)
        if changed and record.get("brief"):
            print("The request on record has changed. The brief was written from the old one, so write it again with `whodunit brief`.")
    else:
        if not args.commit:
            print("Give a commit, or --case <case file> to refresh the motive in a case record.")
            return 2
        found = find_motive(Path(args.repo).resolve(), args.commit)
    if args.json:
        print(json.dumps(found.to_dict(), indent=2))
        return 0 if found.request else 1
    print(f"Commit {found.sha[:12]}  {found.subject}")
    link = checkpoint_link(Path(args.repo).resolve(), found.sha) if found.checkpoint else None
    print(f"Checkpoint: {found.checkpoint or 'none'}" + (f"  {link}" if link else ""))
    if found.note:
        print(found.note)
    if not found.request:
        return 1
    print(f"Asked of the coding agent at {found.request_time}:")
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
    print()
    print("The quote was checked against the transcript." if found.quote_checked else "The quote is not word for word in the transcript, so the page will not say it was checked.")
    traced = found.provenance
    if traced.get("lines"):
        print(f"entire why puts {traced['agree']} of {traced['lines']} changed lines behind this commit and checkpoint."
              + ("" if traced.get("request_agrees") is not False else " The request it holds for them is a different one."))
    elif traced.get("note"):
        print(traced["note"])
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
    tracer = getattr(args, "tracer", OFF)
    seen: dict = {}

    def look_up() -> dict:
        seen["motive"] = find_motive(repo, culprit)
        told = seen["motive"]
        return {"checkpoint": told.checkpoint, "request": (told.request or "")[:300], "note": told.note}
    tracer.step("motive", {"commit": culprit[:12]}, look_up)
    found = seen["motive"]
    evidence = briefs.gather(
        repo, case.id, culprit, case.target, record.get("replays", []), found,
        None if args.no_runs else neatroots(), order=[s["sha"] for s in record["suspects"]],
    )
    if evidence.failing_run is None and not args.no_runs:
        # No failing run could be tied to a replay on record. Make a few more, tagged one by one.
        began = _now_ms()
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
        _replayed(record, began)
        order = [s["sha"] for s in record["suspects"]]
        evidence = briefs.gather(repo, case.id, culprit, case.target, record["replays"], found, neatroots(), order=order)
    evidence.measured, evidence.rate_from = _measured(record)

    def write() -> dict:
        seen["brief"] = briefs.write_brief(evidence, case.symptom)
        made = seen["brief"]
        return {"headline": made["headline"], "sentences_kept": len(made["sentences"]), "sentences_cut": len(made.get("dropped", [])),
                "first_draft_sent_back": bool(made.get("rejected")), "written_by": made.get("writer")}
    tracer.step("brief", {"failing_run": (evidence.failing_run or {}).get("trace_id", "")[:12], "passing_run": (evidence.passing_run or {}).get("trace_id", "")[:12],
                          "measured": evidence.measured}, write)
    written = seen["brief"]
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
    how = "Written by a model" if written.get("writer") == "model" else "Written from the fixed template" + (f", because {written['why']}" if written.get("why") else "")
    print(f"{how}. Sentences cut by the rule checks: {len(written.get('dropped', []))}.")
    for note in evidence.notes:
        print(f"Note: {note}")


def forward(args) -> int:
    """Send the case's failing run and passing run from neatroots to neatlogs cloud, and note it in the record."""
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    evidence = record.get("evidence") or {}
    runs = {key: evidence[key]["trace_id"] for key in ("failing_run", "passing_run") if evidence.get(key)}
    if not runs:
        print("The record has no failing or passing run to send. Run `whodunit brief` first.")
        return 2
    sent, said = forward_to_cloud(list(runs.values()))
    evidence["cloud"] = {"sent": sent, "trace_ids": runs if sent else {}, "note": said}
    record["evidence"] = evidence
    save_record(path, record)
    print(f"Sent {len(runs)} runs to neatlogs cloud: {', '.join(runs.values())}." if sent else f"The runs were not sent to neatlogs cloud. neatroots said: {said}")
    return 0 if sent else 1


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


def _attempt(kind: str, case, repo: Path, record: dict, args, feedback: str = "", number: int = 1) -> dict:
    """Make one fix and replay it. Returns what was tried and how it went."""
    tracer = getattr(args, "tracer", OFF)
    out: dict = {}

    def work() -> dict:
        out["attempt"] = attempt = _try_fix(kind, case, repo, record, args, feedback, tracer)
        seen, harm = attempt.get("verification") or {}, attempt.get("harm") or {}
        return {"commit": (attempt.get("commit") or "")[:12], "kept": _proven(attempt), "failures": seen.get("failures"), "replays": seen.get("replays"),
                "broke_other_requests": len(harm.get("broken", [])), "note": attempt.get("note", "")}
    tracer.step(f"fix attempt {number}, a {kind}", {"culprit": record["lineup"]["culprit"]["sha"][:12], "after_an_earlier_try": bool(feedback)}, work)
    return out["attempt"]


def _try_fix(kind: str, case, repo: Path, record: dict, args, feedback: str, tracer) -> dict:
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

    def verify() -> dict:
        with Runner(repo, case, keep=getattr(args, "keep", False)) as runner:
            checked = fixes.verify(lambda: runner.trial(made.commit), good, bad, budget=args.fix_budget, parallel=args.parallel)
            attempt["failed_replays"] = [f"{r.input} -> {r.reason}" for r in runner.replays if r.verdict == FAIL][:4]
            attempt["voided"] = sum(r.voided for r in runner.replays)
        attempt["verification"] = asdict(checked)
        return {"failures": checked.failures, "replays": checked.replays, "at_most_at_95": round(checked.upper, 4), "cleared_the_bar": checked.fixed, "voided": attempt["voided"]}
    tracer.step("verify the fix", {"commit": made.commit[:12], "bar": "95% likely to be back within 5 points of the rate before the culprit"}, verify)
    checked = attempt["verification"]
    attempt["diff"] = git(repo, "show", "--format=", made.commit)[:4000]
    print(f"  {kind}: {fixes.observed(checked['failures'], checked['replays'])} " + (f"Not kept: {checked['note']}." if checked["note"] else "That clears the bar for keeping it."))
    if checked["fixed"]:
        def no_harm() -> dict:
            harm = _check_harm(case, repo, record, made.commit, args)
            if harm:
                attempt["harm"] = harm
                print(f"  {kind}: {_harm_said(harm)}")
            return {"checked": (harm or {}).get("checked", 0), "broken": [b["text"] for b in (harm or {}).get("broken", [])],
                    "already_failing": len((harm or {}).get("already_failing", []))}
        tracer.step("do no harm", {"commit": made.commit[:12]}, no_harm)
    return attempt


def _check_harm(case, repo: Path, record: dict, commit: str, args) -> dict | None:
    """Replay the other cases' inputs and the ordinary requests on a fix commit. None if there are none to replay."""
    others = _other_requests(case)
    if not others:
        return None
    expect = {text: wanted for text, wanted, _ in others}
    where = {"fix": commit, "before": record["case"]["bad"]}
    with Runner(repo, case, keep=getattr(args, "keep", False)) as runner:
        harm = fixes.do_no_harm(lambda at, text: runner.replay(where[at], CaseInput(text, expect[text])).verdict,
                                [(text, source) for text, _, source in others], parallel=args.parallel)
    return asdict(harm)


def harm(args) -> int:
    """Run the do-no-harm check on a fix that was kept before the check existed, or again on any kept fix."""
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    kept = record.get("fix") or {}
    if not kept.get("commit") or not (kept.get("verification") or {}).get("fixed"):
        print("This case has no fix that cleared its own bar, so there is nothing to check.")
        return 2
    began = _now_ms()
    found = _check_harm(case, repo, record, kept["commit"], args)
    if found is None:
        print("No other cases and no ordinary.toml under cases/, so there is nothing to check against.")
        return 2
    kept["harm"] = found
    for attempt in record.get("attempts", []):
        if attempt.get("commit") == kept["commit"]:
            attempt["harm"] = found
    _replayed(record, began)
    save_record(path, record)
    print(_harm_said(found))
    return 1 if found["broken"] else 0


def _other_requests(case) -> list[tuple[str, dict, str]]:
    """(request, what it should produce, where it came from) for the do-no-harm check.

    They come from the folder kept cases live in, `cases/` under the working directory: the
    inputs of every other case for the same agent, and `ordinary.toml`, a short list of
    everyday requests that should succeed. A request this case already replays is left out.
    """
    import tomllib

    mine, out = {i.text for i in case.inputs}, {}
    for path in sorted((Path.cwd() / "cases").glob("*.toml")):
        try:
            data = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if "good" in data and (data.get("id") == case.id or data.get("target", ".") != case.target or data.get("check", {"kind": "refunds"}) != case.check):
            continue  # this case itself, another agent, or a check this case's runner cannot apply
        source = data.get("id") or path.stem
        for one in data.get("inputs", []):
            if one.get("text") and one["text"] not in mine:
                out.setdefault(one["text"], ({k: v for k, v in one.items() if k != "text"}, f"case {source}" if "good" in data else "an ordinary request"))
    return [(text, expect, source) for text, (expect, source) in out.items()]


def _harm_said(harm: dict) -> str:
    """The do-no-harm result in a sentence, for the command line and the case file."""
    n = harm["checked"]
    said = f"Checked against {n} other {'request' if n == 1 else 'requests'}."
    if harm["broken"]:
        said += f" The fix made {len(harm['broken'])} of them go wrong more often than before: " + "; ".join(
            f'"{b["text"]}" went wrong in {b["fix"][0]} of {b["fix"][1]} replays on the fix, and in {b["before"][0]} of {b["before"][1]} before it' for b in harm["broken"]) + "."
    else:
        said += " The fix broke none of them."
    if harm["already_failing"]:
        k = len(harm["already_failing"])
        said += f" {k} {'was' if k == 1 else 'were'} already going wrong before the fix, which is some other bug's doing."
    if harm["unclear"]:
        k = len(harm["unclear"])
        said += f" {k} went wrong once or twice on the fix commit, too few times to say the fix did it."
    return said


def _proven(attempt: dict) -> bool:
    """Did this attempt clear the bar for keeping a fix, and break nothing else? That is a threshold on the replays, not proof."""
    return bool((attempt.get("verification") or {}).get("fixed")) and not (attempt.get("harm") or {}).get("broken")


def fix(args) -> int:
    """Apply the ruling on a branch and replay until the fix clears the bar or plainly does not. If it does not, try again.

    The bar: the fix commit's failure rate is 95% likely to be back within 5 points of the rate
    before the culprit. A patch that does not clear it gets one more try, with the first patch
    and its failing replays in front of the model. If that does not clear it either, the culprit
    is reverted, which is the safe answer and loses what the commit was for. Every try is kept
    in the record.
    """
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    if not record.get("ruling"):
        print(f"No ruling yet. Run `whodunit ruling {args.case}` first.")
        return 2
    wanted = record["ruling"]["ruling"]
    began = _now_ms()
    attempts = [_attempt(wanted, case, repo, record, args, number=1)]
    if wanted == rulings.PATCH and not _proven(attempts[-1]):
        first = attempts[-1]
        feedback = (first.get("note") or "") + "\nThe first patch:\n" + first.get("diff", "none was made") + "\nReplays of it that still failed:\n" + "\n".join(first.get("failed_replays", []) or ["none recorded"])
        if (first.get("harm") or {}).get("broken"):
            feedback += "\nThe first patch cleared its own case and made other requests go wrong more often than before it. " + _harm_said(first["harm"]) + " A patch must not do that."
        print("  The patch " + ("made other requests worse" if (first.get("harm") or {}).get("broken") else "did not clear the bar") + ". Trying once more, with the first patch and what went wrong in view.")
        attempts.append(_attempt(rulings.PATCH, case, repo, record, args, feedback, number=2))
    if wanted == rulings.PATCH and not _proven(attempts[-1]):
        print("  The second patch is not kept either. Falling back to a revert, which loses what the commit was for.")
        attempts.append(_attempt(rulings.REVERT, case, repo, record, args, number=3))
        attempts[-1]["note"] = ((attempts[-1].get("note") or "") + " This is a fallback: the ruling was to patch, and two patches were not kept.").strip()
    final = next((a for a in reversed(attempts) if _proven(a)), attempts[-1])
    record["fix"] = final
    record["attempts"] = attempts
    _replayed(record, began)
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
        seen = final["verification"]
        print(f"Kept the {final['kind']} {final['commit'][:12]} after {len(attempts)} {'try' if len(attempts) == 1 else 'tries'}: {fixes.observed(seen['failures'], seen['replays'])}")
        print(f"The case is kept as a regression test: {record['fix']['regression_case']}")
        print(f"The branch {final['branch']} is local. Pushing it and opening a pull request is the owner's call.")
    else:
        print(f"Not fixed after {len(attempts)} {'try' if len(attempts) == 1 else 'tries'}. The record has each one.")
    return 0 if _proven(final) else 1


def investigate(args) -> int:
    """Run a whole case: lineup, motive and brief, ruling, fix, damages, case file. Stops only for the owner's ruling.

    The run is one trace. Each step is a span inside it, and so is each round of the lineup
    and each fix attempt. Where the trace goes is `whodunit/trace.py`'s business, and with no
    SDK or no key it goes nowhere and nothing else changes.
    """
    case = Case.load(args.case)
    path = record_path(args)
    if getattr(args, "fresh", False) and path.is_file():
        import time

        path.rename(path.with_name(path.name + time.strftime(".%H%M%S.old")))
    args.tracer = tracer = Trace(case.id)
    if not tracer.on:
        print(f"No trace of this investigation is being sent: {tracer.note}.")
    out: dict = {}

    def run() -> dict:
        out["code"] = _investigate(args, path, tracer)
        record = load_record(path)
        culprit, kept = (record.get("lineup") or {}).get("culprit"), record.get("fix") or {}
        return {"culprit": culprit["sha"][:12] if culprit else None, "probability": (culprit or {}).get("probability"),
                "replays": (record.get("lineup") or {}).get("replays"),
                "fix": f"{kept['kind']} kept" if _proven(kept) else "waiting for the owner's ruling" if out["code"] == 3 else "none kept",
                "no_commit_did_it": bool((record.get("lineup") or {}).get("clear"))}
    try:
        tracer.root({"symptom": case.symptom, "good": case.good[:12], "bad": case.bad[:12]}, run)
    finally:
        tracer.close()
    if tracer.trace_id:
        record = load_record(path)
        record["trace"] = {"where": tracer.where, "trace_id": tracer.trace_id}
        save_record(path, record)
    open_case(argparse.Namespace(case=args.case, record=args.record, no_open=True))
    return out["code"]


def _investigate(args, path: Path, tracer) -> int:
    def note(step: str, outcome: str) -> None:
        # Progress for whoever is watching. The case file's log is worked out from the record itself,
        # so a step that is run again later cannot leave a stale line behind.
        print(f"[{step}] {outcome}")

    def step(name: str, given: dict, command, told) -> int:
        """Run one command of the pipeline inside a span. `told(record)` is what the span says came of it."""
        seen: dict = {}

        def work() -> dict:
            seen["code"] = command(args)
            return {"exit": seen["code"], **told(load_record(path))}
        tracer.step(name, given, work)
        return seen["code"]

    record = load_record(path)
    args.method, args.confidence, args.no_priors, args.keep, args.json = "statistical", 0.95, False, False, False
    args.repeats = 1
    args.no_runs, args.from_record, args.since_ms = False, False, None
    if not (record.get("lineup") or {}).get("culprit"):
        def named(now: dict) -> dict:
            report = now.get("lineup") or {}
            return {"culprit": ((report.get("culprit") or {}).get("sha") or "")[:12] or None, "replays": report.get("replays"),
                    "commits_tested": report.get("commits_tested"), "voided": report.get("voided"), "note": report.get("note", "")}
        args.resume = bool(record.get("replays"))
        code = step("lineup", {"budget": args.budget, "resumed": args.resume}, lineup, named)
        if code == 1:
            note("lineup", f"Nobody could be named inside {args.budget} replays. Carrying on from those replays with {args.budget} more.")
            args.resume = True
            code = step("lineup", {"budget": args.budget, "resumed": True}, lineup, named)
        if code == 4:
            note("lineup", "No commit did it: the good ref fails as often as the bad one today. The case file says what differs from the old runs.")
            return 4
        if code != 0:
            note("lineup", "No culprit named. The case file lists the suspects that remain." if code == 1 else "The case could not be run: its good ref fails or its bad ref passes.")
            return 1
        found = load_record(path)["lineup"]
        note("lineup", f"Named {found['culprit']['sha'][:12]} ({found['culprit']['subject']}) after {found['replays']} replays across {found['commits_tested']} commits.")
    else:
        note("lineup", f"Already named: {record['lineup']['culprit']['sha'][:12]}.")
    if not load_record(path).get("brief") or args.redo_brief:
        brief(args)  # makes its own two spans, one for the motive and one for the brief
        if tracer.where == "cloud":
            # The two runs the brief cites go to the same place as the investigation's own trace.
            step("send the failing and passing run to neatlogs cloud", {}, forward, lambda now: (now.get("evidence") or {}).get("cloud") or {})
        written = load_record(path)
        note("brief", f"Written by {'a model' if written['brief'].get('writer') == 'model' else 'the fixed template'}. Motive: {'on record' if written['motive'].get('request') else written['motive'].get('note') or 'none'}")
    code = step("ruling", {"asked": "revert it, or keep what it was for and patch the bug?"}, ruling,
                lambda now: {"ruling": (now.get("ruling") or {}).get("ruling"), "kind": (now.get("ruling") or {}).get("kind") or (now.get("ruling_question") or {}).get("kind"),
                             "asked_the_owner_now": (now.get("ruling") or {}).get("asked_now"), "waiting": "ruling" not in now})
    if code != 0:
        note("ruling", "Waiting for the owner. Give it with `whodunit ruling <case> --answer revert` or `--answer patch`, then run investigate again.")
        return 3
    decided = load_record(path)["ruling"]
    note("ruling", f"{decided['ruling']} for a {decided['kind']} change" + ("" if decided.get("asked_now") else ", from the standing rule"))
    code = fix(args)  # each attempt is a span of its own
    done = load_record(path)
    tries = done.get("attempts", [])
    seen = (done.get("fix") or {}).get("verification") or {}
    note("fix", (f"Kept a {done['fix']['kind']} after {len(tries)} {'try' if len(tries) == 1 else 'tries'}: {fixes.observed(seen['failures'], seen['replays'])}" if code == 0
                 else f"No fix cleared the bar in {len(tries)} {'try' if len(tries) == 1 else 'tries'}."))
    step("damages", {"workflow": args.workflow}, damages,
         lambda now: {key: (now.get("damages") or {}).get(key) for key in ("case_runs", "case_bad", "wrongly_paid", "withheld", "replay_runs", "replay_usd")})
    return code


def check(args) -> int:
    """Replay a kept case against a ref. This is the regression test."""
    import time

    case = Case.load(args.case)
    repo = Path(args.repo).resolve()
    ref = args.ref or case.fixed or "HEAD"
    began = _now_ms()
    with Runner(repo, case) as runner:
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
            verdicts = list(pool.map(lambda _: runner.trial(ref), range(args.runs)))
    failures, judged = verdicts.count(FAIL), verdicts.count(FAIL) + verdicts.count(PASS)
    sha = resolve(repo, ref)
    print(f"{case.id} at {sha[:12]}: {failures} failures in {judged} replays." + (f" {verdicts.count(VOID)} more were voided by provider errors." if VOID in verdicts else ""))
    path = record_path(args)
    record = load_record(path)
    if record:
        record.setdefault("checks", []).append({"at": time.strftime("%Y-%m-%d %H:%M"), "ref": sha, "runs": judged, "failures": failures})
        _replayed(record, began)
        save_record(path, record)
    return 0 if failures == 0 and judged > 0 and "skip" not in verdicts else 1


def damages(args) -> int:
    loaded = _need_culprit(args)
    if loaded is None:
        return 2
    case, repo, record, path = loaded
    try:
        order = [s["sha"] for s in record["suspects"]]
        since_culprit = order[order.index(record["lineup"]["culprit"]["sha"]):]
        started = [r["started"] * 1000 for r in record.get("replays", []) if r.get("started")]
        # A record from before the stretches were kept has one, from its first replay to its last.
        mine = [tuple(w) for w in record.get("replay_windows", [])] or ([(min(started) - 2000, record.get("replays_until_ms") or _now_ms())] if started else None)
        counted = damage.count(neatroots(), args.workflow, commits=since_culprit, since_ms=args.since_ms, case_id=case.id, replays_between=mine)
        counted = damage.count_case(neatroots(), counted, args.workflow, since_culprit, [(i.text, i.expect.get("refunds", [])) for i in case.inputs])
    except NeatError as exc:
        print(f"neatroots could not be asked: {exc}")
        return 1
    counted.sent_by = case.traffic_sent_by
    record["damages"] = counted.to_dict()
    save_record(path, record)
    if not counted.runs:
        print("No ordinary runs are recorded on the culprit or the commits after it, so there is no damage to count.")
    elif not counted.case_runs:
        print(f"{counted.runs} ordinary {args.workflow} runs are on record for the culprit or later, and none of them asked what this case asks, so no damage can be counted.")
    else:
        print(f"{counted.runs} ordinary {args.workflow} runs are on record for the culprit or later. {counted.case_runs} of them asked what this case asks, "
              f"and {counted.case_bad} failed its check: {counted.wrongly_paid:.2f} refunded that should not have been, {counted.withheld:.2f} owed and not refunded, "
              f"about ${counted.case_bad_usd:.4f} of tokens.")
    if counted.sent_by:
        print(f"Those ordinary runs were sent by {counted.sent_by}, not by real customers.")
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


def _from_trace(args) -> int:
    """Write a case file from one failing run, and stop. `whodunit investigate` takes it from there."""
    import tomllib

    from .env import load_env
    from .neat import NEATLOGS, Mcp

    repo = Path(args.repo).resolve()
    local = neatroots()
    load_env()
    cloud = Mcp(NEATLOGS, token=os.environ["NEATLOGS_API_KEY"]) if os.environ.get("NEATLOGS_API_KEY") else None
    try:
        run = opening.read_failing_run(args.from_trace, local, cloud)
    except LookupError as exc:
        print(exc)
        return 2
    if not run.request or not run.commit:
        print(f"Run {run.trace_id[:12]} was found in {run.source}, and it has no " + ("request in its root span." if not run.request else "commit in its run_info tags, so there is no bad ref."))
        return 2
    try:
        run.commit = resolve(repo, run.commit)
    except RuntimeError:
        print(f"Run {run.trace_id[:12]} ran on commit {run.commit[:12]}, which is not in this repo.")
        return 2
    try:
        earlier = opening.history(local, repo, run)
    except (NeatError, KeyError, TypeError) as exc:
        earlier = []
        print(f"neatroots could not be asked for earlier runs of this request: {exc}")
    made = opening.draft(run, earlier)
    print(f"Failing run {run.trace_id[:12]}, from {run.source}, on commit {run.commit[:12]}.")
    print(f"It was asked: {run.request}")
    print(f"It refunded: {json.dumps(run.paid) if run.paid else 'nothing'}")
    if args.expect is not None:
        made.expected, made.expected_from = json.loads(args.expect), None
    if made.expected is None:
        # The one question. Nobody can say what the run should have done but the owner.
        question = ("No earlier run of this request passed. What should this request have produced? "
                    'Give the refunds as JSON, for example [] or [{"order_id": "1001", "refunded": 42.0}]: ')
        if not sys.stdin.isatty():
            print(question)
            print("Answer with --expect '<JSON>' and run this again.")
            return 2
        try:
            made.expected = json.loads(input(question))
        except (json.JSONDecodeError, EOFError) as exc:
            print(f"That could not be read as JSON: {exc}")
            return 2
    elif made.expected_from:
        print(f"It should have refunded: {json.dumps(made.expected)}, which is what run {made.expected_from['trace_id'][:12]} paid for the same request on commit {made.expected_from['commit'][:12]}.")
    if args.good:
        made.good = resolve(repo, args.good)
    if made.good is None:
        print("No earlier run says where the trouble began, so the last good ref has to be given: --good <ref>")
        return 2
    for said in made.notes:
        print(said)
    like_path = Path(args.like) if args.like else next(
        (p for p in sorted((Path.cwd() / "cases").glob("*.toml")) if "good" in tomllib.loads(p.read_text())), None)
    if like_path is None or not like_path.is_file():
        print("A trace does not say how to run the agent. Point at a case for the same agent with --like <case.toml>.")
        return 2
    like = tomllib.loads(like_path.read_text())
    case_id = args.id or f"trace-{run.trace_id[:8]}"
    def refunds_said(paid: dict) -> str:
        return " and ".join(f"a refund of {amount:.2f} on order {order}" for order, amount in sorted(paid.items())) or "no refund"

    wanted = {str(r["order_id"]): float(r["refunded"]) for r in made.expected or []}
    symptom = args.symptom or f'The request "{run.request}" ended in {refunds_said(run.paid)}, where it should have ended in {refunds_said(wanted)}.'
    out = Path(args.out) if args.out else Path.cwd() / "cases" / f"{case_id}.toml"
    if out.exists():
        print(f"{out} is already there. Pick another --id or --out.")
        return 2
    comment = (f"Opened from failing run {run.trace_id} in {run.source}.\n"
               + (f"The expected result is what run {made.expected_from['trace_id']} paid for the same request on commit {made.expected_from['commit'][:12]}.\n" if made.expected_from
                  else "The expected result was given by the owner.\n")
               + f"How to run the agent was copied from {like_path.name}.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(opening.case_toml(case_id, symptom, made, like, comment))
    between = len(git(repo, "rev-list", f"{made.good}..{made.bad}").split())
    print(f"Last good ref {made.good[:12]}, first bad ref {made.bad[:12]}: {between} suspects.")
    print(f"Case file: {out}")
    print(f"Next: whodunit investigate {out}")
    return 0


def open_case(args) -> int:
    if getattr(args, "from_trace", None):
        return _from_trace(args)
    if not args.case:
        print("Give a case file, or --from-trace <trace id> to write one from a failing run.")
        return 2
    path = record_path(args)
    record = load_record(path)
    if not record:
        print("No cases yet. Lucky you." if not Path(args.case).is_file() else f"No record for this case yet. Run `whodunit lineup {args.case}` first.")
        return 2
    page = casefile.write(for_page(record, path), path.with_name(path.name.replace(".record.json", "") + ".casefile.html"))
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
        record = for_page(load_record(path), path)
        page = casefile.write(record, path.with_name(path.name.replace(".record.json", "") + ".casefile.html"))
        records.append((page.name, record))
    records.sort(key=lambda item: item[1].get("case", {}).get("number", 0))
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
    p.add_argument("--workflow", help="the agent's workflow name in its traces, used to find old runs of the good ref when no commit turns out to be to blame")
    p.add_argument("--no-graph", action="store_true", help="do not ask entire-graph which commits could reach the agent")
    p.add_argument("--no-priors", action="store_true", help="suspect every commit equally, even ones that never touched the agent")
    p.add_argument("--ablation", action="store_true", help="write the result next to the record as <case>.ablation.json and leave the record alone; use with --no-graph to see what the alibis were worth")
    p.add_argument("--record", help="where to write the case record (default: next to the case file)")
    p.add_argument("--keep", action="store_true", help="leave the worktrees in .whodunit/worktrees")
    p.add_argument("--json", action="store_true", help="print the result as JSON on stdout")
    p.set_defaults(func=lineup)
    for name, func, text in (
        ("brief", brief, "write the root-cause brief for a case that has a culprit"),
        ("ruling", ruling, "ask the owner once per kind of change: revert, or keep the intent and patch"),
        ("fix", fix, "apply the ruling on a branch and replay it against the bar for keeping a fix"),
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
    p = commands.add_parser("forward", help="send the case's failing run and passing run from neatroots to neatlogs cloud")
    p.add_argument("case", help="path to the case file")
    p.add_argument("--record", help="the case record (default: next to the case file)")
    p.set_defaults(func=forward)
    p = commands.add_parser("harm", help="replay the other cases' inputs and the ordinary requests on a kept fix, to see that it broke nothing")
    p.add_argument("case", help="path to the case file")
    p.add_argument("--record", help="the case record (default: next to the case file)")
    p.add_argument("--parallel", type=int, default=3)
    p.set_defaults(func=harm)
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
    p = commands.add_parser("open-case", help="write the case file page and open it, or with --from-trace write a new case file from one failing run")
    p.add_argument("case", nargs="?")
    p.add_argument("--record")
    p.add_argument("--no-open", action="store_true", help="write the page without opening a browser")
    p.add_argument("--from-trace", metavar="TRACE_ID", help="write a case file from this failing run in neatroots or neatlogs cloud, and stop")
    p.add_argument("--repo", default=".", help="with --from-trace: the git repo that holds the agent")
    p.add_argument("--like", metavar="CASE", help="with --from-trace: a case for the same agent, to copy how it is built and run (default: the first one under cases/)")
    p.add_argument("--id", help="with --from-trace: the new case's id (default: trace-<first 8 of the trace id>)")
    p.add_argument("--symptom", help="with --from-trace: the symptom line, if the one worked out is not good enough")
    p.add_argument("--expect", metavar="JSON", help="with --from-trace: what the request should have produced, when no earlier run shows it")
    p.add_argument("--good", metavar="REF", help="with --from-trace: the last good ref, when no earlier run places it")
    p.add_argument("--out", help="with --from-trace: where to write the case file (default: cases/<id>.toml)")
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
    p.add_argument("commit", nargs="?", help="commit SHA or ref")
    p.add_argument("--case", help="look the motive up again for this case's culprit and store it in the case record")
    p.add_argument("--record", help="with --case: the case record (default: next to the case file)")
    p.add_argument("--repo", default=".")
    p.add_argument("--steps", type=int, default=12, help="how many of the agent's steps to print")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=motive)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

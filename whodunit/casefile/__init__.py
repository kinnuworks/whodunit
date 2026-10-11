"""The case file: one static HTML page per case, drawn from the case record."""

import math
from html import escape
from pathlib import Path

from ..fix import observed

STYLE = (Path(__file__).parent / "casefile.css").read_text()


def _short(sha: str | None) -> str:
    return (sha or "")[:12]


def _pct(value: float) -> str:
    if value >= 0.9995:
        return "over 99.9%"
    return f"{value:.1%}" if value < 0.995 else f"{value:.2%}"


def _field(label: str, body: str) -> str:
    return f'<section class="field"><h2>{escape(label)}</h2><div class="body">{body}</div></section>'


def _typed(text: str) -> str:
    return f'<pre class="typed">{escape(text.rstrip())}</pre>'


def _cites(ids: list[str]) -> str:
    return "".join(f'<span class="cite">{escape(i)}</span>' for i in ids)


def lineup_svg(record: dict) -> str:
    """One column per suspect, oldest on the left. Height is the probability; marks below are replays."""
    suspects = record.get("suspects", [])
    if not suspects:
        return ""
    culprit = ((record.get("lineup") or {}).get("culprit") or {}).get("sha")
    replays: dict[str, list[str]] = {}
    for replay in record.get("replays", []):
        replays.setdefault(replay["sha"], []).append(replay["verdict"])
    good = replays.get(record.get("case", {}).get("good", ""), [])
    has_odds = any("probability" in s for s in suspects)
    count = len(suspects)
    step = max(12, min(26, 690 // (count + 1)))
    bar_h, top, left = 120, 18, step + 52
    most = max(max(len(v) for v in replays.values()) if replays else 0, 1)
    rows = min(most, 14)
    dot = 7
    height = top + bar_h + 26 + rows * dot + 30
    width = left + count * step + 16
    out = [f'<svg class="lineup" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="The lineup: {count} suspect commits, oldest first">']
    for share in (0.0, 0.5, 1.0):
        y = top + bar_h - share * bar_h
        out.append(f'<line class="rule" x1="{left - 6}" y1="{y:.1f}" x2="{width - 8}" y2="{y:.1f}"/>')
        if has_odds:
            out.append(f'<text class="tick" x="{left - step - 12}" y="{y + 4:.1f}" text-anchor="end">{share:.0%}</text>')

    def marks(x: float, verdicts: list[str]) -> str:
        made = []
        for n, verdict in enumerate(verdicts[: rows * 2]):
            cx = x + (n // rows) * (dot - 1) - (dot - 1) / 2 * (len(verdicts) > rows)
            cy = top + bar_h + 22 + (n % rows) * dot
            made.append(f'<circle class="{"fail" if verdict == "fail" else "skip" if verdict == "skip" else "pass"}" cx="{cx:.1f}" cy="{cy:.1f}" r="2.4"/>')
        return "".join(made)

    gx = left - step / 2 - 4
    out.append(f'<g><title>Last good commit: {good.count("fail")} failures in {len(good)} replays</title>'
               f'<line class="good" x1="{gx:.1f}" y1="{top + bar_h - 6}" x2="{gx:.1f}" y2="{top + bar_h}"/>{marks(gx, good)}</g>')
    for n, suspect in enumerate(suspects):
        x = left + n * step + step / 2
        odds = suspect.get("probability", 1.0 if suspect["sha"] == culprit else 0.0)
        tall = max(2.0, odds * bar_h)
        seen = replays.get(suspect["sha"], [])
        excuse = suspect.get("alibi") or ("" if suspect.get("touches_target", True) else "never touched the agent's folder")
        kind = "culprit" if suspect["sha"] == culprit else "elsewhere" if excuse else "suspect"
        told = f'{n + 1}. {suspect["subject"]} ({_short(suspect["sha"])})'
        if has_odds:
            told += f', {_pct(odds)}'
        if seen:
            told += f', {seen.count("fail")} failures in {len([v for v in seen if v != "skip"])} replays'
        if "skip" in seen:
            told += ", would not build"
        if kind == "elsewhere":
            told += f". Alibi: {excuse}"
        out.append(f'<g><title>{escape(told)}</title>'
                   f'<rect class="hit" x="{x - step / 2:.1f}" y="{top}" width="{step}" height="{height - top}"/>'
                   f'<rect class="bar {kind}" x="{x - (step - 6) / 2:.1f}" y="{top + bar_h - tall:.1f}" width="{step - 6}" height="{tall:.1f}"/>'
                   f'{marks(x, seen)}</g>')
        if kind == "culprit" or n == 0 or n == count - 1:
            out.append(f'<text class="tick{" strong" if kind == "culprit" else ""}" x="{x:.1f}" y="{top + bar_h + 13}" text-anchor="middle">{n + 1}</text>')
    out.append("</svg>")
    return "".join(out)


def timeline(record: dict) -> list[tuple[str, str]]:
    """What happened in this case, in order, as (step, what happened).

    It is worked out from what the record holds now: the lineup, the ruling, each fix attempt.
    An earlier version kept the lines an investigation printed as it went, and those went stale
    as soon as one step was run again by itself.
    """
    lineup, culprit = record.get("lineup") or {}, (record.get("lineup") or {}).get("culprit")
    motive, brief, ruling = record.get("motive") or {}, record.get("brief") or {}, record.get("ruling") or {}
    damages, tries = record.get("damages") or {}, record.get("attempts") or []
    steps = []
    if lineup.get("traffic_runs"):
        steps.append(("traffic", f'{lineup["traffic_runs"]} ordinary runs had already asked this, and {lineup["traffic_failures"]} of them went wrong.'))
    if culprit:
        sure = f' at {_pct(culprit["probability"])}' if "probability" in culprit else ""
        steps.append(("lineup", f'Named {_short(culprit["sha"])}{sure} after {lineup.get("replays", 0)} replays across {lineup.get("commits_tested", 0)} commits.'))
    elif lineup:
        steps.append(("lineup", f'Nobody named after {lineup.get("replays", 0)} replays. {(lineup.get("note") or "no suspect reached the bar").capitalize()}.'))
    if motive:
        steps.append(("motive", f'The request is on record in checkpoint {motive["checkpoint"]}.' if motive.get("request") else (motive.get("note") or "No request is on record.")))
    if brief.get("sentences"):
        told = f'{len(brief["sentences"])} sentences kept and {len(brief.get("dropped", []))} cut by the rule checks'
        steps.append(("brief", f'{told}, after a first draft was sent back.' if brief.get("rejected") else f"{told}."))
    if ruling:
        how = "asked of the owner in this case" if ruling.get("asked_now") else f'from the standing rule set in case {ruling.get("first_case", "")}'
        steps.append(("ruling", f'{ruling["ruling"].capitalize()} for {"an" if ruling["kind"][:1] in "aeiou" else "a"} {ruling["kind"]} change, {how}.'))
    elif record.get("ruling_question"):
        steps.append(("ruling", "Waiting for the owner: revert it, or keep what it was for and patch the bug?"))
    for n, attempt in enumerate(tries, 1):
        seen = attempt.get("verification") or {}
        if attempt.get("commit") is None:
            steps.append(("fix", f'Try {n}, a {attempt["kind"]}: no change was made. {attempt.get("note", "")}'.strip()))
        else:
            steps.append(("fix", f'Try {n}, a {attempt["kind"]}: {observed(seen.get("failures", 0), seen.get("replays", 0))} {"Kept" if seen.get("fixed") else "Not kept"}.'))
    if tries and not any((a.get("verification") or {}).get("fixed") for a in tries):
        steps.append(("fix", f'No fix cleared the bar in {len(tries)} {"try" if len(tries) == 1 else "tries"}. The case stays open.'))
    fix = record.get("fix") or {}
    again = [c for c in record.get("checks", []) if c["ref"] == fix.get("commit")]
    if again:
        steps.append(("check", f'Replayed again as a regression test: {sum(c["failures"] for c in again)} failures in {sum(c["runs"] for c in again)} replays.'))
    if damages.get("case_runs"):
        money = [f'{damages[key]:.2f} {words}' for key, words in (("wrongly_paid", "refunded wrongly"), ("withheld", "owed and not refunded")) if damages.get(key)]
        steps.append(("damages", f'{damages["case_bad"]} of {damages["case_runs"]} ordinary runs that asked this failed the check' + (f': {", ".join(money)}.' if money else ".")))
    return steps


def render(record: dict) -> str:
    case = record.get("case", {})
    lineup = record.get("lineup") or {}
    culprit = lineup.get("culprit")
    suspects = record.get("suspects", [])
    motive = record.get("motive") or {}
    brief = record.get("brief") or {}
    evidence = record.get("evidence") or {}
    ruling = record.get("ruling") or {}
    fix = record.get("fix") or {}
    damages = record.get("damages") or {}
    sent_by = damages.get("sent_by") or case.get("traffic_sent_by")  # who sent the ordinary runs, when it was a script
    parts = []

    # Suspects
    if culprit:
        sure = f' Confidence: {_pct(culprit["probability"])}.' if "probability" in culprit else ""
        named = (f'<p class="verdict"><span class="sha">{escape(_short(culprit["sha"]))}</span> {escape(culprit["subject"])}</p>'
                 f'<p>Suspects: {len(suspects)}. Cleared: {len(suspects) - 1}.{sure}</p>')
    elif lineup:
        named = f'<p class="verdict open">Nobody named yet.</p><p>{escape(lineup.get("note") or "The replays ran out before one suspect stood clear.")}</p>'
    else:
        named = '<p class="empty">No lineup yet. Run <code>whodunit lineup</code> on this case.</p>'
    if lineup:
        rates = ""
        if "failure_rate_from" in lineup and culprit:
            rates = f' From this commit on it fails about {lineup["failure_rate_from"]:.0%} of the time. Before it, about {lineup["failure_rate_before"]:.0%}.'
        scan = f' A scan from the oldest suspect would have tested {lineup["linear_scan_commits"]} commits.' if "linear_scan_commits" in lineup else ""
        if lineup.get("traffic_runs"):
            who = f' The ordinary runs were sent by <code>{escape(sent_by)}</code>, a script that plays customers.' if sent_by else ""
            named += (f'<p class="small">Before any replay, {lineup["traffic_runs"]} ordinary runs had already asked this, '
                      f'and {lineup["traffic_failures"]} of them went wrong. They were used as evidence at no cost.{who}</p>')
        named += (f'<p class="small">{lineup.get("replays", 0)} replays across {lineup.get("commits_tested", 0)} commits, '
                  f'{lineup.get("seconds", 0) / 60:.1f} minutes of replay time.{rates}{scan}</p>')
        named += f'<div class="scroll">{lineup_svg(record)}</div>'
        named += ('<p class="key"><span class="swatch culprit"></span>culprit <span class="swatch suspect"></span>suspect '
                  '<span class="swatch elsewhere"></span>has an alibi <span class="dot fail"></span>failed replay <span class="dot pass"></span>passed replay</p>')
        excused = [s for s in suspects if s.get("alibi") and s["sha"] != culprit]
        if excused:
            rows = "".join(f'<li><span class="sha">{escape(_short(s["sha"]))}</span> {escape(s["subject"])}: {escape(s["alibi"])}.</li>' for s in excused)
            named += f'<details><summary>Alibis: {len(excused)} of {len(suspects)} suspects started with less suspicion</summary><ul class="steps">{rows}</ul></details>'
        tried = record.get("ablation") or {}
        if tried.get("replays") and culprit:
            # What the head start was worth, from a run of the same case without it.
            same = tried.get("culprit") in (None, culprit["sha"])
            ended = (f'to reach {_pct(tried["probability"])} on the same commit' if same and tried.get("probability") else
                     "and named a different commit" if tried.get("culprit") else "and named nobody")
            runs = tried.get("runs", 1)
            named += (f'<p class="small">What the head start was worth: run again without {escape(" and without ".join(tried.get("without") or ["it"]))}, '
                      f'this case took {tried["replays"]} replays across {tried["commits_tested"]} commits {ended}, against {lineup.get("replays", 0)} across {lineup.get("commits_tested", 0)} here. '
                      f'That is {"one run" if runs == 1 else f"{runs} runs"} each way, which is too few to call the difference measured'
                      f'{", and the things taken away cannot be told apart" if len(tried.get("without") or []) > 1 else ""}.</p>')
        if not culprit and lineup.get("remaining"):
            rows = "".join(f'<tr><td class="num">{_pct(r.get("probability", 0))}</td><td class="sha">{escape(_short(r["sha"]))}</td><td>{escape(r["subject"])}</td></tr>' for r in lineup["remaining"][:8])
            named += f'<table class="remaining"><caption>Still in the lineup</caption>{rows}</table>'
    parts.append(_field("Suspects", named))

    # Motive
    if motive.get("request"):
        link = f' <a href="{escape(motive["link"])}">Open the checkpoint</a>' if motive.get("link") else ""
        body = (f'<p>Someone asked the coding agent for this:</p>{_typed(motive["request"])}'
                f'<p class="small">Entire checkpoint <span class="cite">{escape(motive.get("checkpoint") or "")}</span>, asked at {escape((motive.get("request_time") or "")[:16].replace("T", " "))} UTC.{link}</p>')
        steps = [s for s in motive.get("steps", []) if s["kind"] in ("said", "edited")][-6:]
        if steps:
            lines = "".join(
                f'<li><span class="cite">{escape(s["id"])}</span> {escape(s["kind"])}{" " + escape(s["file"]) if s.get("file") else ""}: '
                f'{escape(s["text"].strip().splitlines()[0][:180]) if s["text"].strip() else ""}</li>' for s in steps)
            body += f'<details><summary>What the coding agent did next</summary><ul class="steps">{lines}</ul></details>'
    elif motive:
        body = f'<p class="empty">{escape(motive.get("note") or "No request is recorded for this commit.")}</p>'
        if motive.get("message"):
            body += f'<p>All that is left is the commit\'s own message:</p>{_typed(motive["message"])}'
    else:
        body = '<p class="empty">Not looked up yet.</p>'
    parts.append(_field("Motive", body))

    # Brief
    if brief.get("sentences"):
        body = f'<p class="headline">{escape(brief.get("headline", ""))}</p>'
        body += "".join(f'<p>{escape(s["text"])} {_cites(s["cites"])}</p>' for s in brief["sentences"])
        cut = len(brief.get("dropped", []))
        sent_back = brief.get("rejected") or []
        again = (f' A first draft was sent back because it {escape(sent_back[0]["problem"])}.' if sent_back else "")
        body += (f'<p class="small">Written by: {escape(brief.get("model", "unknown"))}. Every sentence cites a span, a commit or a checkpoint, '
                 f'and is held against what the lineup measured. {cut} cut by those checks.{again}</p>')
    else:
        body = '<p class="empty">No brief yet.</p>'
    parts.append(_field("Brief", body))

    # Evidence
    body = ""
    runs = [(label, evidence.get(key)) for label, key in (("Passing run", "passing_run"), ("Failing run", "failing_run")) if evidence.get(key)]
    if runs:
        body += '<div class="pair">' + "".join(
            f'<div><h3>{label} <span class="cite">{escape(run["trace_id"][:12])}</span></h3><p class="small">at commit {escape(_short(run["commit"]))}</p>{_typed(run["outline"])}</div>'
            for label, run in runs) + "</div>"
    if evidence.get("diff"):
        body += f'<details{" open" if not runs else ""}><summary>The culprit\'s diff</summary>{_typed(evidence["diff"])}</details>'
    for note in evidence.get("notes", []):
        body += f'<p class="small">{escape(note)}</p>'
    parts.append(_field("Evidence", body or '<p class="empty">Nothing collected yet.</p>'))

    # Ruling
    if ruling:
        again = "" if ruling.get("asked_now") else f' Nobody was asked this time. The rule was set on {escape(ruling["decided_on"])} in case {escape(ruling["first_case"])}.'
        what = "Revert it." if ruling["ruling"] == "revert" else "Keep what it was for, and patch the bug."
        article = "an" if ruling["kind"][:1] in "aeiou" else "a"
        body = f'<p class="verdict small-verdict">{what}</p><p>This is the owner\'s standing rule for {article} {escape(ruling["kind"])} change.{again}</p>'
    else:
        body = '<p class="empty">The owner has not been asked yet.</p>'
    parts.append(_field("Ruling", body))

    # Fix
    tries = record.get("attempts") or []

    def tried() -> str:
        rows = ""
        for n, attempt in enumerate(tries, 1):
            seen = attempt.get("verification") or {}
            if attempt.get("commit") is None:
                how = f'no change was made. {escape(attempt.get("note", ""))}'
            else:
                how = (f'<span class="sha">{escape(_short(attempt["commit"]))}</span>, {observed(seen.get("failures", 0), seen.get("replays", 0))} '
                       f'{"Kept" if seen.get("fixed") else "Not kept"}.')
            rows += f'<li>Try {n}, a {escape(attempt["kind"])}: {how}</li>'
        return f'<details open><summary>What it took</summary><ol class="steps">{rows}</ol></details>'

    if fix.get("commit"):
        check = fix.get("verification") or {}
        body = f'<p>{escape(fix["kind"]).capitalize()} committed as <span class="sha">{escape(_short(fix["commit"]))}</span> on branch <code>{escape(fix["branch"])}</code>.</p>'
        if check:
            bar = "the bar for keeping a fix: a failure rate 95% likely to be back within 5 points of the rate before the culprit"
            verdict = f"That clears {bar}." if check["fixed"] else f'That is short of {bar}. {escape(check.get("note", "")).capitalize()}.'
            body += f'<p><strong>{observed(check["failures"], check["replays"])}</strong> {verdict}</p>'
            if check["fixed"]:
                body += ('<p class="small">The second figure is the 95% upper bound on how often the fix still fails, from these replays alone. '
                         'Clearing the bar is not proof: in simulation a fix that still fails 4 runs in 100 clears it about one time in three.</p>')
        if len(tries) > 1:
            body += tried()
        if fix.get("note"):
            body += f'<p class="small">{escape(fix["note"])}</p>'
        again = [c for c in record.get("checks", []) if c["ref"] == fix["commit"]]
        if again:
            runs, failed = sum(c["runs"] for c in again), sum(c["failures"] for c in again)
            body += f'<p>Replayed again as a regression test: {failed} failures in {runs} replays.</p>'
        if fix.get("regression_case"):
            body += f'<p class="small">Kept as a regression test: <code>{escape(Path(fix["regression_case"]).name)}</code></p>'
    elif fix:
        body = f'<p class="verdict open small-verdict">Not fixed.</p><p>{len(tries) or "No"} {"try" if len(tries) == 1 else "tries"}, and none cleared the bar for keeping a fix.</p>'
        if tries:
            body += tried()
        elif fix.get("note"):
            body += f'<p class="small">{escape(fix["note"])}</p>'
    else:
        body = '<p class="empty">Not fixed yet.</p>'
    parts.append(_field("Fix", body))

    # Damages: only runs that fail this case's own check
    if damages:
        if not damages["runs"]:
            body = '<p>No ordinary runs are recorded on the culprit or the commits after it, so there is no damage to count.</p>'
        elif not damages.get("case_runs"):
            body = (f'<p>{damages["runs"]} ordinary runs are on record for the culprit or later, and none of them asked what this case asks. '
                    'No damage can be counted from them.</p>')
        elif not damages["case_bad"]:
            body = (f'<p>None of the {damages["case_runs"]} ordinary runs that asked what this case asks, on the culprit or later, failed its check. '
                    'The replays show the bug. No ordinary run happened to hit it.</p>')
        else:
            money = [f'{damages[key]:.2f} {words}' for key, words in (("wrongly_paid", "was refunded that should not have been"), ("withheld", "was owed and not refunded")) if damages[key]]
            body = (f'<p>{damages["case_bad"]} of the {damages["case_runs"]} ordinary runs that asked what this case asks, on the culprit or later, failed its check. '
                    f'{", and ".join(money).capitalize()}.</p>')
            if "case_bad_usd" in damages:
                body += f'<p class="small">Those {damages["case_bad"]} runs cost about ${damages["case_bad_usd"]:.2f} in tokens.</p>'
        if damages["runs"]:
            body += (f'<p class="small">{damages["runs"]} ordinary runs of every kind are on record for the same commits. '
                     'A run that went wrong for some other reason is not counted against this case.</p>')
            if sent_by:
                body += (f'<p class="small">The ordinary runs were sent by <code>{escape(sent_by)}</code>, a script that plays customers against each commit. '
                         'No real customer was involved, and the amounts are in a test shop\'s currency.</p>')
        body += (f'<p class="small">The investigation used {damages["replay_runs"]} replays, about ${damages["replay_usd"]:.2f}. {escape(damages["note"])}</p>')
    else:
        body = '<p class="empty">Not counted yet.</p>'
    parts.append(_field("Damages", body))

    # Log: what happened, in order, worked out from the record as it stands
    happened = timeline(record)
    if happened:
        rows = "".join(f'<li><span class="cite">{escape(step)}</span> {escape(text)}</li>' for step, text in happened)
        parts.append(_field("Log", f'<ol class="steps">{rows}</ol>'))

    stamp = ("Closed" if (fix.get("verification") or {}).get("fixed") else "Culprit named") if culprit else "Open"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Case {escape(case.get("id", ""))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Alegreya+Sans:wght@400;500;700&family=Courier+Prime:wght@400;700&family=Young+Serif&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<main>
<header>
<p class="label">Whodunit case file <span class="caseid">{escape(case.get("id", ""))}</span><span class="stamp{" closed" if culprit else ""}">{stamp}</span></p>
<h1>{escape(case.get("symptom", "Untitled case"))}</h1>
<p class="lede">{len(suspects)} commits since it last worked. Which one did it?</p>
</header>
{"".join(parts)}
<footer><p>Last good <span class="sha">{escape(_short(case.get("good")))}</span>, first bad <span class="sha">{escape(_short(case.get("bad")))}</span>, agent in <code>{escape(case.get("target", ""))}</code>.</p></footer>
</main>
</body>
</html>
"""


def write(record: dict, path: Path) -> Path:
    path.write_text(render(record))
    return path


def render_index(records: list[tuple[str, dict]]) -> str:
    """The casebook: every case in a folder on one page. `records` are (page file name, record)."""
    rows = ""
    for page, record in records:
        case, lineup = record.get("case", {}), record.get("lineup") or {}
        culprit, fix, damages = lineup.get("culprit"), record.get("fix") or {}, record.get("damages") or {}
        proven = (fix.get("verification") or {}).get("fixed")
        state = "Closed" if proven else "Culprit named" if culprit else "Open"
        who = (f'<span class="sha">{escape(_short(culprit["sha"]))}</span> {escape(culprit["subject"])}' if culprit else "Nobody yet")
        fixed = (f'{escape(fix["kind"])}, {len(record.get("attempts") or [1])} {"try" if len(record.get("attempts") or [1]) == 1 else "tries"}' if proven
                 else "not fixed" if fix else "")
        money = []
        if damages.get("wrongly_paid"):
            money.append(f'{damages["wrongly_paid"]:.2f} paid out wrongly')
        if damages.get("withheld"):
            money.append(f'{damages["withheld"]:.2f} owed and not paid')
        rows += (f'<tr><td><a href="{escape(page)}">{escape(case.get("symptom", page))}</a><div class="small">{len(record.get("suspects", []))} suspects, '
                 f'{lineup.get("replays", 0)} replays</div></td><td>{who}</td><td>{escape(state)}<div class="small">{fixed}</div></td>'
                 f'<td>{escape(", ".join(money))}</td></tr>')
    body = (f'<table class="cases"><thead><tr><th>What was reported</th><th>Which commit</th><th>Where it stands</th><th>What it cost</th></tr></thead><tbody>{rows}</tbody></table>'
            if records else '<p class="empty">No cases yet. Lucky you.</p>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Whodunit casebook</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Alegreya+Sans:wght@400;500;700&family=Courier+Prime:wght@400;700&family=Young+Serif&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<main>
<header>
<p class="label">Whodunit casebook</p>
<h1>Which commit did it, and why</h1>
<p class="lede">{len(records)} {"case" if len(records) == 1 else "cases"} on the refund agent. Each one links to its case file.</p>
</header>
<section class="field"><h2>Cases</h2><div class="body">{body}</div></section>
</main>
</body>
</html>
"""

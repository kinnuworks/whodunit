"""The case file: one static HTML page per case, drawn from the case record."""

import math
from html import escape
from pathlib import Path

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
        kind = "culprit" if suspect["sha"] == culprit else "elsewhere" if not suspect.get("touches_target", True) else "suspect"
        told = f'{n + 1}. {suspect["subject"]} ({_short(suspect["sha"])})'
        if has_odds:
            told += f', {_pct(odds)}'
        if seen:
            told += f', {seen.count("fail")} failures in {len([v for v in seen if v != "skip"])} replays'
        if "skip" in seen:
            told += ", would not build"
        if kind == "elsewhere":
            told += ". Alibi: never touched the agent"
        out.append(f'<g><title>{escape(told)}</title>'
                   f'<rect class="hit" x="{x - step / 2:.1f}" y="{top}" width="{step}" height="{height - top}"/>'
                   f'<rect class="bar {kind}" x="{x - (step - 6) / 2:.1f}" y="{top + bar_h - tall:.1f}" width="{step - 6}" height="{tall:.1f}"/>'
                   f'{marks(x, seen)}</g>')
        if kind == "culprit" or n == 0 or n == count - 1:
            out.append(f'<text class="tick{" strong" if kind == "culprit" else ""}" x="{x:.1f}" y="{top + bar_h + 13}" text-anchor="middle">{n + 1}</text>')
    out.append("</svg>")
    return "".join(out)


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
        named += (f'<p class="small">{lineup.get("replays", 0)} replays across {lineup.get("commits_tested", 0)} commits, '
                  f'{lineup.get("seconds", 0) / 60:.1f} minutes of replay time.{rates}{scan}</p>')
        named += f'<div class="scroll">{lineup_svg(record)}</div>'
        named += ('<p class="key"><span class="swatch culprit"></span>culprit <span class="swatch suspect"></span>suspect '
                  '<span class="swatch elsewhere"></span>never touched the agent <span class="dot fail"></span>failed replay <span class="dot pass"></span>passed replay</p>')
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
        body += f'<p class="small">Written by: {escape(brief.get("model", "unknown"))}. Every sentence cites a span, a commit or a checkpoint. {cut} cut for citing nothing real.</p>'
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
    if fix.get("commit"):
        check = fix.get("verification") or {}
        body = f'<p>{escape(fix["kind"]).capitalize()} committed as <span class="sha">{escape(_short(fix["commit"]))}</span> on branch <code>{escape(fix["branch"])}</code>.</p>'
        if check:
            state = "Proven" if check["fixed"] else "Not proven"
            body += (f'<p><strong>{state}.</strong> {check["failures"]} failures in {check["replays"]} replays of the fix. '
                     f'Probability it is fixed: {_pct(check["probability"])}.{" " + escape(check["note"]) + "." if check.get("note") else ""}</p>')
        if fix.get("regression_case"):
            body += f'<p class="small">Kept as a regression test: <code>{escape(Path(fix["regression_case"]).name)}</code></p>'
    elif fix:
        body = f'<p class="empty">No fix was made. {escape(fix.get("note", ""))}</p>'
    else:
        body = '<p class="empty">Not fixed yet.</p>'
    parts.append(_field("Fix", body))

    # Damages
    if damages:
        if damages["runs"]:
            body = (f'<p>{damages["bad_runs"]} of {damages["runs"]} runs on the culprit or later went bad, which is {damages["bad_share"]:.0%}. '
                    f'They cost about ${damages["wasted_usd"]:.2f} of the ${damages["cost_usd"]:.2f} spent.</p>')
        else:
            body = '<p>No ordinary runs are recorded on the culprit or the commits after it, so there is no damage to count.</p>'
        body += (f'<p class="small">The investigation used {damages["replay_runs"]} replays, about ${damages["replay_usd"]:.2f}. {escape(damages["note"])}</p>')
    else:
        body = '<p class="empty">Not counted yet.</p>'
    parts.append(_field("Damages", body))

    stamp = "Culprit named" if culprit else "Open"
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

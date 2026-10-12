"""The case file: one static HTML page per case, drawn from the case record.

The page is an app screen in a small design system: warm paper, one terracotta accent, cards
with hairline edges, pills for every control, and mono for anything counted. `foundation.css`
is that system as it was given, untouched, and `casefile.css` is what this page adds to it.

The lineup is the centrepiece and keeps its own drawing: every suspect commit is a numbered
position with its short SHA, cleared suspects are struck through, the ones with an alibi are
hatched, each replay is a typed mark, and the culprit is ringed in pencil. The page reads
without any script. The script adds two things, a dark paper and a replay of the investigation
round by round.
"""

import json
import math
import os
import random
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from ..fix import observed
from ..lineup import ChangePoint

HERE = Path(__file__).parent
# The two stylesheets go into the page without their comments. The files themselves keep them.
STYLE = re.sub(r"/\*.*?\*/\n?", "", (HERE / "foundation.css").read_text() + (HERE / "casefile.css").read_text(), flags=re.S)
SCRIPT = (HERE / "casefile.js").read_text()
ROOT = '<html lang="en" data-mood="cream" data-accent="terracotta">'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400..800&family=Geist+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">')
# The mark: an x with a pencil ring round it, which is what the lineup does to the culprit.
MARK = ('<svg class="mark" viewBox="0 0 28 28" width="26" height="26" aria-hidden="true"><path d="M9.5 9.5l9 9M18.5 9.5l-9 9" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'
        '<ellipse cx="14" cy="14" rx="11.6" ry="10" fill="none" stroke="var(--accent-ink)" stroke-width="1.8" transform="rotate(-14 14 14)"/></svg>')
CHECK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         '<path d="M5 12.5l4.5 4.5L19 7.5"/></svg>')
CAP = 9  # typed marks that fit under one suspect before they are written as a glyph and a count
MARKS_GAP = 26  # room between a suspect's SHA and its marks, which is where the bottom of the pencil ring goes


def _short(sha: str | None) -> str:
    return (sha or "")[:12]


def _pct(value: float) -> str:
    if value >= 0.9995:
        return "over 99.9%"
    return f"{value:.1%}" if value < 0.995 else f"{value:.2%}"


def _field(label: str, body: str, margin: str = "") -> str:
    aside = f'<div class="margin">{margin}</div>' if margin else ""
    return f'<section class="field card" id="{escape(label.lower())}"><h2>{escape(label)}</h2><div class="body">{body}</div>{aside}</section>'


def _nav(links: list[tuple[str, str]], action: str) -> str:
    """The floating pill at the top: the brand, a few anchors, the paper toggle and one small action."""
    anchors = "".join(f'<a href="{escape(href)}">{escape(label)}</a>' for label, href in links)
    return ('<nav class="nav" aria-label="Whodunit"><div class="nav__bar">'
            f'<a class="nav__brand" href="index.html">{MARK}<span>Whodunit</span></a><div class="nav__links">{anchors}</div>'
            '<div class="nav__end"><button type="button" class="btn btn-sm btn-ghost" data-theme-toggle aria-pressed="false" hidden>Dark</button>'
            f'{action}</div></div></nav>')


def _typed(text: str) -> str:
    return f'<pre class="typed">{escape(text.rstrip())}</pre>'


def _typed_inline(text: str) -> str:
    return f'<span class="cite">{escape(text)}</span>'


def _when(seconds: float | None) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%-d %b %Y, %H:%M UTC") if seconds else ""


def kept(attempt: dict | None) -> bool:
    """A fix is kept when it cleared its own bar and the do-no-harm check, if one was run, found nothing broken."""
    attempt = attempt or {}
    return bool((attempt.get("verification") or {}).get("fixed")) and not (attempt.get("harm") or {}).get("broken")


def stamp(record: dict) -> tuple[str, str]:
    """What the status badge says, and whether it is the filled one. Only a case with a kept fix is closed."""
    lineup = record.get("lineup") or {}
    if lineup.get("clear"):
        return "No commit did it", ""
    if not lineup.get("culprit"):
        return "Open", ""
    if kept(record.get("fix")):
        return "Case closed", "closed"
    return ("Open, not fixed", "") if record.get("fix") or record.get("attempts") else ("Culprit named", "")


def harm_said(harm: dict) -> str:
    """The do-no-harm check in a sentence or two."""
    n = harm["checked"]
    said = f'Checked against {n} other {"request" if n == 1 else "requests"}: the inputs of the other cases and a few ordinary requests that should succeed.'
    if harm["broken"]:
        k = len(harm["broken"])
        said += f' The fix made {k} other {"request" if k == 1 else "requests"} go wrong more often than before, so it was not kept: ' + "; ".join(
            f'"{b["text"]}" went wrong in {b["fix"][0]} of {b["fix"][1]} replays on the fix and in {b["before"][0]} of {b["before"][1]} before it' for b in harm["broken"]) + "."
    else:
        said += " The fix broke none of them."
    if harm["already_failing"]:
        k = len(harm["already_failing"])
        said += f' {k} {"was" if k == 1 else "were"} already going wrong before the fix. That is some other bug, and is not held against this one.'
    if harm["unclear"]:
        k = len(harm["unclear"])
        said += f' {k} went wrong once or twice on the fix commit, which is too few to say the fix did it.'
    return said


def money_said(damages: dict) -> str:
    """The damage in the shop's money, in a few words. Empty if no money moved."""
    parts = []
    if damages.get("wrongly_paid"):
        parts.append(f'{damages["wrongly_paid"]:.2f} refunded to the wrong people')
    if damages.get("withheld"):
        parts.append(f'{damages["withheld"]:.2f} owed and not refunded')
    return " and ".join(parts)


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
    elif lineup.get("clear"):
        steps.append(("lineup", f'No commit did it. After {lineup.get("replays", 0)} replays, {lineup.get("note", "the good ref fails as often as the bad one")}.'))
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
            broke = (attempt.get("harm") or {}).get("broken")
            line = f'Try {n}, a {attempt["kind"]}: {observed(seen.get("failures", 0), seen.get("replays", 0))} '
            if broke:
                line += f'Not kept, because it made {len(broke)} other {"request" if len(broke) == 1 else "requests"} go wrong more often.'
            else:
                line += "Kept." if seen.get("fixed") else "Not kept."
            steps.append(("fix", line))
    if tries and not any(kept(a) for a in tries):
        steps.append(("fix", f'No fix cleared the bar in {len(tries)} {"try" if len(tries) == 1 else "tries"}. The case stays open.'))
    fix = record.get("fix") or {}
    again = [c for c in record.get("checks", []) if c["ref"] == fix.get("commit")]
    if again:
        steps.append(("check", f'Replayed again as a regression test: {sum(c["failures"] for c in again)} failures in {sum(c["runs"] for c in again)} replays.'))
    if damages.get("case_runs"):
        money = [f'{damages[key]:.2f} {words}' for key, words in (("wrongly_paid", "refunded wrongly"), ("withheld", "owed and not refunded")) if damages.get(key)]
        steps.append(("damages", f'{damages["case_bad"]} of {damages["case_runs"]} ordinary runs that asked this failed the check' + (f': {", ".join(money)}.' if money else ".")))
    return steps


# The lineup


def mark_lines(ordinary: list[str], replays: list[str]) -> list[tuple[str, str]]:
    """The lines typed under one suspect, top to bottom, as (text, css class).

    x is a failed run and o a passed one. Ordinary runs come first, in grey, then replays.
    When there are more marks than fit, each kind is written once with its count underneath,
    so a commit that was replayed a hundred times is not drawn as if it had been replayed nine.
    The script that replays an investigation has the same rule, and the two have to agree.
    """
    marks = [(m, "ord " + ("fail" if m == "x" else "pass")) for m in ordinary] + [(m, {"x": "fail", "o": "pass"}.get(m, "skip")) for m in replays]
    if len(marks) <= CAP:
        return marks
    lines = []
    for glyph, css, among in (("x", "ord fail", ordinary), ("o", "ord pass", ordinary), ("x", "fail", replays), ("o", "pass", replays), ("-", "skip", replays)):
        count = among.count(glyph)
        if count:
            lines += [(glyph, css), (str(count), css + " count")]
    return lines


def _ring(cx: float, cy: float, rx: float, ry: float, seed: str) -> str:
    """An ellipse drawn the way a pencil draws one: a little uneven, and overlapping where it ends."""
    rng = random.Random(seed)
    points = []
    for k in range(29):
        angle = -2.2 + k * (2 * math.pi * 1.09 / 28)
        wobble = 1 + rng.uniform(-0.03, 0.03) + 0.045 * k / 28
        points.append((cx + rx * wobble * math.cos(angle), cy + ry * wobble * math.sin(angle)))
    path = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(points[1:], points[2:]):
        path += f" Q{x0:.1f},{y0:.1f} {(x0 + x1) / 2:.1f},{(y0 + y1) / 2:.1f}"
    return path


def _glyph(verdict: str) -> str | None:
    return {"fail": "x", "pass": "o", "skip": "-"}.get(verdict)


def lineup_parts(record: dict) -> dict:
    """Everything the lineup is drawn from: one column per commit, the last good ref first."""
    suspects = record.get("suspects", [])
    lineup = record.get("lineup") or {}
    culprit = (lineup.get("culprit") or {}).get("sha")
    good = (record.get("case") or {}).get("good", "")
    column = {good: 0} | {s["sha"]: n + 1 for n, s in enumerate(suspects)}
    ordinary = [[] for _ in range(len(suspects) + 1)]
    for run in record.get("witnessed") or []:
        if run["sha"] in column:
            ordinary[column[run["sha"]]].append("x" if run["failed"] else "o")
    replays = [[] for _ in range(len(suspects) + 1)]
    for replay in record.get("replays", []):
        glyph = _glyph(replay["verdict"])
        if glyph and replay["sha"] in column:
            replays[column[replay["sha"]]].append(glyph)
    return {"suspects": suspects, "culprit": culprit, "good": good, "column": column, "ordinary": ordinary, "replays": replays,
            "clear": bool(lineup.get("clear")), "named": bool(culprit)}


def lineup_svg(record: dict) -> str:
    """The lineup. Every suspect is a numbered position with its short SHA, oldest on the left."""
    parts = lineup_parts(record)
    suspects, culprit = parts["suspects"], parts["culprit"]
    if not suspects:
        return ""
    count = len(suspects)
    step = max(19, min(46, 1100 // (count + 1)))
    pad, top, hash_h, line_h = 10, 62, 58, 12
    marks_top = top + 26 + hash_h + MARKS_GAP
    width = pad * 2 + (count + 1) * step
    height = marks_top + (CAP + 1) * line_h + 4
    xs = [pad + n * step + step / 2 for n in range(count + 1)]
    out = [f'<svg class="lineup{"" if parts["named"] else " unnamed"}" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
           f'aria-label="The lineup: {count} suspect commits, oldest on the left. The table below it holds the same information.">',
           '<defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="hatch-line" x1="0" y1="0" x2="0" y2="5"/></pattern></defs>']

    def column(n: int, css: str, title: str, number: str, label: str, odds: str, label_css: str = "hash") -> str:
        x = xs[n]
        lines = "".join(f'<text class="mark {klass}" x="{x:.1f}" y="{marks_top + k * line_h}">{text}</text>'
                        for k, (text, klass) in enumerate(mark_lines(parts["ordinary"][n], parts["replays"][n])))
        # A column is not a tab stop. The lineup's scroll box is one, and the table under it has every column's details.
        return (f'<g class="col {css}"><title>{escape(title)}</title>'
                f'<rect class="hit" x="{x - step / 2:.1f}" y="{top - 14}" width="{step}" height="{height - top + 14}"/>'
                f'<rect class="hatch" x="{x - step / 2 + 2:.1f}" y="{top + 2}" width="{step - 4}" height="{hash_h + 30}"/>'
                f'<text class="pct" x="{x:.1f}" y="{top - (3 if n % 2 else 15)}">{odds}</text>'
                f'<text class="num" x="{x:.1f}" y="{top + 16}">{number}</text>'
                f'<text class="{label_css}" transform="translate({x + 4:.1f},{top + 26 + hash_h}) rotate(-90)">{escape(label)}</text>'
                f'<line class="strike" x1="{x - 7:.1f}" y1="{top + 12}" x2="{x + 7:.1f}" y2="{top + 12}"/>'
                f'<line class="strike" x1="{x + 0.5:.1f}" y1="{top + 26}" x2="{x + 0.5:.1f}" y2="{top + 28 + hash_h}"/>'
                f'<g class="marks">{lines}</g></g>')

    seen = parts["replays"][0]
    out.append(column(0, "good", f'The last good commit ({_short(parts["good"])}): {seen.count("x")} failures in {len(seen)} replays', "", "last good", "", "good-label"))
    for n, suspect in enumerate(suspects, 1):
        odds = suspect.get("probability", 1.0 if suspect["sha"] == culprit else 0.0)
        seen, usual = parts["replays"][n], parts["ordinary"][n]
        excuse = suspect.get("alibi") or ("" if suspect.get("touches_target", True) else "never touched the agent's folder")
        guilty = suspect["sha"] == culprit
        cleared = not guilty and (parts["named"] or parts["clear"] or odds < 0.01)
        told = f'{n}. {suspect["subject"]} ({_short(suspect["sha"])})'
        if "probability" in suspect:
            told += f', {_pct(odds)}'
        if seen:
            told += f', {seen.count("x")} failures in {seen.count("x") + seen.count("o")} replays'
        if "-" in seen:
            told += ", would not build"
        if usual:
            told += f', {usual.count("x")} of {len(usual)} ordinary runs went wrong'
        if excuse:
            told += f". Alibi: {excuse}"
        css = " ".join(filter(None, ["culprit" if guilty else "", "cleared" if cleared else "", "alibi" if excuse and not guilty else ""]))
        shown = _pct(odds) if guilty and "probability" in suspect else f"{odds:.0%}" if odds >= 0.05 and not parts["named"] else ""
        out.append(column(n, css, told, str(n), suspect["sha"][:7], shown))
    if culprit:
        n = parts["column"][culprit]
        x, cy = xs[n], top + 8 + (hash_h + 26) / 2
        rx, ry = step / 2 + 7, (hash_h + 38) / 2
        # The subject goes on whichever side of the culprit has more room, cut to what fits there.
        left = width - x >= x
        lx, ly = (x + 46, 22) if left else (x - 46, 22)
        fits = max(14, int(((width - lx) if left else lx) / 7.9) - 9)
        subject = suspects[n - 1]["subject"]
        subject = subject if len(subject) <= fits else subject[:fits - 1].rstrip() + "…"
        out.append('<g class="named">'
                   f'<path class="ring" pathLength="1" d="{_ring(x, cy, rx, ry, culprit)}"/>'
                   f'<path class="leader" pathLength="1" d="M{x + (rx * 0.55 if left else -rx * 0.55):.1f},{cy - ry * 0.92:.1f} Q{x + (16 if left else -16):.1f},{ly + 14} {lx + (-6 if left else 6):.1f},{ly + 4}"/>'
                   f'<text class="who" x="{lx:.1f}" y="{ly + 8}" text-anchor="{"start" if left else "end"}"><tspan class="sha">{escape(culprit[:7])}</tspan> {escape(subject)}</text></g>')
    out.append("</svg>")
    return "".join(out)


def rounds_of(record: dict) -> tuple[list[dict], bool]:
    """The rounds to replay, and whether they had to be worked out again: (rounds, reconstructed).

    A record made since the investigation became a trace keeps its rounds. An older one keeps
    every replay with the time it started, which is enough to run the lineup's own model over
    them again in order. That is trusted only if it ends where the record ended, with every
    suspect's probability matching what the record holds. Otherwise there is nothing to replay.
    Records whose suspects had alibis from entire-graph are left alone, because the weights
    those alibis carried were not kept.
    """
    if record.get("rounds"):
        return record["rounds"], False
    suspects, lineup = record.get("suspects") or [], record.get("lineup") or {}
    if not suspects or "probability" not in suspects[0] or any(s.get("alibi") and s.get("touches_target", True) for s in suspects):
        return [], False
    good = (record.get("case") or {}).get("good")
    place = {good: -1} | {s["sha"]: n for n, s in enumerate(suspects)}
    state = ChangePoint(len(suspects), [1.0 if s.get("touches_target", True) else 0.05 for s in suspects])
    for run in record.get("witnessed") or []:
        if run["sha"] in place:
            state.observe(place[run["sha"]], run["failed"])
    judged = sorted((r for r in record.get("replays", []) if r["verdict"] in ("pass", "fail") and r["sha"] in place), key=lambda r: r.get("started", 0))
    judged = judged[:lineup.get("replays", len(judged))]  # replays made after the lineup, for the brief, are not part of it
    rounds, batch = [], []

    def close() -> None:
        if batch:
            posterior = state.posterior()
            ranked = sorted(range(len(posterior)), key=lambda i: -posterior[i])[:3]
            rounds.append({"commits": [r["sha"] for r in batch], "verdicts": [r["verdict"] for r in batch],
                           "top": [[suspects[i]["sha"], round(posterior[i], 4)] for i in ranked], "posterior": [round(share, 4) for share in posterior]})
            batch.clear()

    for replay in judged:
        if batch and (replay.get("started", 0) - batch[-1].get("started", 0) > 1.5 or len(batch) >= 12):
            close()  # replays that started together were one round
        batch.append(replay)
        state.observe(place[replay["sha"]], replay["verdict"] == "fail")
    close()
    if not rounds or any(abs(share - s["probability"]) > 0.002 for share, s in zip(state.posterior(), suspects)):
        return [], False
    return rounds, True


def playback(record: dict) -> dict | None:
    """What the script needs to replay the investigation round by round, or None if there are no rounds to replay."""
    rounds, again = rounds_of(record)
    parts = lineup_parts(record)
    if not rounds or not parts["suspects"]:
        return None
    count = len(parts["suspects"])
    step = max(19, min(46, 1100 // (count + 1)))
    number = {sha: n for n, sha in enumerate(s["sha"] for s in parts["suspects"])}
    made = []
    for one in rounds:
        cols = [parts["column"].get(sha) for sha in one["commits"]]
        pairs = [(c, _glyph(v)) for c, v in zip(cols, one["verdicts"]) if c is not None and _glyph(v)]
        if not pairs:
            continue
        who = sorted({c for c, _ in pairs})
        say = "Replayed " + " and ".join("the last good commit" if c == 0 else f"suspect {c}" for c in who) + ":"
        lead_sha, share = one["top"][0]
        made.append({"c": [c for c, _ in pairs], "v": [g for _, g in pairs], "p": one["posterior"],
                     "say": say, "lead": f"Suspect {number[lead_sha] + 1} leads at {share:.0%}."})
    if not made:
        return None
    usual = sum(len(column) for column in parts["ordinary"])
    return {"rounds": made, "ordinary": parts["ordinary"], "cap": CAP, "pace": 260, "lineHeight": 12, "marksTop": 62 + 26 + 58 + MARKS_GAP,
            "x": [round(10 + n * step + step / 2, 1) for n in range(count + 1)],
            "before": (f"Before any replay: {usual} ordinary runs, in grey." if usual else "Before any replay.")
            + (" The rounds were worked out again from the stored replays." if again else "")}


def suspects_table(record: dict) -> str:
    """The lineup again as a table, for anyone who cannot use the drawing."""
    parts = lineup_parts(record)
    rows = ""
    for n, suspect in enumerate(parts["suspects"], 1):
        seen, usual = parts["replays"][n], parts["ordinary"][n]
        guilty = suspect["sha"] == parts["culprit"]
        odds = suspect.get("probability")
        cleared = not guilty and (parts["named"] or parts["clear"] or (odds is not None and odds < 0.01))
        excuse = suspect.get("alibi") or ("" if suspect.get("touches_target", True) else "never touched the agent's folder")
        status = "Culprit" if guilty else "Cleared" if cleared else "Still a suspect"
        if excuse and not guilty:
            status += f". Alibi: {excuse}"
        replays = f'{seen.count("x")} failed, {seen.count("o")} passed' if seen else "not replayed"
        if "-" in seen:
            replays += ", would not build"
        if usual:
            replays += f'. Ordinary runs: {usual.count("x")} of {len(usual)} went wrong'
        rows += (f'<tr class="{"is-culprit" if guilty else "is-cleared" if cleared else ""}"><td class="n">{n}</td><td class="sha">{escape(_short(suspect["sha"]))}</td>'
                 f'<td>{escape(suspect["subject"])}</td><td>{escape(status)}</td><td class="n">{_pct(odds) if odds is not None else ""}</td><td>{escape(replays)}</td></tr>')
    return ('<details class="table"><summary>The lineup as a table</summary><div class="card table-card"><table class="suspects"><thead><tr><th>No.</th><th>Commit</th><th>Subject</th>'
            f'<th>Status</th><th>Odds</th><th>Runs</th></tr></thead><tbody>{rows}</tbody></table></div></details>')


# Exhibits

SPAN = re.compile(r"^\s*([0-9a-f]{8}) ([A-Z_]+) (\S+)")


def exhibit_steps(outline: str) -> list[dict]:
    """A run's outline as steps a person can read down: what the model did and what each tool gave back.

    Each step is {"id", "what", "text", "sign"}. `sign` is what the step amounts to, used to find
    where two runs part: "calls issue_refund", "issue_refund ok", "replies".
    """
    spans = []
    for line in outline.splitlines():
        found = SPAN.match(line)
        if found:
            spans.append({"id": found.group(1), "kind": found.group(2), "name": found.group(3), "in": "", "out": "", "bad": " error" in line})
        elif spans and line.strip().startswith(("in:", "out:")):
            key, _, value = line.strip().partition(":")
            spans[-1][key] = value.strip()
    steps = []
    for span in spans:
        if span["kind"] == "WORKFLOW":
            try:
                asked = json.loads(span["in"]).get("request", span["in"])
            except (json.JSONDecodeError, AttributeError):
                asked = span["in"]
            steps.append({"id": span["id"], "what": "Asked", "text": asked, "sign": "asked"})
        elif span["kind"] == "LLM":
            said = span["out"].removeprefix("assistant:").strip()
            talk, arrow, call = said.rpartition("→")
            if arrow:
                tool = call.strip().split("(")[0]
                steps.append({"id": span["id"], "what": "The model calls", "text": call.strip(), "sign": f"calls {tool}"})
            else:
                steps.append({"id": span["id"], "what": "The model replies", "text": said, "sign": "replies"})
        elif span["kind"] in ("TOOL", "MCP_TOOL"):
            failed = span["bad"] or span["out"].startswith('{"error"')
            steps.append({"id": span["id"], "what": f'{span["name"]} {"fails" if failed else "returns"}', "text": span["out"], "sign": f'{span["name"]} {"fails" if failed else "ok"}'})
    return steps


def _exhibits(evidence: dict) -> tuple[str, str]:
    """Exhibit A, the passing run, and Exhibit B, the failing run, with the first step where they part ringed in the accent. Returns (body, margin note)."""
    shown = [(letter, label, evidence.get(key)) for letter, label, key in (("A", "the passing run", "passing_run"), ("B", "the failing run", "failing_run")) if evidence.get(key)]
    if not shown:
        return "", ""
    listed = {letter: exhibit_steps(run["outline"]) for letter, _, run in shown}
    parts_at = None
    if len(shown) == 2:
        a, b = listed["A"], listed["B"]
        parts_at = next((n for n in range(max(len(a), len(b))) if n >= len(a) or n >= len(b) or a[n]["sign"] != b[n]["sign"]), None)
    body = '<div class="exhibits">'
    for letter, label, run in shown:
        items = "".join(
            f'<li{" class=\"parts\"" if n == parts_at else ""}><span class="what">{escape(step["what"])}</span> {escape(step["text"])} <span class="cite">{escape(step["id"])}</span></li>'
            for n, step in enumerate(listed[letter]))
        body += (f'<div class="exhibit"><h3>Exhibit {letter} <span>{escape(label)}</span></h3>'
                 f'<p class="small">Run <span class="cite">{escape(run["trace_id"][:12])}</span> at commit <span class="sha">{escape(_short(run["commit"]))}</span></p><ol>{items}</ol></div>')
    body += "</div>"
    note = ""
    if parts_at is not None:
        def did(steps: list[dict]) -> str:
            return f'{steps[parts_at]["what"].lower()} {steps[parts_at]["text"][:60]}' if parts_at < len(steps) else "has already stopped"
        note = (f'<p class="parted">The two runs part at step {parts_at + 1}. In Exhibit A {escape(did(listed["A"]))}. In Exhibit B {escape(did(listed["B"]))}.</p>')
    raw = "".join(f'<h3>Exhibit {letter}, as traced</h3>{_typed(run["outline"])}' for letter, _, run in shown)
    body += f'<details><summary>The raw outlines</summary>{raw}</details>'
    return body, note


def _footnotes(brief: dict, evidence: dict, motive: dict) -> tuple[str, str]:
    """The brief with a superscript number after each sentence in place of its ids, and the numbered list of what they are."""
    kinds: dict[str, str] = {}
    for key, label in (("failing_run", "the failing run"), ("passing_run", "the passing run")):
        run = evidence.get(key)
        if run:
            kinds[run["trace_id"][:12]] = label
            for found in re.findall(r"^\s*([0-9a-f]{8}) [A-Z_]+ ", run.get("outline", ""), flags=re.M):
                kinds.setdefault(found, f"a span in {label}")
    if evidence.get("culprit"):
        kinds[evidence["culprit"][:12]] = "the culprit commit"
        kinds[evidence.get("parent", "")[:12]] = "its parent commit"
    if evidence.get("checkpoint"):
        kinds[evidence["checkpoint"]] = "the Entire checkpoint"
    for step in list(evidence.get("steps", [])) + list(motive.get("steps", [])):
        if step.get("id"):
            kinds.setdefault(step["id"], "a step in the coding session")
    order: list[str] = []
    text = ""
    for sentence in brief["sentences"]:
        marks = []
        for cited in sentence["cites"]:
            if cited not in order:
                order.append(cited)
            n = order.index(cited) + 1
            marks.append(f'<a href="#note-{n}" aria-label="Note {n}">{n}</a>')
        text += f'<p>{escape(sentence["text"])}<sup>{" ".join(marks)}</sup></p>'
    notes = "".join(f'<li id="note-{n}"><b>{escape(cited)}</b> {escape(kinds.get(cited, "an id in the evidence"))}</li>' for n, cited in enumerate(order, 1))
    return text, f'<ol class="notes" aria-label="What the brief cites">{notes}</ol>'


def meta(title: str, description: str) -> str:
    """Title, description and the tags a link preview is built from."""
    site = os.environ.get("WHODUNIT_SITE", "").rstrip("/")
    image = f"{site}/og.png" if site else "og.png"
    return (f'<title>{escape(title)}</title>\n<meta name="description" content="{escape(description)}">\n'
            f'<meta property="og:type" content="article">\n<meta property="og:title" content="{escape(title)}">\n'
            f'<meta property="og:description" content="{escape(description)}">\n<meta property="og:image" content="{escape(image)}">\n'
            '<meta name="twitter:card" content="summary_large_image">')


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

    # Suspects: who was named, and what narrowed the field
    if culprit:
        sure = f' Confidence: {_pct(culprit["probability"])}.' if "probability" in culprit else ""
        named = (f'<p class="verdict"><span class="sha">{escape(_short(culprit["sha"]))}</span> {escape(culprit["subject"])}</p>'
                 f'<p>Suspects: {len(suspects)}. Cleared: {len(suspects) - 1}.{sure}</p>')
    elif lineup.get("clear"):
        told = lineup.get("note", "")
        named = (f'<p class="verdict">No commit did it.</p><p>{escape(told[:1].upper() + told[1:])}. All {len(suspects)} suspects are cleared. '
                 'Something outside these commits changed, and this is what the runs say about it:</p>'
                 + '<ul class="steps">' + "".join(f"<li>{escape(line)}</li>" for line in lineup.get("differs", [])) + "</ul>")
    elif lineup:
        named = f'<p class="verdict open">Nobody named yet.</p><p>{escape(lineup.get("note") or "The replays ran out before one suspect stood clear.")}</p>'
    else:
        named = '<p class="empty">No lineup yet. Run <code>whodunit lineup</code> on this case.</p>'
    if lineup:
        rates = ""
        if "failure_rate_from" in lineup and culprit:
            rates = f' From this commit on it fails about {lineup["failure_rate_from"]:.0%} of the time. Before it, about {lineup["failure_rate_before"]:.0%}.'
        if lineup.get("traffic_runs"):
            who = f' The ordinary runs were sent by <code>{escape(sent_by)}</code>, a script that plays customers.' if sent_by else ""
            named += (f'<p class="small">Before any replay, {lineup["traffic_runs"]} ordinary runs had already asked this, '
                      f'and {lineup["traffic_failures"]} of them went wrong. They were used as evidence at no cost.{who}</p>')
        named += (f'<p class="small">{lineup.get("replays", 0)} replays across {lineup.get("commits_tested", 0)} commits, '
                  f'{lineup.get("seconds", 0) / 60:.1f} minutes of replay time.{rates}</p>')
        if "voided" in lineup:
            lost = lineup["voided"]
            named += (f'<p class="small">Voided replays: {lost}. ' + (
                "No replay hit a provider or network error." if not lost else
                f'{"That one" if lost == 1 else "Those"} hit a provider or network error and {"was" if lost == 1 else "were"} run again. A voided replay is never evidence about a commit.')
                + (f' {lineup["timeouts"]} ran out of time and got one more try with double the limit.' if lineup.get("timeouts") else "") + "</p>")
        excused = [s for s in suspects if s.get("alibi") and s["sha"] != (culprit or {}).get("sha")]
        if excused:
            rows = "".join(f'<li><span class="sha">{escape(_short(s["sha"]))}</span> {escape(s["subject"])}: {escape(s["alibi"])}.</li>' for s in excused)
            named += f'<details><summary>Alibis: {len(excused)} of {len(suspects)} suspects started with less suspicion</summary><ul class="steps">{rows}</ul></details>'
        split = lineup.get("inputs_disagree")
        if split:
            # Each input was given a posterior of its own, and two of them cannot have broken at the same commit.
            subject = {s["sha"]: s["subject"] for s in suspects}
            rows = "".join(f'<li>{_typed_inline(text)} points at <span class="sha">{escape(_short(sha))}</span> {escape(subject.get(sha, ""))}</li>'
                           for text, sha in zip(split["inputs"], split["commits"]))
            named += ('<p><strong>The inputs point at different commits.</strong> There may be two regressions in this range. '
                      f'The lineup assumes one, so a culprit named above is at most one of them.</p><ul class="steps">{rows}</ul>')
        second = lineup.get("second_look")
        if second:
            named += f'<p><strong>{escape(second["said"])}</strong></p>'
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
        checked = " Quote checked against the transcript." if motive.get("quote_checked") else ""
        body = (f'<p>Someone asked the coding agent for this:</p>{_typed(motive["request"])}'
                f'<p class="small">Entire checkpoint <span class="cite">{escape(motive.get("checkpoint") or "")}</span>, asked at {escape((motive.get("request_time") or "")[:16].replace("T", " "))} UTC.{checked}{link}</p>')
        traced = motive.get("provenance") or {}
        if traced.get("lines"):
            # A second route to the same answer: what Entire says about each line the commit changed.
            if traced["agree"] == traced["lines"]:
                said = f'Line by line, <code>entire why</code> puts all {traced["lines"]} changed lines that were checked behind this commit and this checkpoint.'
            else:
                where = ", ".join(f'{d["file"]}:{d["line"]} (commit {d["commit"]}, checkpoint {d["checkpoint"] or "none"})' for d in traced["disagree"][:4])
                said = (f'Line by line, <code>entire why</code> puts {traced["agree"]} of the {traced["lines"]} changed lines that were checked behind this commit and this checkpoint. '
                        f'It disagrees on {escape(where)}.')
            if traced.get("request_agrees") is False:
                said += " The request it holds for those lines is not the one quoted above."
            body += f'<p class="small">{said}</p>'
        if motive.get("note"):
            body += f'<p class="small">{escape(motive["note"])}</p>'
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

    # Brief: the sentences, with what each one cites in the margin
    if brief.get("sentences"):
        text, notes = _footnotes(brief, evidence, motive)
        body = f'<p class="headline">{escape(brief.get("headline", ""))}</p>{text}'
        cut = len(brief.get("dropped", []))
        sent_back = brief.get("rejected") or []
        again = (f' A first draft was sent back because it {escape(sent_back[0]["problem"])}.' if sent_back else "")
        if brief.get("writer") == "template" or str(brief.get("model", "")).startswith("none"):
            how = "Written from a fixed template, with no model" + (f', because {escape(brief["why"])}' if brief.get("why") else "")
        else:
            how = "Written by a model"
        body += (f'<p class="small">{how}. Every sentence cites a span, a commit or a checkpoint, '
                 f'and is held against what the lineup measured. {cut} cut by those checks.{again}</p>')
        parts.append(_field("Brief", body, notes))
    else:
        parts.append(_field("Brief", '<p class="empty">No brief yet.</p>'))

    # Evidence: Exhibit A, the passing run, and Exhibit B, the failing run
    body, note = _exhibits(evidence)
    cloud = evidence.get("cloud")
    if cloud and body:
        if cloud.get("sent"):
            runs = []
            for label, key in (("the failing run", "failing_run"), ("the passing run", "passing_run")):
                if key in cloud.get("trace_ids", {}):
                    shown = f'<span class="cite">{escape(cloud["trace_ids"][key])}</span>'
                    link = (cloud.get("links") or {}).get(key)
                    runs.append(f'{label} {f"""<a href="{escape(link)}">{shown}</a>""" if link else shown}')
            body += f'<p class="small">Both runs were sent from neatroots to neatlogs cloud: {" and ".join(runs)}.</p>'
        else:
            body += ('<p class="small">These two runs are in neatroots on the machine that ran the case. They have not been sent to neatlogs cloud. '
                     f'neatroots said: {escape(cloud.get("note", ""))}</p>')
    if evidence.get("diff"):
        body += f'<details{" open" if not note and not body else ""}><summary>The culprit\'s diff</summary>{_typed(evidence["diff"])}</details>'
    for said in evidence.get("notes", []):
        body += f'<p class="small">{escape(said)}</p>'
    parts.append(_field("Evidence", body or '<p class="empty">Nothing collected yet.</p>', note))

    # Ruling
    if ruling:
        again = "" if ruling.get("asked_now") else f' Nobody was asked this time. The rule was set on {escape(ruling["decided_on"])} in case {escape(ruling["first_case"])}.'
        what = "Revert it." if ruling["ruling"] == "revert" else "Keep what it was for, and patch the bug."
        article = "an" if ruling["kind"][:1] in "aeiou" else "a"
        reverted = ruling["ruling"] == "revert"
        body = (f'<p class="verdict small-verdict">{what}</p>'
                f'<p class="choice"><span class="chip{" is-chosen" if reverted else ""}">Revert</span><span class="chip{"" if reverted else " is-chosen"}">Patch</span></p>'
                f'<p>This is the owner\'s standing rule for {article} {escape(ruling["kind"])} change.{again}</p>')
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
                broke = (attempt.get("harm") or {}).get("broken")
                how = (f'<span class="sha">{escape(_short(attempt["commit"]))}</span>, {observed(seen.get("failures", 0), seen.get("replays", 0))} '
                       f'{"Not kept" if broke or not seen.get("fixed") else "Kept"}.')
                if attempt.get("harm"):
                    how += f' {escape(harm_said(attempt["harm"]))}'
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
        if fix.get("harm"):
            body += f'<p>{escape(harm_said(fix["harm"]))}</p>'
        elif check.get("fixed"):
            body += '<p class="small">Only this case\'s own requests were replayed on the fix. Nothing was checked for what else it might have broken.</p>'
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

    # Damages: the money first, then what the runs cost. Only runs that fail this case's own check count.
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
            body = ""
            if money_said(damages):
                body += f'<p class="money">{escape(money_said(damages))}</p>'
            body += (f'<p>{damages["case_bad"]} of the {damages["case_runs"]} ordinary runs that asked what this case asks, on the culprit or later, failed its check.</p>')
            if "case_bad_usd" in damages:
                body += f'<p class="small">Those {damages["case_bad"]} runs cost about ${damages["case_bad_usd"]:.2f} in tokens.</p>'
        if damages["runs"]:
            body += (f'<p class="small">{damages["runs"]} ordinary runs of every kind are on record for the same commits. '
                     'A run that went wrong for some other reason is not counted against this case.</p>')
            if sent_by:
                body += (f'<p class="small">The ordinary runs were sent by <code>{escape(sent_by)}</code>, a script that plays customers against each commit. '
                         'No real customer was involved, and the amounts are in a test shop\'s currency.</p>')
        body += f'<p class="small">The investigation used {damages["replay_runs"]} replays, about ${damages["replay_usd"]:.2f}. {escape(damages["note"])}</p>'
    else:
        body = '<p class="empty">Not counted yet.</p>'
    parts.append(_field("Damages", body))

    # Log: what happened, in order, worked out from the record as it stands
    happened = timeline(record)
    if happened:
        rows = "".join(f'<li><span class="step">{escape(step)}</span><span>{escape(text)}</span></li>' for step, text in happened)
        traced = record.get("trace") or {}
        if traced.get("trace_id"):
            # The investigation is a trace of its own, with a span for each of these steps and each round of the lineup.
            place = {"cloud": "neatlogs cloud", "neatroots": "neatroots on the machine that ran it"}.get(traced.get("where"), "the trace collector")
            name = f'<span class="cite">{escape(traced["trace_id"])}</span>'
            if traced.get("link"):
                name = f'<a href="{escape(traced["link"])}">{name}</a>'
            rows += f'<li><span class="step">trace</span><span>This investigation is itself a trace in {place}: {name}</span></li>'
        parts.append(_field("Log", f'<ol class="steps log">{rows}</ol>'))

    # The header: status, the facts and the three numbers that matter
    words, red = stamp(record)
    started = [r["started"] for r in record.get("replays", []) if r.get("started")]
    opened = _when(min(started)) if started else ""
    closed = _when(record["replays_until_ms"] / 1000) if red and record.get("replays_until_ms") else ""
    number = f'{case["number"]:03d}' if isinstance(case.get("number"), int) else case.get("id", "")
    rows = [("Case no.", number if isinstance(case.get("number"), int) else ""), ("File", case.get("id", "")), ("Opened", opened), ("Closed", closed or ("not yet" if lineup else "")),
            ("Suspects", f'{len(suspects)}' + (f', {len(suspects) - 1} cleared' if culprit else f', all {len(suspects)} cleared' if lineup.get("clear") else ""))]
    if lineup:
        whole = f', {damages["replay_runs"]} in all' if damages.get("replay_runs") else ""
        rows.append(("Replays", f'{lineup.get("replays", 0)} to {"name the culprit" if culprit else "get this far"}{whole}'))
    if damages.get("replay_usd") is not None and damages:
        rows.append(("Cost of the investigation", f'about ${damages["replay_usd"]:.2f}'))
    if damages:
        rows.append(("Damage", money_said(damages) or ("none seen" if damages.get("case_runs") else "none that could be counted")))
    facts = "".join(f'<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>' for label, value in rows if value != "")
    figures = ""
    if lineup:
        figures += f'<div><dt>{lineup.get("replays", 0)}</dt><dd>replays to {"name the culprit" if culprit else "get this far"}</dd></div>'
        if culprit and "probability" in culprit:
            figures += f'<div><dt>{_pct(culprit["probability"])}</dt><dd>sure it is this commit</dd></div>'
        elif lineup.get("remaining") and not culprit:
            figures += f'<div><dt>{_pct(lineup["remaining"][0].get("probability", 0))}</dt><dd>on the leading suspect, short of the 95% it takes to name one</dd></div>'
        if "linear_scan_commits" in lineup:
            figures += (f'<div><dt>{lineup["linear_scan_commits"]}</dt><dd>commits a scan from the oldest suspect would have tested. '
                        f'This lineup tested {lineup.get("commits_tested", 0)}.</dd></div>')
    play = playback(record) if lineup else None
    controls = ('<button type="button" class="btn btn-ink btn-sm playback" data-play aria-pressed="false" hidden>Replay the investigation</button>' if play else "")
    shown = lineup_parts(record) if suspects else {"replays": [], "ordinary": []}
    replay_count = sum(len(column) for column in shown["replays"])
    caption = (f'{replay_count} replays are typed under the commits they ran on.' if replay_count else "No replays yet.") if lineup else ""
    key = ('<p class="key"><span class="chip chip--soft"><b class="fail">x</b>a replay that failed</span><span class="chip chip--soft"><b>o</b>a replay that passed</span>'
           + ('<span class="chip chip--soft"><b style="opacity:.5">x o</b>ordinary runs, in grey</span>' if any(shown["ordinary"]) else "")
           + '<span class="chip chip--soft"><span class="swatch"></span>has an alibi</span><span class="chip chip--soft"><s>struck through</s>cleared</span></p>')
    drawing = ('<section class="lineup-wrap" id="lineup" aria-labelledby="lineup-title"><div class="container">'
               '<div class="stage stage--soft"><div class="card card--raised board">'
               f'<div class="board__head"><h2 id="lineup-title">The lineup</h2>{key}</div>'
               f'<div class="scroll" tabindex="0" role="group" aria-label="The lineup, scrolls sideways">{lineup_svg(record)}</div>'
               f'<div class="under">{controls}<p class="caption" aria-live="polite">{escape(caption)}</p></div></div></div>'
               + suspects_table(record) + (f'<dl class="card figures">{figures}</dl>' if figures else "") + "</div></section>") if suspects else ""
    data = f'<script type="application/json" id="lineup-data">{json.dumps(play, separators=(",", ":")).replace("</", "<\\/")}</script>' if play else ""
    symptom = case.get("symptom", "Untitled case")
    described = (f'{len(suspects)} commits since it last worked. ' + (
        f'The lineup named {_short(culprit["sha"])}, "{culprit["subject"]}", after {lineup.get("replays", 0)} replays.' if culprit else
        "No commit did it: the last good ref fails too." if lineup.get("clear") else "Nobody has been named yet."))
    nav = _nav(([("Lineup", "#lineup")] if suspects else []) + [("Motive", "#motive"), ("Brief", "#brief"), ("Evidence", "#evidence"), ("Fix", "#fix"), ("Damages", "#damages")],
               '<a class="btn btn-sm btn-ink" href="index.html">All cases</a>')
    badge = (f'<p class="badge status{" is-closed" if red else ""}"><span class="badge__tag">{CHECK if red else ""}{escape(words)}</span>'
             f'Case {escape(str(number))}</p>')
    small = ["Drawn from the case record", "Scripted traffic, no real customers" if sent_by else ""]
    ctas = '<div class="cta-row"><a class="btn btn-ink" href="#lineup">See the lineup</a><a class="btn btn-outline" href="#brief">Read the brief</a></div>' if suspects else ""
    # The headline is the question the case asks, and under it what was reported. A case with no suspects yet only has the report.
    count = len(suspects)
    heading = (f'<h1>{count} {"commit" if count == 1 else "commits"} since it last worked. <span class="t-muted">Which one did it?</span></h1>\n'
               f'<p class="lead">{escape(symptom if symptom[-1:] in ".?!" else symptom + ".")}</p>' if count else f'<h1 class="reported">{escape(symptom)}</h1>')
    trust = "".join(f"<span>{escape(text)}</span>" for text in small if text)
    return f"""<!doctype html>
{ROOT}
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta(f'Case {number}. {symptom}', described)}
{FONTS}
<style>{STYLE}</style>
</head>
<body>
{nav}
<main>
<header class="hero hero--split case"><div class="container">
<div>
{badge}
{heading}
{ctas}
<p class="trust">{trust}</p>
</div>
<dl class="card facts">{facts}</dl>
</div></header>
{drawing}
<div class="container sections">
{"".join(parts)}
</div>
</main>
<footer class="footer"><div class="container"><span class="brand">{MARK}Whodunit</span>
<span>Last good <span class="sha">{escape(_short(case.get("good")))}</span>, first bad <span class="sha">{escape(_short(case.get("bad")))}</span>, agent in <code>{escape(case.get("target", ""))}</code>.</span>
<span>Drawn from the case record by <code>whodunit casebook</code>.</span></div></footer>
{data}
<script>{SCRIPT}</script>
</body>
</html>
"""


def _terminal(record: dict) -> str:
    """What `whodunit investigate` printed for a case, in a window. Every line is made from the record, in the command's own words."""
    case, lineup = record.get("case", {}), record.get("lineup") or {}
    suspects, culprit, fix = record.get("suspects", []), lineup.get("culprit"), record.get("fix") or {}
    traffic = (record.get("damages") or {}).get("workflow") if lineup.get("traffic_runs") else None
    lines = [("dim", "$ ") + ("ok", f'uv run whodunit investigate {case.get("file", "case.toml")}' + (f" --from-traffic {traffic}" if traffic else ""))]

    def say(text: str, css: str = "") -> None:
        lines.append((css, text))

    say(f'Case {case.get("id", "")}: {case.get("symptom", "")}')
    say(f'Suspects: {len(suspects)}, of which {sum(bool(s.get("touches_target", True)) for s in suspects)} touched {case.get("target", "")}.')
    excused = [s for s in suspects if s.get("alibi")]
    if excused:
        say(f'Alibis: {len(excused)} of them start with less suspicion, for example {_short(excused[0]["sha"])} ({excused[0]["alibi"]}).', "dim")
    if lineup.get("traffic_runs"):
        seen = {run["sha"] for run in record.get("witnessed") or []}
        say(f'Traffic: {lineup["traffic_runs"]} ordinary runs across {len(seen)} of these commits had already asked this, and {lineup["traffic_failures"]} of them went wrong.', "dim")
    if culprit:
        say(f'Suspects: {len(suspects)}. Cleared: {len(suspects) - 1}.')
        say(f'Culprit: {_short(culprit["sha"])}  {culprit["subject"]}', "hot")
        if "probability" in culprit and "failure_rate_from" in lineup:
            say(f'Confidence: {culprit["probability"]:.1%}. It fails about {lineup["failure_rate_from"]:.0%} of the time from this commit on, and {lineup["failure_rate_before"]:.0%} before it.')
        if "linear_scan_commits" in lineup:
            say(f'Tested {lineup.get("commits_tested", 0)} commits with {lineup.get("replays", 0)} replays in {lineup.get("seconds", 0):.0f}s of replay time. '
                f'A scan from the oldest suspect would have tested {lineup["linear_scan_commits"]} commits.', "dim")
    if kept(fix):
        tries, seen = len(record.get("attempts") or [1]), fix["verification"]
        say(f'Kept the {fix["kind"]} {_short(fix["commit"])} after {tries} {"try" if tries == 1 else "tries"}: {observed(seen["failures"], seen["replays"])}', "ok")
    text = ""
    for n, line in enumerate(lines):
        if n == 0:
            (a, prompt), (b, command) = line[:2], line[2:]
            text += f'<span class="{a}">{escape(prompt)}</span><span class="{b}">{escape(command)}</span>\n'
        else:
            css, said = line
            text += (f'<span class="{css}">{escape(said)}</span>' if css else escape(said)) + "\n"
    return ('<div class="window window--dark" aria-hidden="true"><div class="window__bar"><span class="lights"><i></i><i></i><i></i></span>'
            f'<span class="window__title">whodunit investigate</span></div><pre class="term">{text}</pre></div>')


def write(record: dict, path: Path) -> Path:
    path.write_text(render(record))
    return path


def render_index(records: list[tuple[str, dict]]) -> str:
    """The casebook: the headline case's own output up top, then the docket, one row per case. `records` are (page file name, record)."""
    rows = ""
    named = closed = replays = 0
    cost = 0.0
    scripted = False
    for page, record in records:
        case, lineup = record.get("case", {}), record.get("lineup") or {}
        culprit, damages = lineup.get("culprit"), record.get("damages") or {}
        words, red = stamp(record)
        named += bool(culprit)
        closed += bool(red)
        replays += damages.get("replay_runs") or lineup.get("replays", 0)
        cost += damages.get("replay_usd") or 0.0
        scripted = scripted or bool(damages.get("sent_by") or case.get("traffic_sent_by"))
        who = (f'<span class="sha">{escape(_short(culprit["sha"]))}</span> {escape(culprit["subject"])}' if culprit else
               "None of them. The good ref fails too." if lineup.get("clear") else "Nobody yet")
        number = f'{case["number"]:03d}' if isinstance(case.get("number"), int) else ""
        rows += (f'<tr><td class="no">{number}</td><td><span class="pill-status{" is-closed" if red else ""}">{CHECK if red else ""}{escape(words)}</span></td>'
                 f'<td class="what"><a href="{escape(page)}">{escape(case.get("symptom", page))}</a><div class="small">{len(record.get("suspects", []))} suspects, '
                 f'{lineup.get("replays", 0)} replays to name</div></td><td>{who}</td>'
                 f'<td>{escape(money_said(damages) or ("none seen" if damages.get("case_runs") else ""))}</td></tr>')
    count = len(records)
    line = (f'{count} {"case" if count == 1 else "cases"}. {named} with a culprit named, {closed} closed, {count - closed} open. '
            f'{replays:,} replays in all, about ${cost:.2f}.')
    # The case with the longest lineup is the one shown off, with what the command printed for it.
    headline = max(records, key=lambda item: len(item[1].get("suspects", [])), default=None)
    visual = f'<div class="hero__visual"><div class="stage">{_terminal(headline[1])}</div></div>' if headline and headline[1].get("lineup") else ""
    ctas = ((f'<a class="btn btn-ink" href="{escape(headline[0])}">Open the headline case</a>' if headline else "")
            + '<a class="btn btn-outline" href="#docket">See the docket</a>')
    small = [f"{replays:,} replays in all", f"about ${cost:.2f}", "Scripted traffic, no real customers" if scripted else ""]
    trust = "".join(f"<span>{escape(text)}</span>" for text in small if text)
    nav = _nav(([("Docket", "#docket")] if records else []) + ([("Headline case", headline[0])] if headline else []),
               f'<a class="btn btn-sm btn-ink" href="{escape(headline[0])}">Open a case</a>' if headline else "")
    body = (f"""<header class="hero book"><div class="container">
<p class="badge badge--dot">{count} {"case" if count == 1 else "cases"}, {closed} closed</p>
<h1>Your AI agent worked last week. Now it gets things wrong, <em class="t-serif">sometimes.</em></h1>
<p class="lead">Whodunit tells you which change broke it, who asked for that change, and what it cost. It replays the failing requests on the suspect commits until one of them stands out, then quotes what that commit was asked to do.</p>
<div class="cta-row">{ctas}</div>
<p class="trust">{trust}</p>
{visual}
</div></header>
<section class="section" id="docket"><div class="container">
<div class="section-head section-head--left"><p class="eyebrow">The docket</p><h2>Every case, with its file.</h2><p class="docket-line">{escape(line)}</p></div>
<div class="card docket-card"><table class="docket"><thead><tr><th>No.</th><th>Status</th><th>What was reported</th><th>Culprit</th><th>Damage</th></tr></thead>
<tbody>{rows}</tbody></table></div>
</div></section>""" if records else """<header class="hero book"><div class="container">
<h1>Your AI agent worked last week. Now it gets things wrong, <em class="t-serif">sometimes.</em></h1>
<p class="lead empty">No cases yet. Lucky you.</p>
</div></header>""")
    return f"""<!doctype html>
{ROOT}
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta("Whodunit casebook", f"Which commit broke the agent, and why. {line}")}
{FONTS}
<style>{STYLE}</style>
</head>
<body>
{nav}
<main>
{body}
</main>
<footer class="footer"><div class="container"><span class="brand">{MARK}Whodunit</span><span>Drawn from the case records by <code>whodunit casebook</code>.</span></div></footer>
<script>{SCRIPT}</script>
</body>
</html>
"""

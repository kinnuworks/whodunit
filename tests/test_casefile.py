"""The case file as a made object: stamp, lineup, playback, exhibits, footnotes and the docket."""

import json
import re

from whodunit import casefile

GOOD, A, B, C = "0" * 40, "a" * 40, "b" * 40, "c" * 40


def record(**extra):
    base = {
        "case": {"id": "c", "number": 3, "symptom": "Refunds go to strangers", "good": GOOD, "bad": C, "target": "agent"},
        "suspects": [{"sha": A, "subject": "Tidy", "touches_target": True, "alibi": "only touched README.md, which the agent does not run", "probability": 0.001},
                     {"sha": B, "subject": "Skip the lookup", "touches_target": True, "alibi": "", "probability": 0.998},
                     {"sha": C, "subject": "Later", "touches_target": True, "alibi": "", "probability": 0.001}],
        "lineup": {"culprit": {"sha": B, "subject": "Skip the lookup", "probability": 0.998}, "replays": 5, "commits_tested": 3, "seconds": 30, "linear_scan_commits": 2, "voided": 0},
        "replays": [{"sha": GOOD, "verdict": "pass", "started": 100.0, "input": "x", "reason": ""}, {"sha": C, "verdict": "fail", "started": 100.2, "input": "x", "reason": ""},
                    {"sha": A, "verdict": "pass", "started": 110.0, "input": "x", "reason": ""}, {"sha": B, "verdict": "fail", "started": 120.0, "input": "x", "reason": ""},
                    {"sha": B, "verdict": "fail", "started": 120.1, "input": "x", "reason": ""}],
        "rounds": [{"commits": [GOOD, C], "verdicts": ["pass", "fail"], "top": [[A, 0.4], [B, 0.3], [C, 0.3]], "posterior": [0.4, 0.3, 0.3]},
                   {"commits": [A], "verdicts": ["pass"], "top": [[B, 0.6], [C, 0.39], [A, 0.01]], "posterior": [0.01, 0.6, 0.39]},
                   {"commits": [B, B], "verdicts": ["fail", "fail"], "top": [[B, 0.998], [A, 0.001], [C, 0.001]], "posterior": [0.001, 0.998, 0.001]}],
    }
    base.update(extra)
    return base


def test_only_a_kept_fix_gets_the_red_stamp():
    assert casefile.stamp(record()) == ("Culprit named", "")
    not_fixed = record(fix={"kind": "revert", "commit": None, "branch": "b"}, attempts=[{"kind": "patch", "commit": "1" * 40, "verification": {"fixed": False, "failures": 5, "replays": 90}}])
    assert casefile.stamp(not_fixed) == ("Open, not fixed", "")
    closed = record(fix={"kind": "patch", "commit": "1" * 40, "branch": "b", "verification": {"fixed": True, "failures": 0, "replays": 30}})
    assert casefile.stamp(closed) == ("Case closed", "closed")
    broke = record(fix={"kind": "patch", "commit": "1" * 40, "branch": "b", "verification": {"fixed": True, "failures": 0, "replays": 30}, "harm": {"broken": [{"text": "t"}]}})
    assert casefile.stamp(broke)[1] == ""  # a fix that broke something else does not close a case
    assert casefile.stamp(record(lineup={"culprit": None, "clear": True})) == ("No commit did it", "")
    page = casefile.render(not_fixed)
    assert '<p class="stamp ">Open, not fixed</p>' in page and 'class="stamp closed"' not in page


def test_the_lineup_draws_every_suspect_and_rings_the_culprit():
    drawn = casefile.lineup_svg(record())
    assert drawn.count('class="num"') == 4 and all(sha[:7] in drawn for sha in (A, B, C))  # the good ref and three numbered positions, each with its short SHA
    assert 'class="col culprit"' in drawn and 'class="ring"' in drawn and "Skip the lookup" in drawn
    assert 'class="col cleared alibi"' in drawn and 'class="col cleared"' in drawn  # struck through, and hatched where there is an alibi
    assert drawn.count('class="mark fail"') == 3 and drawn.count('class="mark pass"') == 2  # one typed mark a replay
    assert 'class="tick"' not in drawn and 'class="rule"' not in drawn and ">50%<" not in drawn  # no axis
    page = casefile.render(record())
    assert page.index('class="lineup-wrap"') < page.index("<h2>Suspects</h2>") and page.index("</header>") < page.index('class="lineup-wrap"')
    table = page[page.index('<table class="suspects">'):]
    assert "The lineup as a table" in page and "Culprit" in table and "Alibi: only touched README.md" in table


def test_marks_that_do_not_fit_are_written_as_a_count():
    lines = casefile.mark_lines([], ["x"] * 4 + ["o"] * 35)
    assert lines == [("x", "fail"), ("4", "fail count"), ("o", "pass"), ("35", "pass count")]
    assert len(casefile.mark_lines(["o"], ["x", "o"])) == 3


def test_the_investigation_can_be_replayed_from_its_rounds():
    page = casefile.render(record())
    data = json.loads(re.search(r'<script type="application/json" id="lineup-data">(.*?)</script>', page, re.S).group(1))
    assert [r["c"] for r in data["rounds"]] == [[0, 3], [1], [2, 2]] and data["rounds"][-1]["v"] == ["x", "x"]
    assert data["rounds"][-1]["lead"] == "Suspect 2 leads at 100%." and data["cap"] == casefile.CAP
    assert '<button type="button" class="playback" data-play' in page and "prefers-reduced-motion" in page
    assert 'hidden>Replay the investigation' in page  # off until the script turns it on
    assert '<button type="button" class="playback"' not in casefile.render(record(rounds=[], suspects=[]))


def test_rounds_are_worked_out_again_only_when_they_end_where_the_record_did():
    from whodunit.lineup import ChangePoint

    old = record()
    del old["rounds"]
    old["suspects"] = [{**s, "alibi": ""} for s in old["suspects"]]
    state = ChangePoint(3)
    for sha, verdict in ((GOOD, "pass"), (C, "fail"), (A, "pass"), (B, "fail"), (B, "fail")):
        state.observe({GOOD: -1, A: 0, B: 1, C: 2}[sha], verdict == "fail")
    for suspect, share in zip(old["suspects"], state.posterior()):
        suspect["probability"] = round(share, 5)
    rounds, again = casefile.rounds_of(old)
    assert again and [r["commits"] for r in rounds] == [[GOOD, C], [A], [B, B]]  # replays that started together are one round
    old["suspects"][0]["probability"] = 0.5  # the record says something the replays do not add up to
    assert casefile.rounds_of(old) == ([], False)


def test_citations_are_footnotes_and_exhibits_mark_where_the_runs_part():
    outline_a = "11aa22bb WORKFLOW refund ok\n  in: {\"request\":\"refund 2002\"}\n  22bb33cc LLM chat ok\n    out: assistant: looking → lookup_order({\"order_id\":\"2002\"})\n  33cc44dd TOOL lookup_order ok\n    out: {\"owner\":\"cust_4\"}"
    outline_b = "55ee66ff WORKFLOW refund ok\n  in: {\"request\":\"refund 2002\"}\n  66ff7700 LLM chat ok\n    out: assistant: sure → issue_refund({\"order_id\":\"2002\"})\n  77008811 TOOL issue_refund ok\n    out: {\"refunded\":30}"
    full = record(
        brief={"headline": "h", "writer": "model", "dropped": [], "sentences": [{"text": "The commit dropped the check.", "cites": [B[:12], "66ff7700"]}, {"text": "It paid.", "cites": ["66ff7700"]}]},
        evidence={"culprit": B, "parent": A, "passing_run": {"trace_id": "e" * 32, "commit": A, "outline": outline_a}, "failing_run": {"trace_id": "f" * 32, "commit": B, "outline": outline_b}})
    page = casefile.render(full)
    assert '<sup><a href="#note-1" aria-label="Note 1">1</a> <a href="#note-2" aria-label="Note 2">2</a></sup>' in page and '<sup><a href="#note-2"' in page
    assert f'<li id="note-1"><b>{B[:12]}</b> the culprit commit</li>' in page and "a span in the failing run" in page
    assert "Exhibit A" in page and "Exhibit B" in page and page.count('<li class="parts">') == 2  # the same step, marked in both
    assert "The two runs part at step 2." in page and "The raw outlines" in page
    steps = casefile.exhibit_steps(outline_b)
    assert [s["sign"] for s in steps] == ["asked", "calls issue_refund", "issue_refund ok"]


def test_the_page_has_a_title_a_description_and_light_paper_by_default():
    page = casefile.render(record(damages={"runs": 9, "case_runs": 6, "case_bad": 4, "wrongly_paid": 120.0, "withheld": 0.0, "replay_runs": 50, "replay_usd": 0.18, "note": "n"}))
    assert "<title>Case 003. Refunds go to strangers</title>" in page and 'property="og:image"' in page and 'name="description"' in page
    assert "prefers-color-scheme" not in page and ':root[data-theme="dark"]' in page and "data-theme-toggle" in page  # dark only when chosen
    assert '<p class="money">120.00 refunded to the wrong people</p>' in page  # the money first, in serif
    assert page.index('class="money"') < page.index("in tokens") if "in tokens" in page else True
    for label in ("Case no.", "Opened", "Suspects", "Replays", "Cost of the investigation", "Damage"):
        assert f"<dt>{label}</dt>" in page
    assert '<dt>5</dt>' in page and "<dt>99.80%</dt>" in page and "<dt>2</dt>" in page  # replays, confidence, what a scan would have tested


def test_the_casebook_is_a_docket():
    closed = record(fix={"kind": "patch", "commit": "1" * 40, "branch": "b", "verification": {"fixed": True, "failures": 0, "replays": 30}},
                    damages={"runs": 9, "case_runs": 6, "case_bad": 4, "wrongly_paid": 120.0, "withheld": 0.0, "replay_runs": 50, "replay_usd": 0.18, "note": "n"})
    page = casefile.render_index([("a.casefile.html", closed), ("b.casefile.html", record())])
    assert "2 cases. 2 with a culprit named, 1 closed, 1 open. 55 replays in all, about $0.18." in page
    assert page.count('class="mini-stamp closed"') == 1 and "<th>No.</th><th>Stamp</th><th>What was reported</th><th>Culprit</th><th>Damage</th>" in page
    assert "No cases yet. Lucky you." in casefile.render_index([])

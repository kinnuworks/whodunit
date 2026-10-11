"""Brief, ruling, fix and case file: the steps after a culprit is named."""

import json

import pytest

from tests.planted import git, stub_history
from whodunit import brief as briefs
from whodunit import casefile, fix as fixes, llm, ruling as rulings
from whodunit.case import Case
from whodunit.cli import main
from whodunit.replay import Runner


def evidence(**extra):
    base = dict(
        culprit="c" * 40, parent="p" * 40, subject="Make the replies friendlier", diff="+ be generous",
        checkpoint="abc123def456", request="Make the replies friendlier",
        steps=[{"id": "a0000013", "kind": "said", "text": "I will soften the prompt.", "file": None}],
        failing_run={"trace_id": "f" * 32, "commit": "c" * 40, "input": "refund 2002", "reason": "refunds were [30.0], expected []",
                     "outline": "11aa22bb WORKFLOW refund ok 90ms\n  33cc44dd TOOL issue_refund ok 0ms"},
        passing_run={"trace_id": "e" * 32, "commit": "p" * 40, "input": "refund 2002", "outline": "55ee66ff WORKFLOW refund ok 80ms"},
    )
    base.update(extra)
    return briefs.Evidence(**base)


def test_citable_ids_cover_commits_checkpoint_steps_and_spans():
    ids = evidence().citable()
    assert {"c" * 12, "p" * 12, "abc123def456", "a0000013", "f" * 12, "11aa22bb", "33cc44dd", "55ee66ff"} <= ids


def test_sentences_without_a_real_citation_are_cut():
    checked = briefs.check_citations({"headline": "h", "sentences": [
        {"text": "The culprit loosened the prompt.", "cites": ["cccccccccccc"]},
        {"text": "The refund tool then ran.", "cites": ["33cc44dd", "made-up-id"]},
        {"text": "Customers were furious.", "cites": []},
        {"text": "It cost millions.", "cites": ["deadbeef"]},
    ]}, evidence())
    assert [s["text"] for s in checked["sentences"]] == ["The culprit loosened the prompt.", "The refund tool then ran."]
    assert checked["sentences"][1]["cites"] == ["33cc44dd"]
    assert checked["dropped"] == ["Customers were furious.", "It cost millions."]


def test_an_id_inside_a_sentence_has_to_be_real_too():
    checked = briefs.check_citations({"headline": "cccccccccccc refunds strangers, as 99ff00aa shows", "sentences": [
        {"text": "The refund went out at span 33cc44dd.", "cites": ["cccccccccccc"]},
        {"text": "The passing run shows no refund at span 55ee66fe.", "cites": ["55ee66ff"]},  # one character off the id it cites
        {"text": "Order 2002 cost 129.99 and the run used 1234567 tokens.", "cites": ["cccccccccccc"]},  # numbers, not ids
        {"text": "The model was not defaced.", "cites": ["cccccccccccc"]},  # a word that happens to be hex
    ]}, evidence())
    assert [s["text"] for s in checked["sentences"]] == [
        "The refund went out at span 33cc44dd.", "Order 2002 cost 129.99 and the run used 1234567 tokens.", "The model was not defaced."]
    assert checked["sentences"][0]["cites"] == ["33cc44dd", "cccccccccccc"]  # the id in the text is added to the citations
    assert [u["text"] for u in checked["unresolved"]][:1] == ["The passing run shows no refund at span 55ee66fe."]
    assert "55ee66fe" in checked["unresolved"][0]["problem"]
    assert "99ff00aa" in checked["unresolved"][-1]["problem"]  # the headline is checked as well
    assert briefs.ids_in("paid 129.99 for order 2002 at 1791695776, see 0127ef29 and 367c64a5ae27") == ["0127ef29", "367c64a5ae27"]


def test_words_in_quotation_marks_have_to_be_in_the_evidence():
    held = evidence(request="Make issue_refund round the amount to the nearest whole unit before recording it,\nso what we log matches what the provider will pay.")
    checked = briefs.check_citations({"headline": "h", "sentences": [
        {"text": 'The request said "round the amount to the nearest whole unit before recording it".', "cites": ["abc123def456"]},
        {"text": "It asked that \u201cwhat we log matches what the provider will pay.\u201d", "cites": ["abc123def456"]},
        {"text": 'The request asked for "the logged amount only, never the amount recorded".', "cites": ["abc123def456"]},
        {"text": 'It returned {"refunded": 65, "order_id": "5005"} and the customer\'s reply said the agent\'s refund was done.', "cites": ["cccccccccccc"]},
        {"text": 'It said "Make issue_refund round ... what we log matches".', "cites": ["abc123def456"]},
    ]}, held)
    assert len(checked["sentences"]) == 4
    assert [u["text"] for u in checked["unresolved"]] == ['The request asked for "the logged amount only, never the amount recorded".']
    assert "not in the evidence as quoted" in checked["unresolved"][0]["problem"]


def test_a_brief_that_names_a_span_not_in_the_evidence_is_asked_for_again(monkeypatch):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")
    asked = []
    drafts = iter([
        '{"headline": "h", "sentences": [{"text": "No refund went out at span 55ee66fe.", "cites": ["55ee66ff"]}]}',
        '{"headline": "h", "sentences": [{"text": "No refund went out at span 55ee66ff.", "cites": ["55ee66ff"]}, {"text": "See 0badc0de.", "cites": ["cccccccccccc"]}]}',
    ])

    def ask(system, prompt, **kw):
        asked.append(prompt)
        return next(drafts)
    monkeypatch.setattr(llm, "ask", ask)
    written = briefs.write_brief(evidence(), "symptom")
    assert len(asked) == 2 and "55ee66fe, which is not an id in the evidence" in asked[1]
    assert [s["text"] for s in written["sentences"]] == ["No refund went out at span 55ee66ff."]
    assert written["dropped"] == ["See 0badc0de."] and "unresolved" not in written
    assert written["rejected"][0]["text"] == "No refund went out at span 55ee66fe."


def test_template_brief_cites_everything_it_says():
    written = briefs.template_brief(evidence(), "Refunds go to the wrong customer")
    assert len(written["sentences"]) == 4
    assert briefs.check_citations(written, evidence())["dropped"] == []


def test_model_answer_is_parsed_and_checked(monkeypatch):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")
    answer = 'Here you go:\n{"headline": "Friendlier prompt refunds strangers", "sentences": [{"text": "Good.", "cites": ["abc123def456"]}, {"text": "Bad.", "cites": ["nope"]}]}'
    monkeypatch.setattr(llm, "ask", lambda *a, **k: answer)
    written = briefs.write_brief(evidence(), "symptom")
    assert [s["text"] for s in written["sentences"]] == ["Good."] and written["dropped"] == ["Bad."]


def test_brief_falls_back_to_the_template_when_the_model_fails(monkeypatch):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")

    def boom(*a, **k):
        raise llm.LlmError("the model endpoint answered 500")
    monkeypatch.setattr(llm, "ask", boom)
    written = briefs.write_brief(evidence(), "symptom")
    assert "fixed template" in written["model"] and "500" in written["model"] and written["sentences"]


def test_a_brief_that_says_always_against_the_measured_rate_is_asked_for_again(monkeypatch):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")
    asked = []
    drafts = iter([
        '{"headline": "The shortcut is deterministic", "sentences": [{"text": "The agent goes straight to the refund every time.", "cites": ["abc123def456"]}]}',
        '{"headline": "The shortcut skips the ownership check", "sentences": [{"text": "The agent skipped the lookup in 12 of 14 runs.", "cites": ["abc123def456"]}]}',
    ])

    def ask(system, prompt, **kw):
        asked.append(prompt)
        return next(drafts)
    monkeypatch.setattr(llm, "ask", ask)
    written = briefs.write_brief(evidence(rate_from=0.81, measured="12 of 14 runs failed."), "symptom")
    assert len(asked) == 2 and "rejected by a rule check" in asked[1] and "81%" in asked[1] and "12 of 14 runs failed." in asked[1]
    assert [s["text"] for s in written["sentences"]] == ["The agent skipped the lookup in 12 of 14 runs."]
    assert [o["text"] for o in written["rejected"]] == ["The shortcut is deterministic", "The agent goes straight to the refund every time."]


def test_a_second_draft_that_still_says_always_loses_those_sentences(monkeypatch):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")
    stubborn = '{"headline": "It always fails", "sentences": [{"text": "It fails every time.", "cites": ["abc123def456"]}, {"text": "The prompt changed.", "cites": ["cccccccccccc"]}]}'
    monkeypatch.setattr(llm, "ask", lambda *a, **k: stubborn)
    written = briefs.write_brief(evidence(rate_from=0.59), "Refunds go to strangers")
    assert [s["text"] for s in written["sentences"]] == ["The prompt changed."] and "It fails every time." in written["dropped"]
    assert "always" not in written["headline"]


def test_a_count_of_runs_has_to_be_one_the_lineup_measured():
    measured = "20 replays across 5 commits. From the culprit on, 8 of 8 replays failed. Ordinary runs: 4 of 6 runs went wrong."
    brief = {"headline": "h", "sentences": [
        {"text": "The bisect measured an 81% failure rate across 26 total runs.", "cites": []},
        {"text": "It went wrong in 4 of 6 ordinary runs and in all 8 replays.", "cites": []},
        {"text": "It went wrong in 5 of 6 runs.", "cites": []},
        {"text": "The loop is capped at 3 model calls and order 2002 costs 30.", "cites": []},
    ]}
    found = briefs.unbacked_claims(brief, 0.81, measured)
    assert [o["text"] for o in found] == [brief["sentences"][0]["text"], brief["sentences"][2]["text"]]
    assert '"26"' in found[0]["problem"] and '"5 of 6"' in found[1]["problem"]
    assert briefs.unbacked_claims(brief, 0.81) == []  # nothing measured, nothing to hold a count against


def test_always_is_allowed_when_the_measurements_back_it(monkeypatch):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")
    asked = []

    def ask(system, prompt, **kw):
        asked.append(prompt)
        return '{"headline": "h", "sentences": [{"text": "It fails every time.", "cites": ["abc123def456"]}]}'
    monkeypatch.setattr(llm, "ask", ask)
    assert briefs.write_brief(evidence(rate_from=0.97), "s")["sentences"] and len(asked) == 1
    assert briefs.unbacked_claims({"headline": "h", "sentences": [{"text": "The model does not always follow the rule.", "cites": []}]}, 0.59) == []
    assert briefs.unbacked_claims({"headline": "It is non-deterministic", "sentences": []}, 0.59) == []


@pytest.mark.parametrize("diff, files, kind", [
    ('-SYSTEM = "careful"\n+SYSTEM = "friendly"', ["agent/agent.py"], "prompt"),
    (' SYSTEM = (\n-    "Only refund the owner. "\n+    "Be warm and take their side. "\n     "Never refund more."', ["agent/agent.py"], "prompt"),
    ('+MODEL = "bigger"', ["agent/agent.py"], "model-settings"),
    ('+openai>=2', ["agent/pyproject.toml", "agent/uv.lock"], "dependency"),
    (' @span(kind="TOOL", name="lookup_order")\n def lookup_order(order_id):\n+    for form in forms:', ["agent/agent.py"], "tool-code"),
    ('+def helper(): pass', ["agent/util.py"], "agent-code"),
    ('+note', ["docs/note.md"], "other"),
])
def test_classify(diff, files, kind):
    assert rulings.classify(diff, files) == kind


def test_ruling_is_asked_once_per_kind(tmp_path):
    asked = []

    def ask(question):
        asked.append(question)
        return "patch"
    first, was_asked = rulings.decide(tmp_path, "prompt", "case-1", "c" * 40, "Friendlier replies", "be nice", ask=ask)
    again, asked_again = rulings.decide(tmp_path, "prompt", "case-2", "d" * 40, "Warmer replies", ask=ask)
    assert (first.ruling, was_asked, again.ruling, asked_again) == ("patch", True, "patch", False)
    assert len(asked) == 1 and "Friendlier replies" in asked[0] and again.first_case == "case-1"
    other, asked_other = rulings.decide(tmp_path, "dependency", "case-3", "e" * 40, "Bump", answer="revert")
    assert other.ruling == "revert" and asked_other
    with pytest.raises(ValueError):
        rulings.decide(tmp_path, "tool-code", "case-4", "f" * 40, "x", answer="maybe")


def test_probability_fixed_moves_the_right_way():
    good, bad = (0, 40), (20, 40)
    assert fixes.probability_fixed(0, 12, good, bad) > 0.95
    assert fixes.probability_fixed(4, 8, good, bad) < 0.05
    assert fixes.probability_fixed(0, 2, good, bad) < 0.95  # two passes prove little when the bug fails a third of the time


def test_verify_stops_when_sure():
    passing = fixes.verify(lambda: "pass", (0, 40), (20, 40), budget=90)
    assert passing.fixed and 20 <= passing.replays <= 45  # about 30 clean replays to be sure of a clean baseline
    failing = fixes.verify(lambda: "fail", (0, 40), (20, 40), budget=90)
    assert not failing.fixed and failing.replays == 12 and "still fails more often" in failing.note
    broken = fixes.verify(lambda: "skip", (0, 40), (20, 40))
    assert not broken.fixed and "will not build" in broken.note


def test_the_upper_bound_says_how_little_thirty_clean_replays_show():
    assert 0.060 < fixes.upper_bound(0, 30) < 0.064  # 0 failures in 30 still allows about 6%
    assert fixes.upper_bound(0, 12) > 0.14 and fixes.upper_bound(0, 300) < 0.007
    assert fixes.upper_bound(5, 85) > fixes.upper_bound(0, 90)
    assert fixes.observed(0, 30) == "0 failures in 30 replays. At most 6.2% at 95%."
    assert fixes.observed(1, 12).startswith("1 failure in 12 replays. At most ")
    checked = fixes.verify(lambda: "pass", (0, 40), (20, 40), budget=90)
    assert checked.upper == fixes.upper_bound(0, checked.replays)


def test_a_partial_fix_is_not_called_proven():
    # The bug failed 9 runs in 10. The patch gets it down to 1 in 10, and before the culprit it was 0 in 40.
    import itertools
    one_in_ten = itertools.cycle(["pass"] * 9 + ["fail"])
    checked = fixes.verify(lambda: next(one_in_ten), (0, 40), (36, 4), budget=90)
    assert not checked.fixed
    assert checked.better > 0.95  # it is better than broken, which is recorded and is not the bar


def test_edits_are_applied_only_when_they_match_once(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nx = 1\n")
    answer = "=== a.py\n<<<<<<< SEARCH\ny = 2\n=======\ny = 3\n>>>>>>> REPLACE\n<<<<<<< SEARCH\nx = 1\n=======\nx = 9\n>>>>>>> REPLACE\n=== end\n=== b.py\nwhatever\n=== end"
    changed, problems = fixes.apply_edits(answer, tmp_path, ["a.py"])
    assert changed == ["a.py"] and (tmp_path / "a.py").read_text() == "x = 1\ny = 3\nx = 1\n"
    assert "matched 2 places" in problems and "b.py is not one of the files" in problems


def test_revert_fixes_the_stub_and_the_whole_pipeline_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WHODUNIT_LLM", "none")
    monkeypatch.chdir(tmp_path)  # rulings/ and cases/ are written where the command runs
    made = stub_history(tmp_path / "repo", suspects=10, culprit=6)
    case = str(made["case"])
    assert main(["lineup", case, "--repo", str(made["repo"]), "--budget", "60"]) == 0
    assert main(["brief", case, "--no-runs"]) == 0
    assert main(["ruling", case, "--answer", "revert"]) == 0
    assert main(["fix", case, "--fix-budget", "45"]) == 0
    assert main(["open-case", case, "--no-open"]) == 0
    record = json.loads(made["case"].with_name("case.record.json").read_text())
    assert record["lineup"]["culprit"]["sha"] == made["culprit"]
    assert record["ruling"]["ruling"] == "revert" and record["ruling"]["kind"] == "agent-code"
    assert record["fix"]["verification"]["fixed"] and record["fix"]["verification"]["failures"] == 0
    assert git(made["repo"], "log", "-1", "--format=%s", "whodunit/stub-bonus").startswith('Revert "Add a goodwill bonus')
    kept = tmp_path / "cases" / "stub-bonus.toml"
    assert Case.load(kept).fixed == record["fix"]["commit"]
    page = made["case"].with_name("case.casefile.html").read_text()
    assert "Add a goodwill bonus to refunds" in page and "Revert it." in page
    seen = record["fix"]["verification"]
    assert f"0 failures in {seen['replays']} replays. At most {seen['upper']:.1%} at 95%." in page and "clears the bar" in page
    assert "Proven" not in page and "proven" not in page
    assert "no Entire checkpoint" in page
    # The kept case passes at the fix and fails at the bad ref.
    assert main(["check", str(kept), "--repo", str(made["repo"]), "--ref", record["fix"]["commit"], "--runs", "2"]) == 0
    assert main(["check", str(kept), "--repo", str(made["repo"]), "--ref", made["shas"][-1], "--runs", "2"]) == 1


def test_case_file_renders_an_open_case_without_a_culprit():
    page = casefile.render({"case": {"id": "c1", "symptom": "Refunds <vanish>", "good": "a" * 40, "bad": "b" * 40, "target": "agent"},
                            "suspects": [{"sha": "b" * 40, "subject": "x", "checkpoint": None, "touches_target": True, "probability": 0.6},
                                         {"sha": "d" * 40, "subject": "y", "checkpoint": None, "touches_target": False, "probability": 0.4}],
                            "lineup": {"culprit": None, "replays": 30, "commits_tested": 3, "seconds": 90,
                                       "remaining": [{"sha": "b" * 40, "subject": "x", "probability": 0.6}]}, "replays": []})
    assert "Refunds &lt;vanish&gt;" in page and "Nobody named yet." in page and "Still in the lineup" in page


def test_an_ablation_run_is_kept_beside_the_record_and_shown_on_the_page(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    made = stub_history(tmp_path / "repo", suspects=10, culprit=6)
    case, record_file = str(made["case"]), made["case"].with_name("case.record.json")
    assert main(["lineup", case, "--repo", str(made["repo"]), "--budget", "60"]) == 0
    before = record_file.read_text()
    assert main(["lineup", case, "--repo", str(made["repo"]), "--budget", "60", "--no-graph", "--no-priors", "--ablation"]) == 0
    assert record_file.read_text() == before  # the case record is left alone
    kept = json.loads(made["case"].with_name("case.ablation.json").read_text())
    assert kept["culprit"] == made["culprit"] and kept["replays"] > 0 and "alibis from entire-graph" in kept["without"]
    assert main(["open-case", case, "--no-open"]) == 0
    page = made["case"].with_name("case.casefile.html").read_text()
    assert "What the head start was worth" in page and f"this case took {kept['replays']} replays across {kept['commits_tested']} commits" in page
    assert "one run each way" in page and "cannot be told apart" in page and "too few" in page


def test_investigate_runs_the_whole_case_and_waits_for_the_ruling(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WHODUNIT_LLM", "none")
    monkeypatch.chdir(tmp_path)
    made = stub_history(tmp_path / "repo", suspects=10, culprit=4)
    case = str(made["case"])
    assert main(["investigate", case, "--repo", str(made["repo"]), "--budget", "60"]) == 3  # no ruling yet
    record = json.loads(made["case"].with_name("case.record.json").read_text())
    assert record["lineup"]["culprit"]["sha"] == made["culprit"] and "fix" not in record
    assert record["log"][-1]["step"] == "ruling" and "Waiting for the owner" in record["log"][-1]["outcome"]
    assert main(["investigate", case, "--repo", str(made["repo"]), "--answer", "revert"]) == 0
    record = json.loads(made["case"].with_name("case.record.json").read_text())
    assert record["fix"]["verification"]["fixed"] and len(record["attempts"]) == 1
    assert [e["step"] for e in record["log"]][-3:] == ["lineup", "ruling", "fix"]


def test_a_patch_that_is_not_proven_is_tried_again_and_then_reverted(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WHODUNIT_LLM", "gateway")
    monkeypatch.chdir(tmp_path)
    made = stub_history(tmp_path / "repo", suspects=8, culprit=3)
    case = str(made["case"])
    seen = []

    def useless_patch(system, prompt, **kw):
        seen.append(prompt)
        if system.startswith("You write the root-cause brief"):
            raise llm.LlmError("no brief model in this test")
        # A patch that changes the file and leaves the bug in.
        still_broken = git(made["repo"], "show", f"{made['shas'][-1]}:agent/agent.py")
        return f"=== agent/agent.py\n{still_broken}\n# attempt {len(seen)}\n=== end"
    monkeypatch.setattr(llm, "ask", useless_patch)
    assert main(["investigate", case, "--repo", str(made["repo"]), "--budget", "60", "--answer", "patch", "--fix-budget", "45"]) == 0
    record = json.loads(made["case"].with_name("case.record.json").read_text())
    kinds = [(a["kind"], bool((a.get("verification") or {}).get("fixed"))) for a in record["attempts"]]
    assert kinds == [("patch", False), ("patch", False), ("revert", True)]
    assert record["fix"]["kind"] == "revert" and "fallback" in record["fix"]["note"]
    assert "An earlier patch was tried" in seen[-1] and "refunds were" in seen[-1]
    page = made["case"].with_name("case.casefile.html").read_text()
    assert "What it took" in page

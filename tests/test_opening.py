"""Opening a case from one failing trace."""

import json

import pytest

from tests.planted import stub_history
from tests.traces import Traces
from whodunit import opening
from whodunit.case import Case
from whodunit.cli import main

ASKED = "Please refund order 1001 for customer cust_9."
RIGHT, WRONG = [("1001", 42.0)], [("1001", 47.0)]


@pytest.fixture
def shop(tmp_path, monkeypatch):
    """A planted history with the bug at suspect 6, and ordinary runs of one request on some of its commits."""
    made = stub_history(tmp_path / "repo", suspects=10, culprit=6)
    traces = Traces()
    for n, paid in ((1, RIGHT), (2, RIGHT), (4, RIGHT), (5, RIGHT), (7, WRONG), (8, WRONG)):
        for _ in range(4):
            traces.run(made["shas"][n], ASKED, refunds=paid)
    traces.run(made["shas"][3], "Where is my order 1001?")  # another request, which says nothing about this one
    made["failing"] = traces.run(made["shas"][9], ASKED, refunds=WRONG)
    made["traces"] = traces
    monkeypatch.setattr("whodunit.cli.neatroots", lambda: traces)
    monkeypatch.chdir(tmp_path)
    return made


def test_a_case_is_opened_from_one_failing_trace(shop, capsys):
    out = shop["repo"].parent / "cases" / "from-trace.toml"
    code = main(["open-case", "--from-trace", shop["failing"][:12], "--repo", str(shop["repo"]), "--like", str(shop["case"]), "--id", "from-trace"])
    assert code == 0 and out.is_file()
    case = Case.load(out)
    assert [i.text for i in case.inputs] == [ASKED]  # the input is the root span's
    assert case.bad == shop["shas"][9]  # the bad ref is the commit in the run's tags
    assert case.inputs[0].expect["refunds"] == [{"order_id": "1001", "refunded": 42.0}]  # what the nearest earlier passing run paid
    assert case.good in shop["shas"][:6] and shop["shas"].index(case.good) >= 2  # before the culprit, and not all the way back
    assert (case.target, case.run, case.void_exit_codes) == ("agent", Case.load(shop["case"]).run, (75,))  # how to run it comes from a case like it
    assert case.symptom == f'The request "{ASKED}" ended in a refund of 47.00 on order 1001, where it should have ended in a refund of 42.00 on order 1001.'
    said = capsys.readouterr().out
    assert "commit " + shop["shas"][5][:12] in said and "Next:" in said  # it says where the expectation came from, and stops there
    assert not out.with_name("from-trace.record.json").exists()


def test_with_no_earlier_passing_run_the_owner_is_asked_one_question(shop, capsys, monkeypatch):
    never_seen = "Please refund order 1001 for customer cust_9, it arrived late."
    failing = shop["traces"].run(shop["shas"][9], never_seen, refunds=WRONG)
    args = ["open-case", "--from-trace", failing, "--repo", str(shop["repo"]), "--like", str(shop["case"]), "--id", "asked"]
    monkeypatch.setattr("sys.stdin", open("/dev/null"))
    assert main(args) == 2
    assert "What should this request have produced?" in capsys.readouterr().out and not (shop["repo"].parent / "cases" / "asked.toml").exists()
    assert main(args + ["--expect", '[{"order_id": "1001", "refunded": 42.0}]', "--good", shop["shas"][0]]) == 0
    case = Case.load(shop["repo"].parent / "cases" / "asked.toml")
    assert case.inputs[0].expect["refunds"] == [{"order_id": "1001", "refunded": 42.0}] and case.good == shop["shas"][0]


def test_the_failing_run_can_come_from_the_cloud(shop):
    class Cloud:
        def call(self, tool, **given):
            assert tool == "get_trace_context" and given["trace_id"] == "cafe" * 8
            return {"trace_id": "cafe" * 8, "workflow": "refund-agent", "created_at": "2026-10-11T12:12:47.510Z", "spans": [
                {"span_id": "a1", "name": "refund", "parent_span_id": "", "is_root": True, "input_value": json.dumps({"request": ASKED, "max_steps": 3}), "output_value": "Done"},
                {"span_id": "a2", "name": "run_info", "parent_span_id": "a1", "is_root": False, "input_value": "{}", "output_value": json.dumps({"tags": [f"commit:{shop['shas'][9]}", "llm:gateway"]})},
                {"span_id": "a3", "name": "issue_refund", "parent_span_id": "a1", "is_root": False, "input_value": "{}", "output_value": json.dumps({"order_id": "1001", "refunded": 47.0})},
            ]}
    run = opening.read_failing_run("cafe" * 8, shop["traces"], Cloud())
    assert (run.source, run.request, run.commit, run.paid) == ("neatlogs cloud", ASKED, shop["shas"][9], {"1001": 47.0})
    local = opening.read_failing_run(shop["failing"], shop["traces"], None)
    assert (local.source, local.request, local.commit, local.paid) == ("neatroots", ASKED, shop["shas"][9], {"1001": 47.0})
    with pytest.raises(LookupError):
        opening.read_failing_run("beef" * 8, shop["traces"], None)

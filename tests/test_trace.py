"""The investigation's own trace: what spans it makes, and that it is optional."""

import json
import sys
import types

from tests.planted import stub_history
from whodunit.cli import main
from whodunit.trace import Trace


class FakeSdk(types.ModuleType):
    """Stands in for the Neatlogs SDK and keeps every span it is asked for."""

    def __init__(self):
        super().__init__("neatlogs")
        self.spans, self.stack, self.started, self.closed = [], [], [], False

    def init(self, **settings):
        self.started.append(settings)

    def span(self, kind, name=None):
        def wrap(fn):
            def inner(**given):
                entry = {"name": name, "kind": kind, "input": given, "parent": self.stack[-1]["name"] if self.stack else None}
                self.spans.append(entry)
                self.stack.append(entry)
                try:
                    entry["output"] = fn(**given)
                    return entry["output"]
                finally:
                    self.stack.pop()
            return inner
        return wrap

    def inject_trace_context(self, carrier):
        carrier["traceparent"] = "00-" + "ab" * 16 + "-" + "cd" * 8 + "-01"

    def flush(self):
        self.closed = True

    def shutdown(self):
        pass


def test_nothing_is_traced_and_nothing_breaks_without_the_sdk(monkeypatch):
    monkeypatch.setenv("WHODUNIT_TRACE", "cloud")
    monkeypatch.setitem(sys.modules, "neatlogs", None)  # importing it now fails, as on a machine without the SDK
    trace = Trace("some-case")
    assert not trace.on and "not installed" in trace.note
    assert trace.root({"symptom": "s"}, lambda: trace.step("lineup", {"suspects": 3}, lambda: {"culprit": "c"})) == {"culprit": "c"}
    assert trace.trace_id is None
    trace.close()


def test_the_cloud_needs_a_key_and_the_local_collector_does_not(monkeypatch, tmp_path):
    fake = FakeSdk()
    monkeypatch.setitem(sys.modules, "neatlogs", fake)
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.delenv("WHODUNIT_ENV", raising=False)
    assert "NEATLOGS_API_KEY is not in .env" in Trace("c", where="cloud").note and not fake.started
    local = Trace("c", where="neatroots")
    assert local.on and fake.started[0]["tags"] == ["case:c", "whodunit"] and fake.started[0]["instrumentations"] == []


def test_one_investigation_is_one_trace_with_a_span_for_each_step(tmp_path, monkeypatch, capsys):
    fake = FakeSdk()
    monkeypatch.setitem(sys.modules, "neatlogs", fake)
    monkeypatch.setenv("WHODUNIT_TRACE", "neatroots")
    monkeypatch.setenv("WHODUNIT_LLM", "none")
    monkeypatch.chdir(tmp_path)
    made = stub_history(tmp_path / "repo", suspects=10, culprit=6)
    assert main(["investigate", str(made["case"]), "--repo", str(made["repo"]), "--budget", "60", "--answer", "revert"]) == 0
    names = [s["name"] for s in fake.spans]
    root = fake.spans[0]
    assert root["name"] == "whodunit investigate" and root["kind"] == "WORKFLOW" and root["input"]["case"] == "stub-bonus" and root["parent"] is None
    assert len([s for s in fake.spans if s["parent"] is None]) == 1 and fake.closed  # one trace, and it was flushed
    for wanted in ("lineup", "lineup round 1", "motive", "brief", "ruling", "fix attempt 1, a revert", "verify the fix", "damages"):
        assert wanted in names, wanted
    rounds = [s for s in fake.spans if s["name"].startswith("lineup round")]
    assert all(s["parent"] == "lineup" for s in rounds) and len(rounds) >= 2
    last = rounds[-1]
    assert last["input"]["replayed"] and set(last["output"]["verdicts"]) <= {"pass", "fail", "skip", "void"}
    top = last["output"]["top_three"]
    assert len(top) == 3 and top[0]["commit"] == made["culprit"][:12] and top[0]["probability"] >= 0.95 >= top[1]["probability"]
    verify = next(s for s in fake.spans if s["name"] == "verify the fix")
    assert verify["parent"] == "fix attempt 1, a revert" and verify["output"]["failures"] == 0 and verify["output"]["cleared_the_bar"]
    assert root["output"]["culprit"] == made["culprit"][:12] and root["output"]["fix"] == "revert kept"
    record = json.loads(made["case"].with_name("case.record.json").read_text())
    assert record["trace"] == {"where": "neatroots", "trace_id": "ab" * 16}
    assert len(record["rounds"]) == len(rounds) and record["rounds"][-1]["top"][0][0] == made["culprit"]
    assert abs(sum(record["rounds"][-1]["posterior"]) - 1) < 0.01
    page = made["case"].with_name("case.casefile.html").read_text()
    assert "ab" * 16 in page


def record_with_runs(tmp_path):
    record = {"case": {"id": "c", "repo": str(tmp_path)}, "suspects": [], "lineup": {"culprit": {"sha": "c" * 40, "subject": "s"}, "replays": 3, "commits_tested": 1},
              "evidence": {"failing_run": {"trace_id": "f" * 32, "commit": "c" * 40, "outline": "11aa22bb WORKFLOW refund ok"},
                           "passing_run": {"trace_id": "e" * 32, "commit": "p" * 40, "outline": "55ee66ff WORKFLOW refund ok"}}}
    (tmp_path / "c.toml").write_text('id = "c"\nsymptom = "s"\ngood = "a"\nbad = "b"\n[[inputs]]\ntext = "x"\n')
    (tmp_path / "c.record.json").write_text(json.dumps(record))
    return tmp_path / "c.toml", tmp_path / "c.record.json"


def test_the_two_runs_are_sent_to_the_cloud_and_named_in_the_evidence(tmp_path, monkeypatch, capsys):
    case, record_file = record_with_runs(tmp_path)
    asked = []
    monkeypatch.setattr("whodunit.cli.forward_to_cloud", lambda ids: (asked.append(ids), (True, "sent 10 spans"))[1])
    monkeypatch.chdir(tmp_path)
    assert main(["forward", str(case)]) == 0
    assert asked == [["f" * 32, "e" * 32]]
    cloud = json.loads(record_file.read_text())["evidence"]["cloud"]
    assert cloud["sent"] and cloud["trace_ids"] == {"failing_run": "f" * 32, "passing_run": "e" * 32}
    assert main(["open-case", str(case), "--no-open"]) == 0
    page = (tmp_path / "c.casefile.html").read_text()
    assert "sent from neatroots to neatlogs cloud" in page and "<a href" not in page.split("neatlogs cloud")[1][:300]  # ids, and no made-up link
    monkeypatch.setenv("NEATLOGS_TRACE_URL", "https://dashboard.example.invalid/traces/{trace_id}")
    assert main(["open-case", str(case), "--no-open"]) == 0
    assert f'https://dashboard.example.invalid/traces/{"f" * 32}' in (tmp_path / "c.casefile.html").read_text()


def test_runs_that_could_not_be_sent_are_said_to_be_local(tmp_path, monkeypatch, capsys):
    case, record_file = record_with_runs(tmp_path)
    monkeypatch.setattr("whodunit.cli.forward_to_cloud", lambda ids: (False, "no API key stored: run neatroots cloud login"))
    monkeypatch.chdir(tmp_path)
    assert main(["forward", str(case)]) == 1
    cloud = json.loads(record_file.read_text())["evidence"]["cloud"]
    assert not cloud["sent"] and cloud["trace_ids"] == {}
    assert main(["open-case", str(case), "--no-open"]) == 0
    page = (tmp_path / "c.casefile.html").read_text()
    assert "have not been sent to neatlogs cloud" in page and "neatroots cloud login" in page

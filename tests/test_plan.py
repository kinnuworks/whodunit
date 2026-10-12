"""The business plan sets a spend limit, and an investigation that reaches it stops and says so."""

import json

import pytest

from tests.planted import stub_history
from tests.test_lineup import flaky
from whodunit import casefile
from whodunit.cli import load_record, main
from whodunit.lineup import statistical_bisect
from whodunit.neat import NeatError
from whodunit.plan import REACHED, Meter, meter_for, read_plan, spend_limit

PLAN = {"team_price_usd": 249, "team_investigations_included": 40, "target_margin": 0.7639, "worker_monthly_cost_usd": 61,
        "team_agents_per_shared_worker": 15, "brief_and_patch_cost_per_investigation_usd": 0.2}


class Spent:
    """Stands in for neatroots: every question about replays gets these token counts back."""

    def __init__(self, prompt_tokens: int, completion_tokens: int = 0):
        self.rows = [{"model": "claude-haiku", "pt": prompt_tokens, "ct": completion_tokens}]

    def call(self, tool, **arguments):
        return {"rows": self.rows}


def test_the_limit_is_read_from_the_plan_file(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(PLAN))
    # (249 x (1 - 0.7639) - 61 / 15) / 40
    assert spend_limit(read_plan(path)) == pytest.approx(1.37)
    assert spend_limit({**PLAN, "target_margin": 0.5}) == pytest.approx(3.01)
    meter = meter_for("c", {"replay_windows": [[1, 2]]}, path=path)
    assert meter.limit == pytest.approx(1.37) and meter.allowance == 0.2 and meter.source == str(path) and not meter.raised and meter.windows == [[1, 2]]
    raised = meter_for("c", {}, given=5.0, path=path)
    assert raised.limit == 5.0 and raised.raised and raised.source == "--spend-limit"
    assert not meter_for("c", {}, given=1.0, path=path).raised  # lowering it is not raising it
    assert meter_for("c", {}, path=tmp_path / "none.json") is None and read_plan(tmp_path / "none.json") is None


def test_the_plan_in_the_repo_gives_the_limit_the_readme_quotes():
    plan = read_plan()
    assert plan["team_price_usd"] == 249 and plan["team_investigations_included"] == 40
    assert spend_limit(plan) == pytest.approx(1.37)


def test_the_meter_prices_replays_like_the_damages_and_counts_the_allowance():
    under = Meter(limit=1.37, case_id="c", allowance=0.2, ask=lambda: Spent(1_000_000))  # $1.00 of replays
    assert under.spent() == pytest.approx(1.20) and under.why() == ""
    over = Meter(limit=1.37, case_id="c", allowance=0.2, ask=lambda: Spent(1_000_000, 40_000))  # $1.20 of replays
    assert over.why() == f"{REACHED}: about $1.40 spent of $1.37 allowed"

    def down():
        raise NeatError("connection refused")
    blind = Meter(limit=1.37, case_id="c", allowance=0.2, ask=down)
    assert blind.why() == "" and "connection refused" in blind.to_dict()["note"]


def test_a_lineup_that_would_cross_the_limit_stops_and_names_nobody():
    asked = []

    def stop() -> str:
        asked.append(1)
        return f"{REACHED}: about $1.40 spent of $1.37 allowed" if len(asked) > 2 else ""
    found = statistical_bisect(40, flaky(25, 0.3, seed=3), budget=400, stop=stop)
    assert found.culprit is None and found.note.startswith(REACHED)
    assert found.replays < 40 and len(found.remaining) > 1  # handed back with the suspects still in play
    free = statistical_bisect(40, flaky(25, 0.3, seed=3), budget=400)
    assert free.culprit == 25 and free.replays > found.replays


def test_the_record_says_why_a_lineup_stopped_and_when_the_limit_was_raised(tmp_path, capsys, monkeypatch):
    def down():
        raise NeatError("not running")
    monkeypatch.setattr("whodunit.plan.neatroots", down)
    made = stub_history(tmp_path / "repo", suspects=12, culprit=5, broken=(3,))
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "60", "--spend-limit", "0"]) == 1
    assert "Stopped: the spend limit was reached" in capsys.readouterr().out
    record = load_record(made["case"].with_suffix(".record.json"))
    assert record["lineup"]["culprit"] is None and record["lineup"]["note"].startswith(REACHED)
    assert len(record["lineup"]["remaining"]) > 1 and all("probability" in s for s in record["lineup"]["remaining"])
    assert record["spend"]["stopped"] == "lineup" and record["spend"]["limit_usd"] == 0 and record["spend"]["from"] == "--spend-limit"
    said = dict(casefile.timeline(record))["spend"]
    assert said.startswith("Stopped during the lineup at the spend limit") and said.endswith("a limit set by --spend-limit.")
    # With room to spend, the same case names its culprit and the record says nothing stopped it.
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "60", "--spend-limit", "50"]) == 0
    record = load_record(made["case"].with_suffix(".record.json"))
    assert record["lineup"]["culprit"]["sha"] == made["culprit"] and record["spend"]["stopped"] == ""

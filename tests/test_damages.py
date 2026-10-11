"""Damages: only runs that fail the case's own check are this case's damage."""

import json
import sqlite3

from whodunit import damages

CULPRIT, LATER, EARLIER = "c" * 40, "d" * 40, "a" * 40
PRICES = {"small": (1.0, 5.0)}  # dollars per million tokens in and out, for the one model these traces name
ASKED = "Hi, I'm cust_6. Could I get a refund of 30 dollars for order 2002? Thanks."


class Traces:
    """Stands in for neatroots: answers query_sql from a small SQLite database with the same two tables."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("create table runs (trace_id, workflow, doctor, status, error_count, finding_count, started_ms, input_preview)")
        self.db.execute("create table spans (trace_id, name, span_kind, attributes, output_preview, status_code, model, prompt_tokens, completion_tokens)")
        self.count = 0

    def run(self, commit, asked, refunds=(), case="", status="ok", findings=0, tokens=(1000, 100), at=None):
        self.count += 1
        trace = f"t{self.count:031d}"
        tags = f"commit:{commit}" + (f" case:{case}" if case else "")
        self.db.execute("insert into runs values (?, 'refund-agent', 0, ?, ?, ?, ?, ?)", (trace, status, int(status == "error"), findings, at or self.count * 1000.0, asked))
        self.db.execute("insert into spans values (?, 'run_info', 'CHAIN', ?, '{}', 0, null, 0, 0)", (trace, tags))
        self.db.execute("insert into spans values (?, 'chat', 'LLM', '', '', 0, 'small', ?, ?)", (trace, *tokens))
        for order, amount in refunds:
            self.db.execute("insert into spans values (?, 'issue_refund', 'TOOL', '', ?, 0, null, 0, 0)", (trace, json.dumps({"order_id": order, "refunded": amount})))
        return trace

    def call(self, tool, sql):
        assert tool == "query_sql"
        return {"rows": [dict(row) for row in self.db.execute(sql)]}


def test_only_runs_that_fail_this_cases_check_are_its_damage():
    traces = Traces()
    traces.run(CULPRIT, ASKED, refunds=[("2002", 30.0)])  # this case's bug: someone else's order refunded
    traces.run(LATER, ASKED)  # the same request, and the agent refused, as it should
    traces.run(LATER, "Please refund order 3003 in full for customer cust_7.", refunds=[("3003", 130.0)], status="error", findings=1)  # another regression
    traces.run(LATER, "Please refund order 1001 for customer cust_9.", findings=1)  # a finding that has nothing to do with this case
    traces.run(EARLIER, ASKED, refunds=[("2002", 30.0)])  # before the culprit, so not in the window
    traces.run(CULPRIT, ASKED, refunds=[("2002", 30.0)], case="strangers-paid/1")  # Whodunit's own replay
    since_culprit = [CULPRIT, LATER]
    counted = damages.count(traces, "refund-agent", commits=since_culprit, case_id="strangers-paid", prices=PRICES)
    counted = damages.count_case(traces, counted, "refund-agent", since_culprit, [(ASKED, [])], prices=PRICES)
    assert counted.runs == 4 and counted.replay_runs == 1
    assert (counted.case_runs, counted.case_bad) == (2, 1)  # the two runs that errored or were flagged for other reasons are not counted
    assert (counted.wrongly_paid, counted.withheld) == (30.0, 0.0)
    assert counted.case_bad_tokens == 1100 and counted.case_bad_usd == round((1000 * 1.0 + 100 * 5.0) / 1e6, 4)
    assert not hasattr(counted, "bad_runs")  # "N of M runs went bad" lumped every regression together, and is gone


def test_money_owed_and_not_refunded_is_counted_too():
    traces = Traces()
    owed = "Hi, I'm cust_4. Please refund order 2002, I ordered the wrong item by mistake."
    traces.run(CULPRIT, owed)
    traces.run(CULPRIT, owed, refunds=[("2002", 30.0)])
    counted = damages.count_case(traces, damages.count(traces, "refund-agent", commits=[CULPRIT]), "refund-agent", [CULPRIT], [(owed, [{"order_id": "2002", "refunded": 30.0}])])
    assert (counted.case_runs, counted.case_bad, counted.withheld, counted.wrongly_paid) == (2, 1, 30.0, 0.0)


def test_replays_from_a_later_experiment_are_not_billed_to_the_investigation():
    traces = Traces()
    for at in (10_000.0, 11_000.0, 12_000.0):
        traces.run(CULPRIT, ASKED, case="strangers-paid/1", at=at)
    traces.run(CULPRIT, ASKED, case="strangers-paid/2", at=90_000.0)  # plain bisect, tried on the same case hours later
    everything = damages.count(traces, "refund-agent", commits=[CULPRIT], case_id="strangers-paid", prices=PRICES)
    mine = damages.count(traces, "refund-agent", commits=[CULPRIT], case_id="strangers-paid", prices=PRICES, replays_between=(9_000.0, 13_000.0))
    assert (everything.replay_runs, mine.replay_runs) == (4, 3) and mine.replay_usd < everything.replay_usd + 1e-9

"""A stand-in for neatroots: answers query_sql from a small SQLite database with the same two tables."""

import json
import sqlite3


class Traces:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("create table runs (trace_id, workflow, doctor, status, error_count, finding_count, started_ms, input_preview)")
        self.db.execute("create table spans (trace_id, name, span_kind, parent_span_id, attributes, input_preview, output_preview, status_code, model, prompt_tokens, completion_tokens)")
        self.count = 0

    def run(self, commit, asked, refunds=(), case="", status="ok", findings=0, tokens=(1000, 100), at=None, workflow="refund-agent", info=None):
        """One run of the agent: the request, the commit it ran on, and the refunds it paid."""
        self.count += 1
        trace = f"{self.count:04d}" + "0" * 28
        tags = [f"commit:{commit}", "llm:fake"] + ([f"case:{case}"] if case else [])
        self.db.execute("insert into runs values (?, ?, 0, ?, ?, ?, ?, ?)", (trace, workflow, status, int(status == "error"), findings, at or self.count * 1000.0, asked))
        self.db.execute("insert into spans values (?, 'refund', 'WORKFLOW', null, '', ?, '', 0, null, 0, 0)", (trace, json.dumps({"request": asked, "max_steps": 3})))
        self.db.execute("insert into spans values (?, 'run_info', 'CHAIN', 'root', ?, '{}', ?, 0, null, 0, 0)", (trace, " ".join(tags), json.dumps({"tags": tags, **(info or {})})))
        self.db.execute("insert into spans values (?, 'chat', 'LLM', 'root', '', '', '', 0, 'small', ?, ?)", (trace, *tokens))
        for order, amount in refunds:
            self.db.execute("insert into spans values (?, 'issue_refund', 'TOOL', 'root', '', '', ?, 0, null, 0, 0)", (trace, json.dumps({"order_id": order, "refunded": amount})))
        return trace

    def call(self, tool, sql):
        assert tool == "query_sql"
        return {"rows": [dict(row) for row in self.db.execute(sql)]}

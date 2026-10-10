"""The damages: how many runs went bad, and what they cost.

Counts come from the traces neatroots holds. The dollar figures are estimates from token
counts and a price per million tokens, and are labelled as estimates wherever they appear.
Writing them to cfo.ai is a separate step that needs the owner's yes.
"""

import json
from dataclasses import asdict, dataclass

from .neat import Mcp

# US dollars per million tokens (input, output), by the model name on the LLM span. These are
# list prices as best known when this was written. Pass your own to `count` for real billing.
PRICES = {"claude-haiku": (1.00, 5.00), "claude-sonnet-4.6": (3.00, 15.00), "fake": (0.0, 0.0), "mock": (0.0, 0.0)}


@dataclass
class Damages:
    workflow: str
    since_ms: float | None
    runs: int
    bad_runs: int
    bad_share: float
    tokens: int
    bad_tokens: int
    cost_usd: float  # of all runs in the window
    wasted_usd: float  # of the bad runs
    replay_runs: int = 0  # runs Whodunit itself made while investigating
    replay_usd: float = 0.0
    case_runs: int = 0  # ordinary runs on the culprit or later whose request is one of the case's inputs
    case_bad: int = 0  # of those, the ones that paid out something other than what the case expects
    wrongly_paid: float = 0.0  # money refunded that should not have been, in the orders' currency
    withheld: float = 0.0  # money that should have been refunded and was not
    note: str = "Dollar figures are estimates from token counts."

    def to_dict(self) -> dict:
        return asdict(self)


def _cost(prompt_tokens: int, completion_tokens: int, price: tuple[float, float]) -> float:
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000


BAD = "(r.status = 'error' or r.error_count > 0 or r.finding_count > 0)"
REPLAY = "exists (select 1 from spans i where i.trace_id = r.trace_id and i.name = 'run_info' and i.attributes like '{like}')"


def _spend(mcp: Mcp, where: str, prices: dict) -> tuple[float, float, int, int]:
    """(cost of all runs, cost of bad runs, tokens, bad tokens) for the runs that match, priced per model."""
    rows = mcp.call("query_sql", sql=(
        f"select s.model as model, {BAD} as bad, coalesce(sum(s.prompt_tokens), 0) as pt, coalesce(sum(s.completion_tokens), 0) as ct "
        f"from runs r join spans s on s.trace_id = r.trace_id and s.span_kind = 'LLM' where {where} group by s.model, bad"
    ))["rows"]
    cost = bad_cost = tokens = bad_tokens = 0
    for row in rows:
        spent = _cost(row["pt"], row["ct"], prices.get(row["model"] or "", (0.0, 0.0)))
        cost, tokens = cost + spent, tokens + row["pt"] + row["ct"]
        if row["bad"]:
            bad_cost, bad_tokens = bad_cost + spent, bad_tokens + row["pt"] + row["ct"]
    return cost, bad_cost, tokens, bad_tokens


def count(mcp: Mcp, workflow: str, commits: list[str] | None = None, since_ms: float | None = None, case_id: str | None = None,
          prices: dict | None = None) -> Damages:
    """Count the workflow's ordinary runs on the culprit and the commits after it.

    `commits` are those SHAs. A run is bad if it errored or neatroots raised a finding on it.
    Replays made for a case are left out of the damage and reported on their own line.
    """
    prices = prices or PRICES
    safe = workflow.replace("'", "''")
    window = f" and r.started_ms >= {float(since_ms)}" if since_ms else ""
    production = f"r.workflow = '{safe}' and r.doctor = 0{window} and not " + REPLAY.format(like="%case:%")
    if commits is not None:
        on_bad = " or ".join(f"i.attributes like '%commit:{sha}%'" for sha in commits if sha.isalnum()) or "0"
        production += f" and exists (select 1 from spans i where i.trace_id = r.trace_id and i.name = 'run_info' and ({on_bad}))"
    row = mcp.call("query_sql", sql=f"select count(*) as runs, coalesce(sum({BAD}), 0) as bad from runs r where {production}")["rows"][0]
    cost, bad_cost, tokens, bad_tokens = _spend(mcp, production, prices)
    damages = Damages(
        workflow=workflow, since_ms=since_ms, runs=row["runs"], bad_runs=row["bad"],
        bad_share=round(row["bad"] / row["runs"], 4) if row["runs"] else 0.0,
        tokens=tokens, bad_tokens=bad_tokens, cost_usd=round(cost, 4), wasted_usd=round(bad_cost, 4),
    )
    if case_id:
        mine = REPLAY.format(like=f"%case:{case_id}%".replace("'", "''"))
        damages.replay_runs = mcp.call("query_sql", sql=f"select count(*) as runs from runs r where {mine}")["rows"][0]["runs"]
        damages.replay_usd = round(_spend(mcp, mine, prices)[0], 4)
    return damages


def count_case(mcp: Mcp, damages: Damages, workflow: str, commits: list[str], inputs: list[tuple[str, list[dict]]]) -> Damages:
    """Judge the ordinary runs that asked exactly what the case asks, and add up the money.

    `inputs` are (request text, refunds a correct run pays). What a run paid is read from its
    issue_refund tool spans. This is the part of the damage that is in the shop's currency and
    not in tokens: refunds that went out wrongly, and refunds that should have and did not.
    """
    expected = {text: {str(r["order_id"]): float(r["refunded"]) for r in refunds} for text, refunds in inputs}
    safe = workflow.replace("'", "''")
    on_bad = " or ".join(f"i.attributes like '%commit:{sha}%'" for sha in commits if sha.isalnum()) or "0"
    asked = ", ".join("'" + text.replace("'", "''") + "'" for text in expected) or "''"
    runs = mcp.call("query_sql", sql=(
        "select r.trace_id, r.input_preview from runs r where "
        f"r.workflow = '{safe}' and r.doctor = 0 and r.input_preview in ({asked}) and not " + REPLAY.format(like="%case:%") +
        f" and exists (select 1 from spans i where i.trace_id = r.trace_id and i.name = 'run_info' and ({on_bad})) limit 200"
    ))["rows"]
    if not runs:
        return damages
    ids = ", ".join("'" + r["trace_id"] + "'" for r in runs)
    paid: dict[str, dict[str, float]] = {r["trace_id"]: {} for r in runs}
    for span in mcp.call("query_sql", sql=f"select trace_id, output_preview from spans where name = 'issue_refund' and status_code != 2 and trace_id in ({ids}) limit 200")["rows"]:
        try:
            out = json.loads(span["output_preview"] or "{}")
            order, amount = str(out["order_id"]), float(out["refunded"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        paid[span["trace_id"]][order] = paid[span["trace_id"]].get(order, 0.0) + amount
    for run in runs:
        want, got = expected[run["input_preview"]], paid[run["trace_id"]]
        over = sum(max(0.0, got.get(o, 0.0) - want.get(o, 0.0)) for o in set(got) | set(want))
        under = sum(max(0.0, want.get(o, 0.0) - got.get(o, 0.0)) for o in set(got) | set(want))
        damages.case_runs += 1
        if over > 0.005 or under > 0.005:
            damages.case_bad += 1
            damages.wrongly_paid += over
            damages.withheld += under
    damages.wrongly_paid, damages.withheld = round(damages.wrongly_paid, 2), round(damages.withheld, 2)
    return damages

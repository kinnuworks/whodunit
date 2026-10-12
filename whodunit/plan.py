"""What the business plan lets one investigation spend, and a meter that says when it has been spent.

The plan is the cfo.ai model. `pitch/plan.json` holds the few numbers read from it. Nothing here
talks to cfo.ai.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .damages import PRICES, REPLAY, _spend
from .neat import Mcp, NeatError, neatroots

PLAN = Path("pitch/plan.json")
REACHED = "the spend limit was reached"


def read_plan(path: str | Path = PLAN) -> dict | None:
    path = Path(path)
    return json.loads(path.read_text()) if path.is_file() else None


def spend_limit(plan: dict) -> float:
    """The most one investigation may spend, in dollars, if the plan's margin on a Team agent is to hold.

        limit = (team price x (1 - target margin) - worker cost / agents per worker) / investigations included

    A Team agent pays the price each month. Keeping the margin leaves price x (1 - margin) for
    serving it. Its share of a replay worker comes off that, and the rest is spread over the
    investigations the tier includes, as if all of them were used. An investigation that stays
    under this cannot be the one that breaks the margin.
    """
    serving = plan["team_price_usd"] * (1 - plan["target_margin"])
    worker = plan["worker_monthly_cost_usd"] / plan["team_agents_per_shared_worker"]
    return round((serving - worker) / plan["team_investigations_included"], 2)


@dataclass
class Meter:
    """Adds up what one investigation has spent and says when that reaches its limit.

    Replays are priced the way the damages are: token counts from the runs' model spans in
    neatroots, at list prices. The model calls for the brief and the patch are not metered, so
    the plan's allowance for them is counted as spent from the start. A replay still being
    written to neatroots is not counted yet, so the meter runs a few replays behind.
    """

    limit: float
    case_id: str
    source: str = str(PLAN)  # where the limit came from: the plan file, or the flag
    raised: bool = False  # whether the flag set it above what the plan allows
    allowance: float = 0.0
    windows: list = field(default_factory=list)  # earlier stretches of this investigation's replays, in ms
    ask: Callable[[], Mcp] | None = None  # how to reach neatroots, when it is not the usual way
    started_ms: float = field(default_factory=lambda: time.time() * 1000 - 2000)
    unknown: str = ""  # why the replays could not be priced, if neatroots could not be asked
    stopped: str = ""  # the step that was stopped, once one has been

    def spent(self) -> float:
        stretches = [*self.windows, [self.started_ms, time.time() * 1000 + 60000]]
        mine = REPLAY.format(like=f"%case:{self.case_id}%".replace("'", "''"))
        mine += " and (" + " or ".join(f"(r.started_ms >= {float(lo)} and r.started_ms <= {float(hi)})" for lo, hi in stretches) + ")"
        try:
            return self.allowance + _spend((self.ask or neatroots)(), mine, PRICES)[0]
        except NeatError as exc:
            self.unknown = str(exc)
            return self.allowance

    def why(self) -> str:
        """Why the investigation has to stop here, or nothing if it may go on."""
        spent = self.spent()
        return f"{REACHED}: about ${spent:.2f} spent of ${self.limit:.2f} allowed" if spent >= self.limit else ""

    def to_dict(self) -> dict:
        said = {"limit_usd": self.limit, "from": self.source, "raised": self.raised, "spent_usd": round(self.spent(), 4),
                "allowance_usd": self.allowance, "stopped": self.stopped}
        if self.unknown:
            said["note"] = f"neatroots could not be asked what the replays cost, so only the allowance was counted: {self.unknown}"
        return said


def meter_for(case_id: str, record: dict, given: float | None = None, path: str | Path = PLAN) -> Meter | None:
    """The meter for one investigation: the plan's limit, or the one given on the command line. None when there is neither."""
    plan = read_plan(path)
    allowed = spend_limit(plan) if plan else None
    if given is None and allowed is None:
        return None
    limit = allowed if given is None else given
    return Meter(limit=limit, case_id=case_id, source=str(path) if given is None else "--spend-limit",
                 raised=given is not None and allowed is not None and given > allowed,
                 allowance=(plan or {}).get("brief_and_patch_cost_per_investigation_usd", 0.0),
                 windows=[list(w) for w in record.get("replay_windows", [])])

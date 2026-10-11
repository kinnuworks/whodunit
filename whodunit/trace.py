"""The investigation's own trace.

`whodunit investigate` sends one trace per case: a span for each round of the lineup, and
spans for the motive, the brief, the ruling, each fix attempt and the checks on it. So the tool
that reads an agent's traces can be read the same way.

The trace goes to neatlogs cloud when the Neatlogs SDK is installed (`uv sync --extra trace`)
and NEATLOGS_API_KEY is in .env. Without the SDK or the key nothing is sent, and everything
else works the same. WHODUNIT_TRACE picks where it goes:

    cloud      neatlogs cloud (default)
    neatroots  the local collector, which needs no key
    off        nowhere
"""

import os
from typing import Any, Callable

from .env import load_env

CLOUD = "https://ingest.neatlogs.com"


class Trace:
    """Spans for one investigation. Every method is safe to call when tracing is off."""

    def __init__(self, case_id: str, where: str | None = None):
        self.case_id = case_id
        self.sdk: Any = None
        self.where = "off"
        self.trace_id: str | None = None
        self.note = ""  # why nothing is being sent, when nothing is
        where = where or os.environ.get("WHODUNIT_TRACE", "cloud")
        if where == "off":
            self.note = "tracing is switched off"
            return
        try:
            import neatlogs
        except ImportError:
            self.note = "the Neatlogs SDK is not installed (uv sync --extra trace)"
            return
        if where == "cloud":
            load_env()
            key, endpoint = os.environ.get("NEATLOGS_API_KEY", ""), CLOUD
            if not key:
                self.note = "NEATLOGS_API_KEY is not in .env"
                return
        elif where == "neatroots":
            key, endpoint = "neatroots-local", os.environ.get("NEATLOGS_ENDPOINT", "http://localhost:4100")
        else:
            self.note = f"WHODUNIT_TRACE={where} is not one of cloud, neatroots, off"
            return
        try:
            neatlogs.init(api_key=key, endpoint=endpoint, workflow_name="whodunit", tags=[f"case:{case_id}", "whodunit"],
                          instrumentations=[], flush_interval=1.0)
        except Exception as exc:  # a tracing problem must never stop an investigation
            self.note = f"the Neatlogs SDK would not start: {exc}"
            return
        self.sdk, self.where = neatlogs, where

    @property
    def on(self) -> bool:
        return self.sdk is not None

    def step(self, name: str, given: dict, work: Callable[[], Any], kind: str = "CHAIN") -> Any:
        """Run `work()` inside a span and return what it returns.

        The span's input is `given` and its output is the return value, so `work` should return
        a small summary of what happened. Spans nest the way the calls do.
        """
        if not self.on:
            return work()

        @self.sdk.span(kind=kind, name=name)
        def traced(**given):
            return work()

        return traced(**given)

    def root(self, given: dict, work: Callable[[], Any]) -> Any:
        """The span the whole investigation runs inside. Its trace id is kept for the case record."""
        def inside():
            if self.on:
                carrier: dict = {}
                try:
                    self.sdk.inject_trace_context(carrier)  # "00-<trace id>-<span id>-<flags>"
                    self.trace_id = carrier.get("traceparent", "").split("-")[1]
                except Exception:
                    self.trace_id = None
            return work()

        # The case id is in the span's input as well as the tags, because cloud search reads span text.
        return self.step("whodunit investigate", {"case": self.case_id, **given}, inside, kind="WORKFLOW")

    def close(self) -> None:
        if self.on:
            try:
                self.sdk.flush()
                self.sdk.shutdown()
            except Exception:
                pass


OFF = Trace("", where="off")

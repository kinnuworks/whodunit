"""A small client for the MCP endpoints of neatroots (local) and neatlogs cloud.

Both speak JSON-RPC over HTTP. This is the only place whodunit talks to them, and it uses
nothing outside the standard library.
"""

import json
import os
import re
import urllib.error
import urllib.request

NEATROOTS = "http://localhost:4100/mcp"
NEATLOGS = "https://ingest.neatlogs.com/mcp"


class NeatError(RuntimeError):
    pass


class Mcp:
    def __init__(self, url: str = NEATROOTS, token: str | None = None, timeout: float = 60.0):
        self.url, self.token, self.timeout = url, token, timeout
        self.session: str | None = None
        self.ready = False

    def _post(self, method: str, params: dict | None = None, notify: bool = False):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            body["id"] = 1
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        request = urllib.request.Request(self.url, json.dumps(body).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self.session = response.headers.get("Mcp-Session-Id") or self.session
                raw = response.read().decode()
                kind = response.headers.get("Content-Type") or ""
        except urllib.error.HTTPError as exc:
            raise NeatError(f"{self.url} answered {exc.code} to {method}") from None
        except OSError as exc:
            raise NeatError(f"{self.url} is not reachable: {exc}") from None
        if notify or not raw.strip():
            return None
        if "text/event-stream" in kind:
            raw = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")][-1]
        reply = json.loads(raw)
        if "error" in reply:
            raise NeatError(f"{method} failed: {reply['error'].get('message', reply['error'])}")
        return reply.get("result")

    def call(self, tool: str, **arguments):
        """Call one tool and return its result, parsed from JSON when it is JSON."""
        if not self.ready:
            self._post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "whodunit", "version": "0.1"}})
            self._post("notifications/initialized", {}, notify=True)
            self.ready = True
        result = self._post("tools/call", {"name": tool, "arguments": arguments}) or {}
        text = "\n".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
        if result.get("isError"):
            raise NeatError(f"{tool} failed: {text[:300]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


MODEL_ID = re.compile(r"\b(?:claude|gpt|gemini|qwen|llama|mistral)(?:[-:.]?\d[\w.:\-]*|-[a-z][\w.:\-]*)", re.I)  # a family name with a version or a variant after it
SDK_PREFIX = re.compile(r"(?<![./\w])(?:openai|anthropic|litellm)\.(?=\w)")  # "sdk.chat.completions.create", "sdk.SomeError", and not a host name


def unnamed(text: str) -> str:
    """Trace text with model ids and SDK names taken out, for anything that ends up in a record.

    A case file names no model and no vendor. An id becomes "small model" or "larger model" when
    its name says which, and a span called after an SDK keeps only the call's own name. Span ids
    are untouched, so the run can still be looked up as it was traced.
    """
    def tier(match: re.Match) -> str:
        name = match.group(0).lower().rstrip(".:-")
        rest = match.group(0)[len(name):]  # a full stop that ended the sentence, say
        if any(word in name for word in ("haiku", "mini", "nano", "-ha")):
            return "small model" + rest
        return ("larger model" if any(word in name for word in ("sonnet", "opus", "-so", "-op")) else "model") + rest

    return SDK_PREFIX.sub("", MODEL_ID.sub(tier, text))


def select_all(mcp: Mcp, sql: str, cap: int = 5000) -> list[dict]:
    """Run a SELECT and page through it. neatroots hands back at most 200 rows per query."""
    rows: list[dict] = []
    while len(rows) < cap:
        page = mcp.call("query_sql", sql=f"{sql} limit 200 offset {len(rows)}").get("rows", [])
        rows += page
        if len(page) < 200:
            break
    return rows


def neatroots() -> Mcp:
    return Mcp(os.environ.get("NEATROOTS_MCP", NEATROOTS))


def replay_runs(mcp: Mcp, case_id: str, sha: str | None = None, limit: int = 200) -> list[dict]:
    """Runs neatroots holds for a case, newest first, each with the commit it ran on.

    The agent writes its tags into the run_info span, which is where this reads them from.
    """
    like = f"%case:{case_id}%" if sha is None else f"%commit:{sha}%case:{case_id}%"
    safe = like.replace("'", "''")
    rows = mcp.call("query_sql", sql=(
        "select r.trace_id, r.status, r.started_ms, r.total_tokens, r.prompt_tokens, r.completion_tokens, "
        "r.error_count, r.finding_count, r.input_preview, r.output_preview, s.output_preview as info "
        "from runs r join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
        f"where s.attributes like '{safe}' order by r.started_ms desc limit {int(limit)}"
    ))
    out = []
    for row in rows.get("rows", []):
        tags = []
        try:
            tags = json.loads(row.pop("info") or "{}").get("tags", [])
        except (json.JSONDecodeError, AttributeError):
            pass
        row["commit"] = next((t.split(":", 1)[1] for t in tags if t.startswith("commit:")), None)
        row["case"] = next((t.split(":", 1)[1] for t in tags if t.startswith("case:")), None)
        out.append(row)
    return out

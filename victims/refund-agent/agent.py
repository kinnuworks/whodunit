"""A small refund agent, traced with the public Neatlogs SDK.

Adapted from the refund-agent example in neatroots (Apache-2.0). Changes from the
original: steering is removed, the model and the trace destination are each one
setting, replays read their input from neatroots, and every run is tagged with
the commit it ran on.

    uv run agent.py "Please refund order 1001 for customer cust_9."
    REFUND_LLM=gateway uv run agent.py "..."     # the hackathon gateway
    TRACE_TO=neatlogs uv run agent.py "..."      # send the trace to neatlogs cloud

Settings, all environment variables:

    REFUND_LLM   mock (default), fake, gateway or own
    REFUND_MODEL model id, overrides the default for the chosen REFUND_LLM
    TRACE_TO     neatroots (default) or neatlogs
    WHODUNIT_COMMIT, WHODUNIT_CASE   added to the trace as tags by the replay runner
    WHODUNIT_ENV path to the .env file, if it is not in a parent folder
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env_file() -> None:
    """Read keys from .env into this process. Values already set in the environment win."""
    explicit = os.environ.get("WHODUNIT_ENV")
    candidates = [Path(explicit)] if explicit else [p / ".env" for p in (HERE, *HERE.parents)]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def need(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"{name} is not set. Add it to .env at the repo root.")
    return value


def llm_settings() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) for the chosen REFUND_LLM."""
    choice = os.environ.get("REFUND_LLM", "mock")
    if choice == "mock":  # neatroots mock-llm
        return os.environ.get("MOCK_LLM_URL", "http://127.0.0.1:4110/v1"), "mock", "mock"
    if choice == "fake":  # python fake_llm.py
        return os.environ.get("FAKE_LLM_URL", "http://127.0.0.1:4199/v1"), "fake", "fake"
    load_env_file()
    if choice == "gateway":
        return need("LITELLM_BASE_URL"), need("LITELLM_API_KEY"), "claude-haiku"
    if choice == "own":
        return "https://api.anthropic.com/v1/", need("ANTHROPIC_API_KEY"), "claude-haiku-5-5"
    sys.exit(f"REFUND_LLM={choice} is not one of mock, fake, gateway, own.")


def trace_settings() -> tuple[str, str]:
    """Return (endpoint, api_key) for the chosen TRACE_TO."""
    choice = os.environ.get("TRACE_TO", "neatroots")
    if choice == "neatroots":
        # neatroots sets NEATLOGS_ENDPOINT itself when it replays the agent.
        return os.environ.get("NEATLOGS_ENDPOINT", "http://localhost:4100"), "neatroots-local"
    if choice == "neatlogs":
        load_env_file()
        return "https://ingest.neatlogs.com", need("NEATLOGS_API_KEY")
    sys.exit(f"TRACE_TO={choice} is not one of neatroots, neatlogs.")


def current_commit() -> str:
    given = os.environ.get("WHODUNIT_COMMIT")
    if given:
        return given
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_tags() -> list[str]:
    tags = [f"commit:{current_commit()}", f"llm:{os.environ.get('REFUND_LLM', 'mock')}"]
    for name, label in (("WHODUNIT_CASE", "case"), ("NEATROOTS_REPLAY_ID", "replay")):
        if os.environ.get(name):
            tags.append(f"{label}:{os.environ[name]}")
    return tags


LLM_BASE_URL, LLM_API_KEY, DEFAULT_MODEL = llm_settings()
MODEL = os.environ.get("REFUND_MODEL", DEFAULT_MODEL)
TRACE_ENDPOINT, TRACE_API_KEY = trace_settings()

import neatlogs  # noqa: E402
from neatlogs import span  # noqa: E402

TAGS = run_tags()

neatlogs.init(
    api_key=TRACE_API_KEY,
    endpoint=TRACE_ENDPOINT,
    workflow_name=os.environ.get("WORKFLOW", "refund-agent"),
    tags=TAGS,
    instrumentations=["openai"],
    flush_interval=0.2,
)

from openai import OpenAI  # noqa: E402  (import after neatlogs.init)

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

SYSTEM_RULES = [
    "You are a refund agent for an online shop.",
    "Use lookup_order to find an order before refunding it.",
    "Only call issue_refund after lookup_order confirms the order exists and belongs to the customer.",
    "Never refund more than the order amount.",
    "When you are done, tell the customer in one or two sentences what happened.",
]
SYSTEM = " ".join(SYSTEM_RULES)
TOOLS = [
    {"type": "function", "function": {"name": "lookup_order",
     "description": "Look up an order by id. Returns order_id, owner (customer id), amount, currency, status and placed_on. "
                     "If the order id does not exist, returns an error instead.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "issue_refund",
     "description": "Refund an order for the given amount. Returns the order_id and the amount refunded.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}}, "required": ["order_id", "amount"]}}},
]
ORDERS = {
    "1001": {"order_id": "1001", "owner": "cust_9", "amount": 42.0, "currency": "USD", "status": "delivered", "placed_on": "2026-09-01"},
    "1002": {"order_id": "1002", "owner": "cust_9", "amount": 18.5, "currency": "USD", "status": "delivered", "placed_on": "2026-09-02"},
    "2002": {"order_id": "2002", "owner": "cust_4", "amount": 30.0, "currency": "USD", "status": "shipped", "placed_on": "2026-09-15"},
    "3003": {"order_id": "3003", "owner": "cust_7", "amount": 129.99, "currency": "USD", "status": "delivered", "placed_on": "2026-09-28"},
    "4004": {"order_id": "4004", "owner": "cust_2", "amount": 75.0, "currency": "EUR", "status": "delivered", "placed_on": "2026-09-20"},
    "5005": {"order_id": "5005", "owner": "cust_3", "amount": 64.75, "currency": "USD", "status": "delivered", "placed_on": "2026-09-25"},
    "6006": {"order_id": "6006", "owner": "cust_9", "amount": 25.0, "currency": "USD", "status": "delivered", "placed_on": "2026-09-18"},
    "7007": {"order_id": "7007", "owner": "cust_9", "amount": 60.0, "currency": "USD", "status": "delivered", "placed_on": "2026-10-02"},
}
REFUNDS: list[dict] = []  # what this run paid out, for the checks to read


@span(kind="TOOL", name="lookup_order")
def lookup_order(order_id: str):
    if order_id not in ORDERS:
        raise LookupError(f"404: order {order_id} not found")
    return ORDERS[order_id]


@span(kind="TOOL", name="issue_refund")
def issue_refund(order_id: str, amount: float):
    refund = {"refunded": amount, "order_id": order_id}
    REFUNDS.append(refund)
    return refund


def call_tool(name, args):
    fn = {"lookup_order": lookup_order, "issue_refund": issue_refund}[name]
    try:
        return json.dumps(fn(**args))
    except Exception as exc:  # the agent sees tool errors as results
        print(f"tool call failed: {name}: {exc}", file=sys.stderr)
        return json.dumps({"error": str(exc)})


@span(kind="CHAIN", name="run_info")
def run_info():
    """Put the tags in a span's output too. neatlogs cloud search reads span text and skips tags."""
    return {"tags": TAGS, "commit_short": current_commit()[:12], "model": MODEL}


@span(kind="WORKFLOW", name="refund")
def run(request: str, max_steps: int = 8):
    run_info()
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request}]
    for _ in range(max_steps):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, max_tokens=300)
        m = r.choices[0].message
        if not m.tool_calls:
            return m.content
        messages.append({"role": "assistant", "content": m.content, "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        for tc in m.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": call_tool(tc.function.name, args)})
    return "Stopped after too many steps."


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--json"]
    request = os.environ.get("NEATROOTS_REPLAY_INPUT") or " ".join(args) or "Please refund order 1001 for customer cust_9."
    try:
        reply = run(request)
        if "--json" in sys.argv:
            print(json.dumps({"request": request, "reply": reply, "refunds": REFUNDS, "model": MODEL}))
        else:
            print(reply)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()

"""A small refund agent, traced with the public Neatlogs SDK.

Adapted from the refund-agent example in neatroots (Apache-2.0). Changes from the
original: steering is removed, the model and the trace destination are each one
setting, replays read their input from neatroots, and every run is tagged with
the commit it ran on.

    uv run agent.py "{example}"
    REFUND_LLM=gateway uv run agent.py "..."     # the hackathon gateway
    TRACE_TO=neatlogs uv run agent.py "..."      # send the trace to neatlogs cloud
    uv run agent.py "..." --quiet                # skip printing the reply, keep only the trace

Settings, all environment variables:

    REFUND_LLM   mock (default), fake, gateway or own
    REFUND_MODEL model id, overrides the default for the chosen REFUND_LLM
    TRACE_TO     neatroots (default) or neatlogs
    WHODUNIT_COMMIT, WHODUNIT_CASE   added to the trace as tags by the replay runner
    WHODUNIT_ENV path to the .env file, if it is not in a parent folder
"""

import functools
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_REQUEST = "Please refund order 1001 for customer cust_9."

__doc__ = __doc__.format(example=DEFAULT_REQUEST)

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


@functools.lru_cache(maxsize=1)
def agent_version() -> str:
    import tomllib

    with open(HERE / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


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

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=30.0, max_retries=2)

SYSTEM_RULES = [
    # Tone: how to come across to an upset customer
    "You are a refund agent for an online shop. Customers who reach you are often frustrated, "
    "so be warm and empathetic, and make clear you're on their side and will do what it takes to sort things out.",
    "Start your reply by acknowledging what went wrong for the customer, in your own words, before you say "
    "what you did about it.",
    "Give customers the benefit of the doubt on small details, like a mistyped order number or an imprecise "
    "amount or date. Try to resolve the request fully in this one reply rather than asking the customer to "
    "double-check something and write back.",
    # Lookups and ownership: when to call lookup_order vs issue_refund, and whose order it is
    "If the customer has already given both an order number and an amount, call issue_refund directly with "
    "those, without calling lookup_order first, unless you still need to check whether the order has been "
    "delivered yet.",
    "Only call lookup_order when the order number or the amount is missing or unclear, or when you need to "
    "check whether the order has been delivered yet, to find or confirm it before refunding.",
    "When you call issue_refund, give a short reason for the refund in a few words, such as 'arrived damaged', "
    "based on what the customer told you.",
    "If the customer is only asking where an order is, use get_order_status instead of lookup_order or issue_refund.",
    # Typos: retry likely mistypes of the order number
    "Customers often mistype order numbers. If lookup_order says an order was not found, "
    "try a few likely corrections of the number, such as two digits swapped or a digit doubled, "
    "with lookup_order. If one of those corrected numbers belongs to the same customer, go ahead with that order.",
    "To check whether an order is the customer's, call lookup_order and compare the owner field it returns to "
    "the customer id the customer gave you. That's the only account check there is, there's no separate lookup "
    "for customer accounts, so never tell a customer you can't look up their account. A matching owner means "
    "you're clear to go ahead, including calling issue_refund.",
    "If an order doesn't belong to this customer, or you can't confirm it does, never say whose it is or mention "
    "another customer or any internal id. Don't suggest the customer did anything wrong. Just let them know you "
    "can't apply it to their account and that you'll get them sorted, and ask for whatever you need to find the "
    "right order.",
    # Shipped orders: a refund request before the order has even arrived
    "If a refund request is for an order that's still shipped, not yet delivered, don't issue the refund yet. "
    "Reassure the customer it's on its way, tell them when it was placed (the placed_on date), and let them "
    "know they're welcome to come back for a refund if it doesn't turn up or they still don't want it once it "
    "arrives.",
    # Refunds: what issue_refund can and can't do
    "Never refund more than the order amount.",
    "You can only issue a refund, not send a replacement. If a replacement would make sense for what the "
    "customer described, say so and offer them the choice between that refund and a replacement, and tell "
    "them a person will follow up to arrange the replacement if they'd rather have that.",
    # Wrapping up: what to tell the customer at the end
    "When you are done, tell the customer in one or two warm, plain sentences what happened.",
]
SYSTEM = " ".join(SYSTEM_RULES)
TOOLS = [
    {"type": "function", "function": {"name": "lookup_order",
     "description": "Look up an order by id. Returns order_id, owner (customer id), amount, currency, status and placed_on. "
                     "If the order id does not exist, returns an error instead.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "issue_refund",
     "description": "Refund an order for the given amount. Returns the order_id and the amount refunded.",
     "parameters": {"type": "object", "properties": {
         "order_id": {"type": "string"},
         "amount": {"type": "number"},
         "reason": {"type": "string", "description": "Short free text reason for the refund, such as 'arrived damaged'."},
     }, "required": ["order_id", "amount", "reason"]}}},
    {"type": "function", "function": {"name": "get_order_status",
     "description": "Look up an order's status by id, without refunding it. Returns order_id, status and placed_on. "
                     "If the order id does not exist, returns an error instead.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
]
ORDERS = json.loads((HERE / "orders.json").read_text())
REFUNDS: list[dict] = []  # what this run paid out, for the checks to read


@span(kind="TOOL", name="lookup_order")
def lookup_order(order_id: str):
    """Look up an order by id. Returns the order dict, or raises LookupError if it does not exist."""
    if order_id not in ORDERS:
        raise LookupError(f"404: order {order_id} not found")
    return ORDERS[order_id]


@span(kind="TOOL", name="issue_refund")
def issue_refund(order_id: str, amount: float, reason: str):
    """Record a refund for an order. Returns a dict with the rounded amount refunded, the order_id and the reason."""
    refund = {"refunded": round(amount), "order_id": order_id, "reason": reason}
    REFUNDS.append(refund)
    return refund


@span(kind="TOOL", name="get_order_status")
def get_order_status(order_id: str):
    """Look up an order's status by id, without refunding it. Returns order_id, status and placed_on,
    or raises LookupError if the order does not exist."""
    if order_id not in ORDERS:
        raise LookupError(f"404: order {order_id} not found")
    order = ORDERS[order_id]
    return {"order_id": order["order_id"], "status": order["status"], "placed_on": order["placed_on"]}


TOOL_FUNCTIONS = {"lookup_order": lookup_order, "issue_refund": issue_refund, "get_order_status": get_order_status}


def call_tool(name, args):
    """Dispatch a tool call by name with its arguments. Returns the tool's result as a JSON string,
    or a JSON string with an "error" key if the tool call raised."""
    fn = TOOL_FUNCTIONS[name]
    try:
        return json.dumps(fn(**args))
    except Exception as exc:  # the agent sees tool errors as results
        timestamp = datetime.now().strftime("%H:%M:%S")
        order_id = args.get("order_id")
        if order_id is not None:
            print(f"[{timestamp}] tool {name} failed for order {order_id}: {exc}", file=sys.stderr)
        else:
            print(f"[{timestamp}] tool {name} failed: {exc}", file=sys.stderr)
        return json.dumps({"error": str(exc)})


@span(kind="CHAIN", name="run_info")
def run_info(max_steps: int):
    """Put the tags in a span's output too. neatlogs cloud search reads span text and skips tags."""
    return {
        "tags": TAGS,
        "commit_short": current_commit()[:12],
        "model": MODEL,
        "version": agent_version(),
        "max_steps": max_steps,
    }


MODEL_CALLS = 0


@span(kind="WORKFLOW", name="refund")
def run(request: str, max_steps: int = 3):
    global MODEL_CALLS
    run_info(max_steps)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request}]
    for _ in range(max_steps):
        r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, max_tokens=150)
        MODEL_CALLS += 1
        m = r.choices[0].message
        if not m.tool_calls:
            return m.content
        messages.append({"role": "assistant", "content": m.content, "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] tool {tc.function.name} got bad arguments: {exc}", file=sys.stderr)
                content = json.dumps({"error": f"invalid arguments JSON: {exc}"})
            else:
                content = call_tool(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
    return "I couldn't finish this one. A person will follow up with you shortly."


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a not in ("--json", "--quiet")]
    request = os.environ.get("NEATROOTS_REPLAY_INPUT") or " ".join(args) or DEFAULT_REQUEST
    try:
        reply = run(request)
        if "--json" in sys.argv:
            print(json.dumps({"request": request, "reply": reply, "refunds": REFUNDS, "model": MODEL,
                              "model_calls": MODEL_CALLS}))
        elif "--quiet" not in sys.argv:
            print(reply)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()

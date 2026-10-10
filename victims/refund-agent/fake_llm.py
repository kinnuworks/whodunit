"""A scripted OpenAI-compatible chat server, so the refund agent runs with no model and no key.

Adapted from the refund-agent example in neatroots (Apache-2.0). The original looped on a
failing lookup until a steering note arrived. This one plays a careful agent: it looks the
order up, refunds the full amount if the order belongs to the customer, and says what it did.

    python fake_llm.py [port] [log file]      # port 4199 by default

Every request is appended to requests.jsonl.
"""

import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[2] if len(sys.argv) > 2 else "requests.jsonl"


def tool_call(n: int, name: str, args: dict) -> tuple[dict, str]:
    call = {"id": f"call_{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    return {"role": "assistant", "content": None, "tool_calls": [call]}, "tool_calls"


def say(text: str) -> tuple[dict, str]:
    return {"role": "assistant", "content": text}, "stop"


def next_message(messages: list[dict]) -> tuple[dict, str]:
    request = next((m.get("content") or "" for m in messages if m.get("role") == "user"), "")
    order = re.search(r"order\s+#?(\d+)", request, re.I)
    customer = re.search(r"cust_\w+", request)
    results = [json.loads(m.get("content") or "{}") for m in messages if m.get("role") == "tool"]
    if order is None:
        return say("Which order would you like refunded? Please send the order id.")
    order_id = order.group(1)
    if not results:
        return tool_call(0, "lookup_order", {"order_id": order_id})
    found = results[0]
    if "error" in found:
        return say(f"I could not find order {order_id}. Please check the order id.")
    if customer and found.get("owner") != customer.group(0):
        return say(f"Order {order_id} belongs to a different customer, so I cannot refund it.")
    if len(results) == 1:
        return tool_call(1, "issue_refund", {"order_id": order_id, "amount": found["amount"]})
    return say(f"Order {order_id} has been refunded in full: {found['amount']:.2f}.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        with open(LOG, "a") as f:
            f.write(json.dumps(body) + "\n")
        message, finish = next_message(body.get("messages", []))
        resp = {
            "id": f"chatcmpl-{time.time_ns()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "fake"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52},
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4199
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

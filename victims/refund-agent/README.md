# Refund agent

This is the agent Whodunit investigates. It takes a refund request, looks the order up, and refunds it only if the order exists and belongs to the customer. It can also answer a plain "where is my order?" question with `get_order_status`, which returns the status and placed_on date without touching a refund. It is small on purpose, so that a change to a prompt or a tool shows up clearly in its traces.

It started as the `refund-agent` example that ships with neatroots, which is licensed under Apache-2.0. A copy of that licence is in `LICENSE`. The changes made here are listed at the bottom of this file.

## How refunds are decided

These are the rules the agent follows today, in plain words. They live in `SYSTEM_RULES` in `agent.py`.

- Be warm. Acknowledge what went wrong before saying what was done about it, and try to settle the request in one reply instead of asking the customer to come back with more details.
- Give the customer the benefit of the doubt on small mistakes, like a mistyped order number or an approximate amount or date.
- If the customer already gave an order number and an amount, go straight to `issue_refund` with those, unless the agent still needs to check whether the order has been delivered. Otherwise, use `lookup_order` first to find or confirm the order.
- A refund needs a short reason, such as "arrived damaged", taken from what the customer said.
- A plain "where is my order?" question gets `get_order_status`, not a lookup or a refund.
- If `lookup_order` can't find the order number, try a few likely typos of it, such as two digits swapped or a digit doubled. If one of those belongs to the same customer, use that order.
- An order belongs to the customer when the owner field `lookup_order` returns matches the customer id given. That's the only ownership check there is.
- If an order doesn't belong to the customer, or ownership can't be confirmed, the agent never says whose it is or hints that the customer did anything wrong. It just says it can't apply it to their account yet and asks for what it needs to find the right order.
- If the order hasn't been delivered yet, the agent doesn't refund it. It reassures the customer, mentions when the order was placed, and tells them they can come back if it doesn't arrive or they decide they don't want it after all.
- A refund is never for more than the order amount.
- The agent can only refund, not send a replacement. Where a replacement would fit, it offers the customer a choice between the two and says a person will follow up for the replacement.
- The reply ends with one or two plain, warm sentences telling the customer what happened.

## Run it

You need [uv](https://docs.astral.sh/uv/) and a running neatroots (`neatroots start`).

```bash
neatroots mock-llm                                              # in another terminal, a key-free stand-in model
uv run agent.py "Please refund order 1001 for customer cust_9."
```

Open http://localhost:4100 to see the run. Add `--json` to get the reply and the refunds paid out as one line of JSON. With `REFUND_LLM=fake` and the command above:

```json
{"request": "Please refund order 1001 for customer cust_9.", "reply": "Order 1001 has been refunded in full: 42.00.", "refunds": [{"refunded": 42, "order_id": "1001", "reason": "customer request"}], "model": "fake", "model_calls": 3}
```

The orders live in `orders.json`, keyed by order id. Each order has an id, owner, amount, currency, status, and placed_on date. Any other order id comes back as a 404 from the lookup tool.

| id | customer | amount | currency | status | placed on |
| --- | --- | --- | --- | --- | --- |
| 1001 | cust_9 | 42.00 | USD | delivered | 2026-09-01 |
| 1002 | cust_9 | 18.50 | USD | delivered | 2026-09-02 |
| 1111 | cust_8 | 55.00 | USD | delivered | 2026-10-06 |
| 1212 | cust_4 | 48.00 | USD | shipped | 2026-10-07 |
| 2002 | cust_4 | 30.00 | USD | shipped | 2026-09-15 |
| 3003 | cust_7 | 129.99 | USD | delivered | 2026-09-28 |
| 4004 | cust_2 | 75.00 | EUR | delivered | 2026-09-20 |
| 5005 | cust_3 | 64.75 | USD | delivered | 2026-09-25 |
| 6006 | cust_9 | 25.00 | USD | delivered | 2026-09-18 |
| 7007 | cust_9 | 60.00 | USD | delivered | 2026-10-02 |
| 8008 | cust_6 | 90.00 | USD | shipped | 2026-10-05 |
| 9009 | cust_5 | 45.00 | USD | delivered | 2026-09-30 |

To add one, add a new key to `orders.json` with the same fields as the others. The order id in the value should match its key.

Status is `delivered` or `shipped`. Today the agent treats both the same: if the order exists and belongs to the customer, it refunds regardless of status.

## Choosing the model

`REFUND_LLM` picks where the model calls go.

| Value | Model | Needs |
| --- | --- | --- |
| `mock` (default) | neatroots' mock LLM on port 4110. It calls a tool by keyword and does not follow the refund rules. | `neatroots mock-llm` |
| `fake` | A scripted careful agent on port 4199. Same answer every time. | `uv run python fake_llm.py` |
| `gateway` | `claude-haiku` on the hackathon gateway | `LITELLM_BASE_URL` and `LITELLM_API_KEY` in `.env` |
| `own` | A small Haiku model on your own key | `ANTHROPIC_API_KEY` in `.env` |

`REFUND_MODEL` overrides the model id. Keep one model for the whole of a case, because Whodunit compares failure rates across commits and a model change would look like a regression.

The agent reads `.env` from the repo root by itself, and only when the chosen setting needs a key.

## Choosing where traces go

`TRACE_TO=neatroots` (the default) sends the run to the local collector on port 4100. `TRACE_TO=neatlogs` sends it to neatlogs cloud with `NEATLOGS_API_KEY` from `.env`. One run goes to one place.

Every run carries tags: `commit:<sha>` for the commit the code ran on, `llm:<setting>`, and `case:<id>` when `WHODUNIT_CASE` is set. The replay runner sets `WHODUNIT_COMMIT` when it runs the agent from a worktree. The same values are written to a `run_info` span, since neatlogs cloud search reads span text and does not read tags. Search the cloud for the first 12 characters of the SHA. The full 40 characters return nothing.

## Replays

```bash
neatroots rerun add refund-agent "uv run -q agent.py" --cwd .
neatroots replay <trace-id> --input "Please refund order 1002 for customer cust_9."
```

During a replay neatroots sets `NEATROOTS_REPLAY_INPUT`, and the agent uses it in place of the command line.

## Smoke check

`smoke.py` is a pytest-free sanity check that never touches the model or `issue_refund`. It loads `orders.json` through `lookup_order` and `get_order_status` and checks that every order has the six expected fields, every currency is a three-letter code, and every amount is positive. Run it with `uv run python smoke.py`.

## Troubleshooting

**Connection refused on port 4100.** neatroots is not running. Start it with `neatroots start` in another terminal before running the agent or a replay.

**Missing LITELLM keys.** `REFUND_LLM=gateway` needs `LITELLM_BASE_URL` and `LITELLM_API_KEY` in `.env` at the repo root. Without them the gateway call fails before it reaches the model. Check the keys are in `.env`, not the shell that launches the agent, since `.env` is read from the repo root by the agent itself.

**The mock LLM ignores the refund rules.** This is expected, not a bug. `REFUND_LLM=mock` calls a tool by keyword and does not check that the order belongs to the customer or exists at all. Use `REFUND_LLM=fake` (`uv run python fake_llm.py`) for a model that follows the rules the same way every time, or `gateway`/`own` for a real model.

## Changes from the neatroots example

- Steering (`neatroots_steer`) is removed, so nothing alters what the model receives between runs.
- The model and the trace destination are each one environment variable.
- The agent reads its replay input from `NEATROOTS_REPLAY_INPUT`.
- Runs are tagged with the commit and the case, and a `run_info` span repeats the tags.
- Orders moved out of `agent.py` into `orders.json`, which now holds ten orders in place of one.
- The refunds a run paid out are kept in memory for checks to read.
- `issue_refund` requires a short reason (such as `arrived damaged`), which is stored with the refund.
- A `get_order_status` tool answers "where is my order?" questions with the status and placed_on date, without refunding anything.
- Each run makes at most 3 model calls, each capped at 150 tokens, to save on gateway spend.
- The OpenAI client carries a 30-second timeout and 2 retries, where the original had neither.
- The `run_info` span also carries the first 12 characters of the hash of `uv.lock`, next to the model and the version, so a run says which dependencies it ran with.
- When the model provider or the network fails (a refused connection, a timeout, a rate limit, a 5xx, a rejected key), the agent prints `provider error: ...` on stderr and exits with code 75. Any other failure keeps its usual exit code. A replay harness can then throw the run away and try again without blaming the commit.
- The system prompt is warmer: it acknowledges what went wrong before saying what was done, gives the customer the benefit of the doubt on a mistyped order number, tries digit-swap and digit-double corrections on a failed lookup, and offers a replacement alongside a refund where that fits.
- If an order doesn't belong to the customer, the agent never names whose it is or mentions another customer.
- `fake_llm.py` plays a careful agent. The original repeated a failing lookup until a steering note arrived.
- Dependencies are in `pyproject.toml` and locked with uv for Python 3.12.

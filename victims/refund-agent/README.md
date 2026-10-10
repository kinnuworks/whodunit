# Refund agent

This is the agent Whodunit investigates. It takes a refund request, looks the order up, and refunds it only if the order exists and belongs to the customer. It can also answer a plain "where is my order?" question with `get_order_status`, which returns the status and placed_on date without touching a refund. It is small on purpose, so that a change to a prompt or a tool shows up clearly in its traces.

It started as the `refund-agent` example that ships with neatroots, which is licensed under Apache-2.0. A copy of that licence is in `LICENSE`. The changes made here are listed at the bottom of this file.

## Run it

You need [uv](https://docs.astral.sh/uv/) and a running neatroots (`neatroots start`).

```bash
neatroots mock-llm                                              # in another terminal, a key-free stand-in model
uv run agent.py "Please refund order 1001 for customer cust_9."
```

Open http://localhost:4100 to see the run. Add `--json` to get the reply and the refunds paid out as one line of JSON.

The orders live in `orders.json`, keyed by order id. It currently has 1001, 1002, 6006 and 7007 (customer `cust_9`), 2002 (`cust_4`), 3003 (`cust_7`), 4004 (`cust_2`, EUR), 5005 (`cust_3`) and 8008 (`cust_6`). Each order has an id, owner, amount, currency, status, and placed_on date. Any other order id comes back as a 404 from the lookup tool.

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

## Troubleshooting

**Connection refused on port 4100.** neatroots is not running. Start it with `neatroots start` in another terminal before running the agent or a replay.

**Missing LITELLM keys.** `REFUND_LLM=gateway` needs `LITELLM_BASE_URL` and `LITELLM_API_KEY` in `.env` at the repo root. Without them the gateway call fails before it reaches the model. Check the keys are in `.env`, not the shell that launches the agent, since `.env` is read from the repo root by the agent itself.

**The mock LLM ignores the refund rules.** This is expected, not a bug. `REFUND_LLM=mock` calls a tool by keyword and does not check that the order belongs to the customer or exists at all. Use `REFUND_LLM=fake` (`uv run python fake_llm.py`) for a model that follows the rules the same way every time, or `gateway`/`own` for a real model.

## Changes from the neatroots example

- Steering (`neatroots_steer`) is removed, so nothing alters what the model receives between runs.
- The model and the trace destination are each one environment variable.
- The agent reads its replay input from `NEATROOTS_REPLAY_INPUT`.
- Runs are tagged with the commit and the case, and a `run_info` span repeats the tags.
- There are eight orders in place of one, and the refunds a run paid out are kept for checks to read.
- `issue_refund` requires a short reason (such as `arrived damaged`), which is stored with the refund.
- Each run makes at most 3 model calls, each capped at 150 tokens.
- A `get_order_status` tool answers "where is my order?" questions with the status and placed_on date, without refunding anything.
- `fake_llm.py` plays a careful agent. The original repeated a failing lookup until a steering note arrived.
- Dependencies are in `pyproject.toml` and locked with uv for Python 3.12.

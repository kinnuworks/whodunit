# Build log

Whodunit, built for neatHack between 10 and 12 October 2026. Times are IST. Newest entry last.

## Saturday 10 October

### 7:05 PM, repo created

The project is Whodunit: given an AI agent that used to work and now fails, find the commit that broke it, show what that commit was asked to do, fix it, and count the damage.

Checked before writing any code:

- neatroots 0.2.6 is running on port 4100 with 0 runs so far. Its local model is not installed, so checks will be rule checks for now.
- The hackathon model gateway lists a small Haiku model. Three parallel calls came back in about 1.4 seconds each, so replays can run a few at a time.
- In a throwaway repo, `entire enable` kept the redaction settings that were already in `.entire/settings.json` and installed 9 agent hooks plus 5 git hooks. Email and phone redaction is on here from the first commit because the session transcripts in this repo are public.

Next: turn Entire on, get the refund agent running with traces going to neatlogs and neatroots, and verify the first checkpoint.

### 7:20 PM, the refund agent runs and both collectors see it

`victims/refund-agent/` now holds the demo target. It started as the `refund-agent` example that ships with neatroots (Apache-2.0, licence copied alongside) and lost its steering hook, so nothing changes what the model receives between runs.

What was run and what came back:

- neatroots: `python -m neatlogs doctor --probe` passed all 8 checks against port 4100. Six agent runs landed under the `refund-agent` workflow with the full span tree, for example run `ffbdcba4` (3 model calls, 2 tool calls, 156 tokens).
- neatlogs cloud: the same probe passed against `ingest.neatlogs.com`, and `search_traces` over MCP found the run that refunded order 1002 through the gateway (trace `61e879c3`, 6 spans, 2,792 tokens).
- Gateway model `claude-haiku` refunded order 1001 for 42.00 and refused order 2002 because it belongs to another customer. Both answers are correct.
- Whole-agent replay works: `neatroots replay ffbdcba4... --input "..."` started run `5b20f1eb` and the agent picked the new input up from `NEATROOTS_REPLAY_INPUT`.

Found out along the way:

- One SDK process sends to one endpoint, so `TRACE_TO` picks neatroots or neatlogs per run.
- Tags reach both stores (`neatlogs.tags` on the root span), but neatlogs cloud search does not read them. Writing the tags into a `run_info` span's output makes them searchable. Even then the full 40 character SHA returns nothing, while a 12 character prefix finds the run. The replay runner should search by prefix.
- neatroots `search_runs` text search does not read tags either. `query_sql` over `spans.attributes` does.
- A run takes about 3 seconds end to end with a scripted model, of which about 2 are Python imports. That is the floor for one replay.
- `neatroots mock-llm` picks a tool by keyword and refunds 9 for any order, so it is good for plumbing and useless as a known-good baseline. `fake_llm.py` is the scripted careful agent for that.

Not tested yet: `REFUND_LLM=own`, the owner's key fallback.

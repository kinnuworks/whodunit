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

### 7:16 PM, the refund agent runs and both collectors see it

`victims/refund-agent/` now holds the demo target. It started as the `refund-agent` example that ships with neatroots (Apache-2.0, licence copied alongside) and lost its steering hook, so nothing changes what the model receives between runs.

What was run and what came back:

- neatroots: `python -m neatlogs doctor --probe` passed all 8 checks against port 4100. Ten agent runs landed under the `refund-agent` workflow (54 spans) with the full span tree, for example run `ffbdcba4` (3 model calls, 2 tool calls, 156 tokens).
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

### 7:17 PM, first Entire checkpoints verified

The hooks do fire for sessions run in the desktop app, which was the open question. Both commits got an `Entire-Checkpoint:` trailer, and `entire checkpoint list` shows 2 checkpoints: `fc9699a4e609` on 601c1fc and `f8f2b3618deb` on d210212.

`entire checkpoint explain --transcript` returned 240 entries, about 955,000 characters. Checked before any push:

- None of the six key values in `.env` appears, in full or by 12 character prefix.
- The owner's email shows only as `[REDACTED_EMAIL]`, 3 times. The 10 to 12 digit strings the phone pattern could match are timestamps and decimals.
- The transcript does carry things that are not secrets and are still personal: the home folder path, the names of every connector installed in the coding agent, and the titles of the private notes index. The owner should read that list before the first push and decide.

Nothing has been pushed.

### 7:31 PM, plain bisect finds a planted bug across 20 commits

The owner ruled that the repo stays private until just before submission, so nothing is pushed yet.

Milestone 2 is in: `whodunit lineup <case file>` checks each suspect commit out into its own git worktree, replays the case inputs there, and bisects.

The run that counts used the real refund agent with the scripted model, on a throwaway history of 20 commits built by `tests/planted.py`. Suspect 14 adds a 10% top-up to every refund, suspect 6 has a syntax error, and four commits never touch the agent.

- It named suspect 14, `Add a 10% goodwill top-up to refunds`, after testing 7 commits with 11 replays in 50 seconds. A scan from the oldest suspect would have tested 14 commits.
- The failing replays paid 46.20 on order 1001, where the case expects 42.00.
- All 11 replays reached neatroots tagged with the case id and their commit, across 7 distinct commits.
- A commit that will not compile is skipped, as `git bisect skip` does. If skipped commits sit right before the culprit, the report lists the suspects that remain and names nobody.

52 fast tests pass in about 11 seconds. They cover every culprit position for 1 to 41 suspects. The end to end test on the real agent passes too, and takes 2 minutes 38 seconds.

Found out along the way:

- A replay costs about 4.5 seconds here, counting the first `uv run` in a fresh worktree, which builds that worktree's environment from the uv cache.
- The planted history has no Entire checkpoints, because nobody asked a coding agent for those commits. The motive step needs the real history from the second session.

### 8:51 PM, the statistical bisect and what the simulator says about it

`whodunit/lineup.py` now has the statistical bisect: one change point, an unknown failure rate on each side with a Beta prior, and an exact posterior over which suspect is the first bad one. It names a commit at 95% and otherwise hands back the remaining suspects with probabilities. `whodunit/simulate.py` runs it against simulated cases next to plain bisect, and `eval/simulator/` holds the charts, the tables and a write-up.

What the simulator found, with 40 suspects and 500 cases per point:

- When good commits never fail, plain bisect with repeats beats the statistical bisect at every budget. On a bug that fails 30% of the time, 80 replays get plain bisect with repeats to 97% and the statistical bisect to 67%. This was not the result hoped for and it is in the write-up as it stands.
- When good commits fail 5% of the time on their own, plain bisect with repeats collapses and gets worse with more replays: 31% right at 40 replays, 4% at 320. The statistical bisect reaches 60% at 160 replays and 84% at 320.
- Plain bisect with one replay per commit is right 10% of the time on the 30% bug.
- The statistical bisect's wrong accusations run from 0% to 7% of cases. The bar is 95%, so 7% is over.

Two changes from the brief, both made because of the simulator. The prior on the good side's failure rate went from uniform to about 5%, which took the 30% bug from 59% solved to 93% at 300 replays. And the next replay is picked by expected information gain. The picker looked like the big win at first. Measured again with the new prior, the two pickers came within a couple of cases of each other, so the write-up says the prior did the work.

### 8:51 PM, a real run got tangled up with the machine

The first try at bisecting a flaky bug in the real agent was thrown away. Three things were going on:

- neatroots now has a local model switched on (`qwen2.5:3b-16k` through Ollama), which it did not at 7 PM. Its `ignored-tool-error` check runs that model on incoming runs, so 4 replays at a time queued model work behind every run, on a machine already busy with other jobs. Load average passed 300 and a 3 second replay took over 2 minutes.
- Replays then hit the 120 second timeout and were counted as failures, which they were not.
- The timeout killed `uv` and left the agent process running. `run_command` now stops the whole process group, with a test.

Worktrees with the same lockfile now share one environment, so a new commit no longer means a new install. The run was restarted at 2 replays at a time.

One good thing came out of it: neatroots raised 4 findings by itself on the flaky lookup failures ("Carried on after a failed tool call", probability 0.82 to 0.89), so its checks do see this bug. One of its explanations is wrong about what the agent did next, with a grounding score of 0.03.

### 8:51 PM, motive, brief, ruling, fix, damages and the case file

All in as commands that read and write one case record: `whodunit motive`, `brief`, `ruling`, `fix`, `check`, `damages` and `open-case`.

- Motive works on this repo's own checkpoints. For commit d210212 Entire shows "no prompt recorded", because that checkpoint covers the second commit of one long turn. Tying the prompt to the commit by time recovers it.
- The brief asks a model for JSON and cuts any sentence whose citation is not a span, commit, checkpoint or session step that is really in the evidence. With no model it falls back to a fixed template and says so.
- The ruling is asked once per kind of change and kept under `rulings/`. Entire Brain is not set up on this machine, so there is no mirror yet.
- The fix reverts or patches on a local branch and replays until it is 95% likely fixed or 95% likely not. With a bug that fails a third of the time, 10 clean replays give 97.6%.
- Damages are counted from neatroots and priced per model from the LLM spans. The prices in the code are list prices from memory and need checking before any number goes to cfo.ai.

85 fast tests pass. They take about 4 and a half minutes on this machine today because of the load.

Still open: the session transcript also carries `ownerAccountUuid` and `ownerOrganizationUuid` fields in its `bridge-session` entries. That goes on the list for the owner to read before anything is pushed.

### 9:06 PM, the statistical bisect finds a bug that fails about a third of the time

This is milestone 3 on the real refund agent with the scripted model. `tests/planted.py` built 40 commits with a lookup bug at suspect 27: a `raise` sits inside a loop over a set of strings, and a set iterates in a different order in each Python process, so the lookup gives up on about one run in three.

- `whodunit lineup` named suspect 27, `Accept order ids written with a # or leading zeros`, at 95.2% after 48 replays across 11 of the 40 commits.
- It put the failure rate at 39% from that commit on and 1% before it. The true rate is about 33%.
- A scan from the oldest suspect would have had to work through 27 commits, each replayed often enough to catch a one in three failure.
- Replay time was 35 minutes, about 44 seconds per replay, on a machine with a load average near 70. The same replay takes 3 to 5 seconds on a quiet machine.

Then the rest of the pipeline on the same case:

- The brief took three tries to get right, and the first two are the interesting part. Both named the right commit and the right symptom and cited real spans, and both got the mechanism wrong: one blamed `lstrip`, the other said the `raise` was outside the loop, which would make it fail every time. Every sentence passed the citation check. So the check keeps a brief tied to the evidence and does nothing to stop a wrong reading of the diff. What fixed it was giving the model the changed code as it reads after the commit, with line numbers and indentation, and the measured failure rates with an instruction to explain why the failure is intermittent. The third brief has the loop, the set order and the 39%.
- Ruling: revert, given on the command line for this throwaway repo. No ruling has been recorded in this repo, because that is the owner's to give.
- Fix: the revert was committed on a local branch and replayed 8 times with no failures, which puts it at 95.8% fixed. The case was kept as a regression test.
- The case file page rendered from the record. A screenshot and the record are in `evidence/`.

Also added: `whodunit onset`, which reads the agent's ordinary runs from neatroots and brackets the failure between a good and a bad ref using the same change-point model, and `eval/score.py`, which scores cases against an answer key and refuses to run if the key's SHA-256 does not match the one committed beforehand.

A real-model case is running now. Dropping the ownership rule from the system prompt in the name of friendlier replies made the gateway's small model refund another customer's order in 3 runs of 8, so that prompt change is planted at suspect 31 of 40 and the statistical bisect is looking for it.

### 9:18 PM, a real prompt regression found on a real model, then patched

This is the case the project is for. In a planted history of 40 commits, suspect 31 is `Make the agent's replies friendlier`. It rewrites the system prompt and, along the way, drops the rule that an order must belong to the customer. Nothing errors. The gateway's small model simply refunds another customer's order some of the time.

- `whodunit lineup` named suspect 31 at 95.5% after 32 replays across 9 of the 40 commits, in 15 minutes of replay time. It put the failure rate at 57% from that commit on and 2% before it.
- The replays cost about 10 cents on the gateway.
- The brief was right on the first try this time. It quotes the dropped rule, points at the span where the model notes the order belongs to `cust_7` and refunds it anyway, and at the passing run where the same mismatch stopped the refund.
- Ruling: patch, given on the command line for this throwaway repo.
- The patch was written by the gateway's larger model. It kept "friendly" and "be warm" and put the ownership rule back. 0 failures in 6 replays, 98.2% likely fixed. Fewer replays were needed than for the lookup bug because this one fails more often.

The record and a screenshot of the case file are in `evidence/`.

Two fixes came out of this run. A reworded prompt was being classed as an agent-code change, because the diff only touches the string lines and the name `SYSTEM` sits in the context. And the damages step was counting every run of the workflow, including ones from before the culprit existed. It now counts ordinary runs on the culprit and later commits, and says so when there are none, as there are none here.

What this case still lacks is a motive. The history is planted, so no coding session asked for friendlier replies. That needs the second session.

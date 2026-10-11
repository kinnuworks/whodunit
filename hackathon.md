# Build log

Whodunit, built for neatHack between 10 and 12 October 2026. Times are IST. Newest entry last.

## Saturday 10 October

### 7:05 PM, repo created

The project is Whodunit: given an AI agent that used to work and now fails, find the commit that broke it, show what that commit was asked to do, fix it, and count the damage.

Checked before writing any code:

- neatroots 0.2.6 is running on port 4100 with 0 runs so far. Its local model is not installed, so checks will be rule checks for now.
- The hackathon model gateway lists a small model. Three parallel calls came back in about 1.4 seconds each, so replays can run a few at a time.
- In a throwaway repo, `entire enable` kept the redaction settings that were already in `.entire/settings.json` and installed 9 agent hooks plus 5 git hooks. Email and phone redaction is on here from the first commit because the session transcripts in this repo are public.

Next: turn Entire on, get the refund agent running with traces going to neatlogs and neatroots, and verify the first checkpoint.

### 7:16 PM, the refund agent runs and both collectors see it

`victims/refund-agent/` now holds the demo target. It started as the `refund-agent` example that ships with neatroots (Apache-2.0, licence copied alongside) and lost its steering hook, so nothing changes what the model receives between runs.

What was run and what came back:

- neatroots: `python -m neatlogs doctor --probe` passed all 8 checks against port 4100. Ten agent runs landed under the `refund-agent` workflow (54 spans) with the full span tree, for example run `ffbdcba4` (3 model calls, 2 tool calls, 156 tokens).
- neatlogs cloud: the same probe passed against `ingest.neatlogs.com`, and `search_traces` over MCP found the run that refunded order 1002 through the gateway (trace `61e879c3`, 6 spans, 2,792 tokens).
- The gateway's small model refunded order 1001 for 42.00 and refused order 2002 because it belongs to another customer. Both answers are correct.
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

- neatroots now has a small local model switched on, which it did not at 7 PM. Its `ignored-tool-error` check runs that model on incoming runs, so 4 replays at a time queued model work behind every run, on a machine already busy with other jobs. Load average passed 300 and a 3 second replay took over 2 minutes.
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

## Sunday 11 October

### 12:29 AM, the victim has a real history

A second coding session grew `victims/refund-agent` while this one stayed out of git. It never edited the agent itself. For each change it called `eval/ask.sh`, which starts a fresh headless coding session with one ordinary request, so every commit has its own Entire checkpoint with the request that led to it.

- 55 commits to the agent in all: 2 sent from this session to test the mechanics, and 53 from the second session. Seven more requests made no commit and were dropped or reworded.
- 5 cases were sealed in `cases/`. Two fail every time and three fail some of the time, by the second session's own probes on the gateway model. The ranges hold 11 to 15 suspects each.
- The answer key is in `eval/answer-key.json`, which git ignores and this session has not opened. Its SHA-256, `d5b98bb3...4dca`, was committed as 4c45f7f before Whodunit ran on any case, and the file on disk matches it.
- `whodunit motive` shows the exact request behind the two test commits, so the motive step now has real material.

What it cost, as the second session reported it: about $18.40 for the 60 coding sessions, about $5 for the second session itself, and its estimate of $2 or less for about 480 probe runs on the gateway. That is roughly $25, which is more than the $10 to $15 this session guessed beforehand.

One thing to fix was found on the first test commit: the headless session added a co-author trailer naming its model. `eval/ask.sh` now turns that off and strips any that slip through.

The judging criteria were read from the public hackathon page and added to `AGENTS.md`. Two things stand out. cfo.ai is required and nothing exists for it yet. And neatroots, where most of the tracing work has gone, is not named on the page, so the evidence needs to show up in neatlogs cloud.

### 1:06 AM, the sealed eval: five planted regressions, none wrongly accused

Whodunit ran on the five sealed cases with replays on the gateway's small model. The answer key stayed unopened until every case had run. `eval/sealed/README.md` has the table.

- With 120 replays allowed per case: 3 of 5 solved, 0 wrong accusations, 2 where nobody was named.
- The two open cases were resumed from their own replays with more allowed, and both were then named correctly at 168 replays each. So 5 of 5 in the end, still with no wrong accusation.
- The two slow ones are the bugs that fail least often, about 12% and 14% of the time. On one of them the top suspect at 120 replays was the wrong commit, at 53%, and Whodunit named nobody.
- Replay spend was about $1.91 for all five cases.
- The ranges are short, 11 to 15 suspects, so this says little about savings against a scan on a long history.

For the first time the cases have motives. Three of them, in the words that were typed:

- `turned-away`: "one more for friendlier replies. When someone asks for a refund on an order that's still shipped and hasn't arrived yet, the agent is a bit blunt about it."
- `strangers-paid`: "since we capped the loop at 3 model calls, simple refunds feel slow, and most customers already tell us the order number and the amount."
- `cents-off`: "our new payments provider only accepts refund amounts in whole currency units".

Things that went wrong, and what was done:

- 6 of the 53 new commits carry an `Entire-Checkpoint` trailer that Entire cannot resolve. Its log shows "condensation failed: failed to get commit object: object not found" for those sessions, and `entire doctor` finds nothing to repair. One of the six is the culprit of `half-done-batch`, so that case has no recorded request. Whodunit now says so and falls back to the commit's own message.
- Replays that ran side by side on one commit with one input could not be matched to their runs in neatroots, so one brief was first written without a failing run to look at. Each replay now carries its own tag in the trace, and the brief step makes a few tagged replays when it has no matched failing run.
- Three prompt changes were classed as agent-code, because the prompt is now a list called `SYSTEM_RULES`. Fixed.
- Two model-written briefs were overwritten with the no-model template during testing and had to be written again. That brings the count of model-written briefs and patches to 12, against a guideline of about 10 before Sunday 4:30 PM.
- Session transcripts are full of absolute paths, and those were landing in the case records. The motive step now strips them.

Not done: no ruling has been given for any of the five, because that is the owner's question to answer. The culprits fall into three kinds: prompt (`strangers-paid`, `wrong-order-refunded`), tool code (`cents-off`), and model settings (`half-done-batch`). `turned-away` is classed as agent code and reads like a prompt change, which is one more thing the classifier gets wrong.

### 1:40 AM, a checkpoint takes in every session that is open

Two sessions were open in this folder at once. One ran `whodunit fix`, which committed patches on `whodunit/turned-away` and `whodunit/cents-off`. The other was doing unrelated reading and touched neither branch. Entire attached both sessions to those two commits, as checkpoints `b7aa968e95c5` and `587df29ec38f`.

At 1:21 AM one test was failing, `tests/test_replay.py::test_real_refund_agent_across_20_commits`, with other work uncommitted in the tree.

So a commit's checkpoint can hold a session that had nothing to do with it. The motive step reads checkpoints to find the request behind a culprit, and it needs to pick the session that touched the commit's files. Until it does, work that is unrelated to a change should be done from another folder.

### 1:01 PM, one agent, real fixes, and a stricter idea of "fixed"

The machine slept from about 3 AM to 10:30 AM with jobs in flight, so this entry covers a night's work with a hole in the middle.

Whodunit is now one command. `whodunit investigate <case>` runs the lineup, the motive and brief, the ruling, the fix, the damages and the case file, and stops only when it needs the owner's ruling. The owner was asked revert or patch for three kinds of change, with patch suggested, and said to go ahead. The rulings are in `rulings/` with that noted in each.

The headline run is `cases/whole-history.toml`: one regression, the whole grown history, 57 suspects.

- Before any replay it had two things. entire-graph gave 22 of the 57 commits an alibi (README only, a helper script the agent never calls, and so on). And 18 ordinary runs in neatroots had already asked the same thing, 4 of them wrongly.
- 20 replays across 5 commits then named `ced2ecd`, "Let the agent skip lookup_order when the customer gives order number and amount", at 99.8%. A scan from the oldest suspect would have tested 37 commits.
- The motive, from Entire checkpoint `bfbe27725663`: "since we capped the loop at 3 model calls, simple refunds feel slow, and most customers already tell us the order number and the amount."
- The brief sets the request against the commit: it asked for a shortcut, and the commit removed the ownership check with nothing in its place.
- The ruling came from the standing rule for prompt changes, so nobody was asked.
- A model-written patch was proven on 30 clean replays.
- Damages: 4 of 6 ordinary runs that asked this paid out wrongly, 120.00 in refunds on other people's orders.
- The whole investigation cost about 18 cents of replays.

How the five sealed cases ended:

| Case | Fix | Tries | Proof | Money, from ordinary runs |
| --- | --- | ---: | --- | --- |
| cents-off | patch | 1 | 0 failures in 30 | 0.51 over-refunded in 3 runs |
| strangers-paid | patch | 1 | 0 failures in 30 | 30.00 refunded wrongly in 1 of 3 runs |
| wrong-order-refunded | patch | 1 | 0 failures in 36 | 60.00 refunded wrongly in 1 of 2 runs |
| turned-away | revert | 3 | 0 failures in 30 | 360.00 owed and not refunded in 6 runs |
| half-done-batch | none | 3 | not proven | none seen in 5 runs |

What went wrong, which is most of what was learned:

- The first proof standard was too lenient. A fix was called proven when its replays looked like the good side and not the bad side, and the patch for `turned-away` passed on 3 clean replays. Replayed again as a regression test it failed 2 of 8. It had taken the bug from 9 failures in 10 to about 1 in 10. A fix is now proven only when its failure rate is back within 5 points of the rate before the culprit, at 95%, which takes about 30 clean replays.
- Under that standard `turned-away` shows the recovery ladder working. The first patch failed 5 of 12 replays. The second, written with the first patch and its failures in view, failed 4 of 18. Whodunit then reverted the culprit and proved the revert on 30 clean replays. The request was for friendlier replies, and no wording the model tried kept that without also turning refunds away.
- `half-done-batch` is the case Whodunit could not close. Two patches each left 5 failures in 90 replays, about 6% against 14% before and 1% at baseline. The revert conflicts with later commits. It says "not fixed" and the case file lists all three tries. That one case used 558 replays, about $3.50.
- An earlier, lenient run had `cents-off` fail its first patch (3 of 3) and pass its second. Those records were replaced when the cases were rerun under the stricter standard.
- The gateway answered 504 to a patch request twice. Model calls now retry, and patches are asked for as small search and replace edits in place of whole files, which are quicker to produce.
- A checkpoint takes in every session open in the folder, as the other session found. The motive step now reads each session in a checkpoint and uses the one that edited the commit's files.

Also in: `eval/traffic.py --cases` sends the requests customers were making, so the damages can be read in the shop's currency from the `issue_refund` spans. The entire-graph agent guide is installed with `entire graph init-agents`. `.mcp.json` names the cfo.ai server, which still needs the owner's sign-in.

Spend so far on the gateway is about $13 of $20 by estimate: about $9.80 of small-model calls traced locally, about $1.30 traced to neatlogs cloud, and about $2 of larger-model briefs and patches.

### 1:16 PM, plain bisect on the same sealed cases

Two measurements that bear on the main claim.

The baseline on this agent was clean. Across the six cases, commits before a culprit were replayed 211 times with no failures. The simulator says that in that world plain bisect with retries is the cheaper tool, so it was run on the five sealed cases, with each commit replayed up to 5 times over and called bad on the first failure. One run per case.

- `cents-off`, `strangers-paid` and `turned-away`, which fail most of the time: right on all three, with 55 replays in all against the statistical bisect's 75.
- `wrong-order-refunded`, which fails about one run in eight: a bad commit passed all 5 tries, and plain bisect named "Add a get_order_status tool", an innocent commit three places from the culprit. Nothing in its output says it might be wrong.
- `half-done-batch`, about one run in seven: the bad ref passed 10 replays in a row, so plain bisect had nothing to bisect.

So the honest version of the pitch is narrower than the one this started with. Where a bug fails often, plain bisect with a few retries is enough and costs less. Where it fails rarely, the number of retries has to be guessed before the rate is known, and guessing low gives a confident wrong answer. The statistical bisect spent more there, 168 replays each, and did not name anyone until it was sure. `eval/sealed/README.md` has the table and `eval/sealed/plain/` has the records.

The second measurement: `whole-history` was run again without the entire-graph alibis and without traffic. It took 30 replays across 8 commits to reach 95.4%, against 20 replays across 5 commits and 99.8% with them. One run each way.

Other things since the last entry: a casebook page at `cases/index.html` lists every case, `whodunit investigate --fresh` starts a case over for the video, queries to neatroots now page past its 200-row limit, and the fast tests run in a GitHub Actions workflow. The onset from traffic alone is not sharp on this history: with five regressions in it and only "errored or flagged" to go on, it brackets the whole range. The per-case witness, which judges each run against what the case expects, is what the headline run used.

### 2:00 PM, a review of the repo, and the headline number

A review of the repo listed claims that the code or the records do not back. The rest of today works through that list in order, one commit per item, and each entry says whether the review was right.

The first one was right. The README, the pitch line in `AGENTS.md` and milestone 7 all said 41 commits. That number came from the plan, written before the victim had a history. The headline case has 57 suspects, so all three now say 57. "Suspects: 41. Cleared: 40." stays in `AGENTS.md` where it is marked as sample copy. The case file page was never wrong, because it counts the suspects in the record.

Before the first commit, `entire session list` showed one other session in this folder, idle for half an hour. The owner was told.

### 2:10 PM, the headline brief said "every time" next to a page that said 81%

The review was right. The brief for `whole-history` ended: "The bug is deterministic whenever a customer quotes any valid order number and amount ... it goes straight to issue_refund every time." The same page reported an 81% failure rate, and 2 of the 6 ordinary runs on the culprit or later had done the right thing.

How it happened: the 8 replays from the culprit on all failed, and the only number the model was shown was "about 81%" with no counts behind it. The 81% is lower because ordinary traffic was counted too, and that went wrong in 4 of 6 runs.

What changed in `whodunit/brief.py`:

- A rule check with no model in it. A brief that says always, every time or deterministic, when the measured rate from the culprit on is under 95%, is rejected and asked for once more with the rejected sentences and the measurements in front of the model. If the second draft still says it, those sentences are cut the way a sentence with no real citation is cut. "Does not always" and "non-deterministic" are let through.
- The model now sees the counts, split around the culprit: replays, ordinary runs, and the two together. The lineup stores which commit each ordinary run was on, so later steps can make that split. The `whole-history` record was given the split by asking neatroots the same question the lineup asked. It came back with the same 18 runs and 4 failures.
- `whodunit brief --from-record` writes a brief again from the evidence already collected, with nothing replayed.

What went wrong on the way: the first rewrite got the rate right and then made up a total, "across 26 total runs". Nothing in the measurements says 26. So the check now also holds any count of runs or replays in a sentence against the measurements, and the model is told not to add counts up into new ones. The second rewrite is the one in the record. It says 8 of 8 replays failed from the culprit on, gives the 81% estimate, and says the evidence does not show why some ordinary runs came out right.

Two calls to the larger model, about 6 cents.

### 2:35 PM, an id inside a sentence has to be real too

The review was right on both counts. The `cents-off` brief said "as shown in span ad7eeb7e" and cited `ad7edb7e`. The citation was real and the id in the sentence was one character off, and the check only looked at citations. The same brief said "Python's round() rounds 0.5 and above up", which is not how it treats a half.

What changed in the citation check:

- Any token in a sentence that looks like an id, eight or more hex characters with a digit in them, has to match something in the evidence. If it does not, the sentence is cut and the draft is sent back once, the same way as for the measured rate. Ids that do match are added to the sentence's citations.
- Words in quotation marks have to be in the evidence as quoted, once they are long enough to be a quotation. This was not on the review's list. It came from reading the rewrites: one said the request "did not ask for the recorded refund to differ", when the request's own words were "round the amount to the nearest whole unit before recording it". The model is now told to give the request in its own words, in quotes, and the quotes are checked.
- The model is told not to explain from memory how a language behaves, and that a commit may simply have done what was asked. The old instruction told it to say where the request and the commit part ways, which made it find a gap when there was none.
- When every run from the culprit on failed, the measurements now say that the estimate sits under 100% only because the replays are few. Before that, a rewrite spent a sentence on "the remaining 7% that may pass".

Run over the eight briefs on record, the new check flags one sentence, the one the review named.

Rewriting the `cents-off` brief took six drafts, and I read each one. What was wrong with the ones not kept: a headline that said `round()` "truncates", a claim about what the request had not asked for, "one dollar more" for a difference of 0.25, and one whose last sentence was muddled. The fifth is in the record. The model made the same slip again in it, `ad7eeb7e` for `ad7edb7e`, and this time the check sent the draft back and the second try had the id right. The page says so under the brief. What is still loose in the kept one: its headline says the commit "rounds refund amounts up", which is true of both requests in the case and not of every amount.

Nothing checks arithmetic or meaning. A person still has to read a brief before it is quoted anywhere. About 30 cents of larger-model calls for this and the entry before it.

### 4:30 PM, what "proven" was worth

The review was right, and the number is in the repo now. `eval/simulator/fix-bar.json` has 2,000 simulated fixes per row against the same criterion `whodunit fix` uses. A fix that still fails 4 runs in 100 clears the bar 35 to 38% of the time, depending on how many clean replays there were before the culprit. One that still fails 2 in 100 clears it about 70% of the time. One that fails 10 in 100 clears it 4% of the time.

The criterion stays as it was: a fix is kept when its failure rate is 95% likely to be back within 5 points of the rate before the culprit. What changed is what gets said about it.

- The page, the command line, the README, `pitch/` and the sealed eval write-up no longer say "proven". They give the count and the 95% upper bound on the failure rate after the fix: "0 failures in 30 replays. At most 6.2% at 95%." For the 36-replay case it is 5.2%. For the two patches on `half-done-batch`, 5 failures in 90, it is 10.6%.
- The bound is a quantile of the posterior the criterion already uses for the fix commit, Beta(0.5 + failures, 0.5 + passes), worked out exactly and checked against 200,000 samples.
- The page says under a kept fix that clearing the bar is not proof, with the one-in-three figure.

Earlier entries in this log still say "proven", because that is what was believed when they were written.

What went wrong: the first version of the simulation ran for ten minutes and had to be stopped. The posterior is worked out by sampling, 20,000 draws each time, and the simulation asked for it a few hundred thousand times. It is cached now, which is safe because the seed is fixed, and it still takes about six minutes.

A gap of about an hour and a half before this entry is the session waiting, not work.

### 4:40 PM, wrong accusations, counted against accusations made

The review was right, and what came out is the least comfortable result so far.

`eval/simulator/README.md` gave wrong accusations as a share of all cases, 0% to 7%. Where the lineup mostly names nobody, that number hides how often a named commit is innocent. The tables now give the share of accusations made, for every cell, and the grid goes down to a bug that fails 10% of the time.

For the statistical bisect, pooled over the ten budgets, 40 suspects:

- Clean baseline: 0% wrong at a bug that fails every time, 4.2% at 30%, 6.1% at 20%, 10.8% at 10%.
- Good commits fail 5% of the time: 0.9% at every time, 8.0% at 30%, 18.2% at 20%, and 80.4% at 10%, which is 74 wrong of the 92 commits it named in 5,000 cases.

So "named at 95%" holds for bugs that fail about a third of the time or more, and does not hold for rare ones. On a clean baseline with a 10% bug, plain bisect with repeats is also simply better: 99% right at 320 replays against 60%.

Two of the sealed cases sit near 12% and 14%, so a smaller run copies their shape: 13 suspects, clean baseline, 12% bug, 2,000 cases per row. With 320 replays allowed, which is what those cases had, 4% of accusations are wrong. With 120 it is 13%. The sealed result of five named and none wrongly fits that and is too small to confirm it. `eval/sealed/README.md` now says so.

The README's list of what the tool does not do has this in it, with the numbers.

What went wrong: the regeneration takes about ten minutes now, up from two, and the README had said two. The seventh chart panel sits alone on a third row.

### 4:42 PM, damages that belonged to other cases

The review was right. `whodunit/damages.py` counted a run as bad if it errored or neatroots raised any finding on it, on the culprit or any later commit. The history has five regressions in it, so "25 of 147 runs went bad" on the headline page was the sum of all of them, and the token cost beside it was too.

Now a run is this case's damage only if it fails this case's own check: it asked what one of the case's inputs asks, on the culprit or later, and paid out something other than what the case expects. The lumped count is gone from the record and the page. What the page says for the headline case: 4 of the 6 ordinary runs that asked this failed the check, 120.00 was refunded that should not have been, and those 4 runs cost about a cent in tokens. It still gives the 147 as the number of ordinary runs on those commits, and says that runs that went wrong for other reasons are not counted.

The money figures did not change, because they were already judged against the case. `half-done-batch` now says plainly that none of its 5 matching runs failed.

The traffic. Every ordinary run was sent by `eval/traffic.py`, a script that plays customers against each commit. The agent at an old commit cannot be made to tag its runs differently, so the case file carries it: `traffic_sent_by = "eval/traffic.py"`. The page says under Suspects and under Damages that no real customer was involved and that the amounts are a test shop's. `pitch/business-plan.md` no longer calls the refund amounts measured. It says they were counted from scripted traffic, and that the replay costs are the part that is real spend.

Found on the way, and not on the review's list: the line "the investigation used N replays" counted every run ever tagged with the case id. Recounting today gave 80 for the headline case where the page said 50, because the run without alibis, from this afternoon, used the same case id. The five sealed cases had picked up the plain-bisect replays the same way. The count is now bounded by the time of the record's own first and last replays. With that bound all six came back to what they were: 50, 65, 74, 119, 240 and 558. The existing records got their upper bound from the time they were last committed.

Also wrong in my own first draft of the plan note: I wrote "232 scripted requests over 58 commits". neatroots holds 411 ordinary runs over 60 commits, and 232 is the number that went to neatlogs cloud. The note says "a few hundred".

`tests/test_damages.py` runs the queries against a small SQLite database with a second regression in it.

### 4:44 PM, what the alibis saved

The page and the pitch said 22 of 57 commits had an alibi and stopped there. The number that says what that was worth was already in this log: run again with no alibis and no ordinary runs to go on, the headline case took 30 replays across 8 commits to reach 95.4%, against 20 across 5.

That is now on the page under the alibis, in the README, in the video script and in the sealed eval write-up, each time with the two things that limit it: it is one run each way, and the alibis and the traffic were taken away together, so the 10 replays cannot be split between them.

The page draws it from a file next to the record, `cases/whole-history.ablation.json`. `whodunit lineup --ablation` writes that file from a real run and leaves the case record alone. The file in the repo today was entered by hand from this log, and says so, because the record of the original run was not kept. It gets replaced by a real one when the headline case is rerun at the end of stage 2.

### 4:47 PM, a log that could not go stale

The review was right. On `turned-away` the Fix section showed a revert kept after three tries and the Log said "Proven with a patch after 1 try". On `cents-off` the Log said two tries and Fix showed one.

The Log was a list of lines that `whodunit investigate` printed and stored as it went. Both cases were later rerun one step at a time under the stricter standard, with `whodunit fix`, and that replaced the attempts and left the stored lines as they were.

The page's Log is now worked out from the record as it stands when the page is drawn: the lineup, the motive, the brief, the ruling, one line per fix attempt, any regression replays, and the damages. Nothing an investigation prints is stored any more, and the old lines are out of the six records. There are no times in it, because the record does not hold a time for each step. The investigation's own trace, which is stage 2, is where times will come from.

Two more things turned up while checking each page against its record:

- `half-done-batch` said "No fix was made" and listed none of its three tries, although an earlier entry in this log claims the case file lists all three. It lists them now, under "Not fixed."
- Two records carried a stored note saying "two patches were not proven". It now says they did not clear the bar, to match the wording change from earlier today.

### 4:51 PM, no model and no assistant by name

The review was right. Every case page printed "Written by:" followed by a model id. Every record with a motive named the coding assistant and its model. The trace outlines in the records carried the replay model's id and a span named after an SDK.

What changed:

- A brief records who wrote it as "model" or "template", and for a template why. Which model it was is a setting and stays out of the record. The page says "Written by a model."
- The motive no longer has fields for the assistant or its model. `whodunit motive` says "the coding agent".
- Trace outlines and run comparisons go through one function on their way into a record. A model id becomes "small model" or "larger model", and a span named after an SDK keeps only the call's own name. Span ids are untouched, so the run can still be looked up as it was traced.
- The eight records in `cases/` and `evidence/` were rewritten the same way, and the six pages redrawn.
- Three earlier entries in this log named a model. They now say "a small model".

What is left, on purpose. Three kinds of place still carry a vendor's name, because they quote the agent under investigation and changing a quotation would make the evidence untrue: the culprit's diff, the changed code as it reads after the commit, and the subject line of one suspect commit. That shows on three of the six pages. It is the owner's call whether those should be masked as well.

Also left: `victims/refund-agent/` and its README, which are the thing being investigated and whose history was made by the second session. `eval/ask.sh` and `whodunit/llm.py` name a command and model ids because a command and an API call need them. The price table in `whodunit/damages.py` is keyed by the model name on a trace span. The screenshots in `evidence/` still show the old line, and are due to be retaken in stage 3.

### 4:53 PM, the working brief against the code

The review was right about each thing it named in `AGENTS.md`, and reading the brief against the code turned up a few more.

- Verdicts. The brief said a replay's verdict is read "from neatroots findings or a local check". Only the second is true. The verdict comes from the case's check on what the agent printed, and `list_findings` is never called.
- Rulings. The brief said they are mirrored to Entire Brain. They are files under `rulings/`. Brain is not installed.
- Fixes. The brief said `fix.py` opens the PR or Trail. Nothing here pushes or opens anything.
- Damages. The brief said they are written to cfo.ai. They go to the case record. A write to cfo.ai is a step for a person with the cfo.ai server, and needs the owner's yes.
- Motive. The brief listed `entire why`. The code uses `entire checkpoint explain` only. Line-level provenance is on the list for stage 2.
- Models. The brief said investigation and fix run through the coding agent in headless mode. That is one of four settings and not the default, which is the gateway.
- Grading. The brief said it starts with neatroots rule checks. It is the case's own check.
- The list of MCP tools named eight. The code calls three.
- The milestones read as a plan. Each one now says what became of it. Four are done, the fifth is done in part, and cfo.ai, the AWS runner, the stretch target, the video and the posts are not.
- "Still to do, in order of points" is now "in this order".

The rules that came out of today are in the brief as well: damage is only the runs that fail the case's own check, traffic numbers say they came from a script, a fix is reported as a count with its upper bound, and a brief gets read by a person before it is quoted.

### 4:54 PM, one entry out of this log, one image out of the evidence

The entry of 1:21 AM on 11 October, about other teams' entries, is removed from this log in an ordinary commit. The history is not rewritten, so the text is still in the earlier commits. One line of it was about this build and is kept, moved into the 1:40 AM entry: a test was failing at the time. That test, the end to end run on the real agent with a scripted model, was run again just now and passes in 38 seconds.

`evidence/neathack-bingo.png` is moved to `pitch/`. Nothing in `evidence/` linked to it. What happens to it is the owner's call.

### 4:56 PM, getting ready to go public, without pushing

Four small things, each checked against the code first. All four were as the review said.

- The fix commit took whatever git identity was around, and a clean CI runner has none. `whodunit/fix.py` now signs as `whodunit <whodunit@whodunit.invalid>` for whichever of name and address is not set, and leaves a set identity alone. The test hides the machine's git config and tells git not to guess. It fails without the change.
- The checkpoint link was worked out when the motive was recorded, and there was no remote then, so all six records held an empty link that would have stayed empty after the push. The link is no longer stored. It is worked out from the repo's remote each time a page is drawn. With no remote there is still no link on any page, which is the truth for now.
- A root `LICENSE`, Apache-2.0, the same text as the victim's, and a short section in the README.
- `pitch/posts.md` number 6 said six customers were owed 60.00 each. The record has 360.00 withheld across six runs: three requests owed 90.00 and three owed 30.00. The average is 60.00 and nobody was owed that. Corrected.

That is the end of stage 1. Nothing was pushed, posted, written to cfo.ai or launched. Larger-model calls for the two rewritten briefs came to about 40 cents, and no replays were made.

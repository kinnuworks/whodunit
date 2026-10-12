# Whodunit working brief

Whodunit finds the commit that broke an AI agent. It shows what that commit was asked to do, fixes it, proves the fix, and reports what the breakage cost. The pitch in one line: "57 commits since it last worked. Which one did it?"

This is the brief for whoever writes code here, human or coding agent. Read it before changing anything.

## Sessions in this repo are published

Entire records every coding session in this repo and the repo is public, so the whole transcript of a session can be read by anyone. Treat everything typed, read or printed during a session as public.

- Keys live in `.env`, which git ignores. Never print a value from it, never paste one into a prompt, and never open it with a tool that echoes its contents. Load it inside the code that needs it.
- Do not open private notes, mail, chat logs or any file outside this repo from a session here. If the work seems to need one, stop and ask the owner.
- Email and phone redaction is switched on in `.entire/settings.json`. After the first commit, read the checkpoint with `entire checkpoint explain --transcript` before anything is pushed.
- Never run `entire enable` with `--import-history`. It would pull older sessions from this folder into the public record.

## How one case runs

1. Start from a case file: the failing inputs, what each should have produced, the last good ref and the first bad one. `whodunit onset` can suggest the refs from the agent's ordinary runs in neatroots, and with `--cloud` asks neatlogs when a detection began firing.
2. List the suspect commits between the last good ref and the first bad one. Commits that cannot reach the agent get an alibi from the path filter and from entire-graph. Ordinary runs that already asked what the case asks count as evidence before any replay.
3. Replay the failing inputs against suspect commits in git worktrees. Agent failures are random, so repeat until the result is statistically confident.
4. Name the culprit and pull the Entire checkpoint behind it, which holds the original request and the session.
5. Write the brief, with every sentence checked by rule against the evidence and the measurements.
6. Ask the owner one question (revert, or keep the intent and patch) and remember the ruling.
7. Fix on a local branch, replay the fix against the bar below, and keep the case as a permanent regression test. The code stops there. Pushing the branch and opening a PR or an Entire Trail is the owner's step.
8. Count the damage: the runs that fail the case's own check, the money they moved and what they cost. Writing any of it to cfo.ai is done by hand through the cfo.ai server, with the owner's yes, and no code here does it.

Any description of the project opens with "which commit, and why". The fix comes after that.

## Layout

Python 3.12 through uv, in one repo.

- `whodunit/case.py`: a case is a symptom, the failing inputs, a good ref, a bad ref and a check.
- `whodunit/suspects.py`: the commits in `good..bad` with their Entire checkpoint ids. Commits that cannot reach the agent's code get a lower prior (path filter first, then entire-graph impact).
- `whodunit/replay.py`: one git worktree per commit under test. It runs the target's replay command with the case input, tags the run with the commit SHA and a tag of its own, and takes the verdict from the case's check on what the agent printed (the refunds it made, or a command of the case's choosing). neatroots findings are not read for the verdict. A commit that will not build is skipped, like `git bisect skip`. A run that ends in a provider or network error is voided and tried again, up to three attempts, and never counts. The case file lists how the agent signals it: `void_exit_codes` and, for older commits, `void_stderr`. A timeout gets one more try with double the limit and is a failure only if that times out too.
- `whodunit/graph.py`: the alibis. It asks entire-graph what a commit changed and whether the agent's entry file calls it.
- `whodunit/lineup.py`: plain bisect and the statistical bisect, described below. Before bisecting it weighs today's replays of the two ends against each other, and if the good ref fails about as often as the bad one it names nobody and marks the range clear.
- `whodunit/motive.py`: `entire checkpoint explain` for the culprit, which gives the sessions in its checkpoint. The request is the last prompt typed before the commit, in the session that ran the commit. Two checks follow. The request has to be word for word in the transcript, or the page does not say the quote was checked. And `entire why FILE:LINE --json`, run in a checkout of the culprit on the lines it changed, has to name the same commit, checkpoint, session and request. `whodunit motive --case <case>` does the lookup again for a case record.
- `whodunit/brief.py`: the model writes the root-cause brief from the culprit diff, the relevant slice of the session transcript and a failing run set against a passing one. Rule checks with no model in them cut or send back what does not hold: every sentence cites a span id, a commit or a checkpoint, an id or a quotation inside a sentence has to be in the evidence, and "always" or a count of runs has to agree with what the lineup measured.
- `whodunit/ruling.py`: the ask-once memory (revert or patch, per kind of change), stored as files under `rulings/`. Nothing is mirrored to Entire Brain, which is not installed.
- `whodunit/fix.py`: applies the fix on a local branch, replays it until it clears the bar or plainly does not, and reports the count with a 95% upper bound. A fix that clears the bar is then replayed against the other cases' inputs and `cases/ordinary.toml`, and is not kept if it makes one of them go wrong more often than before it. `whodunit/cli.py` then keeps the case under `cases/` as a regression test. Nothing is pushed and no PR or Trail is opened.
- `whodunit/damages.py`: counts the runs that fail the case's own check, the money they moved and what they cost, from the traces in neatroots. It writes to the case record only.
- `whodunit/casefile/`: the static HTML case file, which is the main demo surface. `whodunit open-case` writes one page and `whodunit casebook` writes them all with an index.
- `whodunit/onset.py`: reads the agent's ordinary runs from neatroots and brackets the failure between a good and a bad ref with the same change-point model. `--cloud` asks neatlogs when a detection began firing.
- `whodunit/opening.py`: `whodunit open-case --from-trace <id>` writes a case file from one failing run. The input comes from the root span, the bad ref from the run_info tags, the expected result from the nearest earlier run of the same input that passed, and the good ref from `onset.py` over every run of that input. With no earlier passing run it asks the owner one question.
- `whodunit/neat.py`, `whodunit/llm.py`, `whodunit/env.py`: the MCP client for neatroots and neatlogs, the one place a model is asked for text, and the `.env` loader.
- `whodunit/trace.py`: the investigation's own trace. One trace per `whodunit investigate`, with a span per lineup round and per step, sent with the Neatlogs SDK when it is installed (`uv sync --extra trace`) and the key is in `.env`. `WHODUNIT_TRACE` is `cloud`, `neatroots` or `off`. The tests always run with it off.
- `whodunit/simulate.py` and `whodunit/chart.py`: the simulator and its SVG charts. Results live in `eval/simulator/`.
- `whodunit/cli.py`: the commands. Each step reads and writes one case record, `<case>.record.json`, next to the case file.
- `eval/`: `score.py` scores cases against a sealed answer key, `traffic.py` sends everyday requests through a history, `probe.py` runs one request a few times at one commit, `ask.sh` starts a fresh coding session with one request, and `SECOND-SESSION.md` briefs the session that grows the victim. `eval/sealed/` and `eval/simulator/` hold the results.
- `tests/planted.py`: throwaway histories with a known culprit (an overpayment, a lookup that fails one run in three, a prompt change that needs a real model).
- `victims/refund-agent/`: the demo target. It starts from the refund agent in neatroots' `examples/` (Apache-2.0, and the README must say so) and grew to 57 commits through real coding-agent requests in a separate session, so the history and its checkpoints are genuine.

### The statistical bisect

Model a single change point c. The failure rate is p_good before c and p_bad from c onward. Estimate both rates by running the two endpoints several times and keeping Beta posteriors. Hold a posterior over c. Each round, replay the commit with the highest expected information gain and update with the Bernoulli outcome. The even split is kept as an option and does about as well. The prior on the good rate is about 5%, loosely held, which matters far more than the choice of picker. Stop at 95% on one commit or when the replay budget runs out, and in the second case report the remaining suspects with their probabilities.

Unit-test it against a simulator. Publish the curve of accuracy against replay budget, next to plain bisect, at failure rates from 100% down to 10%, with wrong accusations counted against accusations made.

The simulator's verdict so far, in `eval/simulator/README.md`: on a clean baseline plain bisect with repeats is cheaper, and on a flaky one it falls apart. The 95% bar means 95% only for bugs that fail about a third of the time or more.

## Tool facts checked on 10 October 2026

### neatroots

Version 0.2.6 is installed at `~/.local/bin/neatroots` and serves on port 4100. It is a local collector with checks and replay, and its MCP endpoint is `http://localhost:4100/mcp`.

- Whole-agent replay: `neatroots rerun add <project> "<command>" --cwd <dir>`, then `neatroots replay <trace-id> [--input ...]`. The agent receives `NEATROOTS_REPLAY_INPUT`, `NEATROOTS_REPLAY_ID` and `NEATLOGS_ENDPOINT`.
- Checks are YAML files in `.neatroots/checks/`. The `rule` kinds (repeat, errors, count, threshold, match, run_end) need no model. `yes_no` questions return a probability and need neatroots' local model. On the evening of 10 October a small local model was found switched on, served on port 11434, and the built-in `ignored-tool-error` check ran it on incoming runs. A burst of replays then queues model work on this machine, so keep replays to two or three at a time while it is on. On the afternoon of 11 October `neatroots status` reported that model as unavailable.
- `neatroots mock-llm` is a key-free stand-in LLM on port 4110.
- `neatroots status` reports "cloud no key". `neatroots cloud forward <trace ids>` sends runs to neatlogs cloud and needs `neatroots cloud login` first, which stores the project key in the macOS Keychain. That is the owner's step. Until it is done, `whodunit forward` records that the runs stayed local.
- MCP tools the code calls: `query_sql`, `get_run_outline` and `compare_runs`. Whodunit replays the agent itself, in worktrees, and does not use neatroots' own `rerun` or `replay`. `list_findings` is not read either, because a verdict comes from the case's check.

### neatlogs cloud

The MCP endpoint is `https://ingest.neatlogs.com/mcp` with the project key as a Bearer token. `search_traces` does full-text search over names, errors and metadata, and no tag filter is documented, so check early that a commit SHA stored in metadata can be searched. `get_trace_context` returns the span tree with inputs and outputs. `get_detection_trend` returns hour or day buckets and dates the onset of failures. The Python SDK needs Python 3.10 to 3.13, takes the Project API key (the `nlw_` key returns 401), and needs `neatlogs.flush()` before exit. `python -m neatlogs doctor --probe` checks the setup.

### Entire

CLI 0.11.4. It captures a checkpoint when a commit follows agent work, stores it under `refs/entire/checkpoints/`, and adds an `Entire-Checkpoint:` trailer to the commit.

- `entire checkpoint explain --commit <sha> --json` returns metadata, and `--transcript` returns the session JSONL.
- `entire why FILE:LINE --json` returns the commit, checkpoint, prompt and session behind a line. `entire blame` works per file.
- `entire plugin install graph`, then `entire graph init-agents --repo .`, sets up entire-graph. Brain is `entire brain setup`. Trails need `entire runner setup -y`.
- Checkpoint links take the form `https://entire.io/gh/OWNER/REPO/commit/FULL_SHA`.
- Not yet verified: whether the hooks fire for sessions run in the desktop app. Run `entire checkpoint list` after the first commit. If it is empty, run the coding agent from a terminal.

### cfo.ai

The MCP endpoint is `https://api.cfo.ai/mcp` and uses OAuth, which the owner has to authorise. Tools include `edit_table_blocks`, `edit_scenarios` and `edit_pages`. The plan should be a multi-page model with stated assumptions, upside and downside scenarios, and a simulator. Every write to cfo.ai needs the owner's yes.

The owner passed on a notice on 11 October: cfo.ai credits are unlimited for the length of the hackathon, and the dashboard does not show it. So credit use is no reason to keep the model small.

## Models and spend

- Replays of the refund agent use the small model on the hackathon gateway (a chat-completions endpoint, `LITELLM_BASE_URL` and `LITELLM_API_KEY` in `.env`, $20 budget). Three parallel calls on 10 October each returned in about 1.4 seconds with no throttling. The owner's own API key is the fallback and should be a one-setting switch.
- Most development runs should use `neatroots mock-llm` or a scripted fake LLM and cost nothing.
- Never change model or provider inside one case. The bisect compares failure rates across commits, and a model change would look like a regression.
- The brief and the patch are asked of a model through `whodunit/llm.py`. `WHODUNIT_LLM` picks where: the gateway by default, the owner's own key, a coding agent in headless mode, or none, which falls back to a fixed template. The repo must work with a plain API key so other people can run it. Keep `ANTHROPIC_API_KEY` out of the shell that launches the coding agent, and load `.env` only inside the code that needs it.
- A replay is graded by the case's own check on what the agent printed, which uses no model. The bisect itself uses no model, and neither do the rule checks on a brief.
- The guideline of about 10 investigations before Sunday 4:30 PM was passed during the night. The count of model-written briefs and patches stood at 12 by 1 AM on Sunday.

## AWS

There is one shared $25 allowance and nothing meters it, so stop resources when they are idle. Use us-east-1 only, the pre-provisioned `Hackathon_VPC`, instance types t2, t3 or t3a from nano to large, and volumes of 50 GB or less. Only one EC2 instance may exist at a time, so terminate before replacing. Bedrock is not included. The plan is a single t3.large from Sunday evening as the replay worker and the host for the public case file page. Launching anything is the owner's call each time.

## Eval

A second session grows the victim's history and plants regressions through ordinary-sounding requests. It writes the answer key to a file, and the SHA-256 of that file is committed before Whodunit runs. Report cases solved, wrong accusations, replays used against a linear scan, and cost per case, and include at least one case Whodunit gets wrong. The stretch goal is one real regression in a public open-source agent with a comment or PR upstream, which needs the owner's yes.

## What the judges score

From the public hackathon page, read on 11 October. Each part is scored out of 100 and weighted.

- The agent: 30%. Evidence asked for: before and after runs with the numbers compared, and a run where an action failed along with what the agent did next.
- Use of neatlogs, Entire and cfo.ai: 25%. All three are required. For cfo.ai the page asks for a business plan covering pricing, costs, revenue and runway. For Entire it names checkpoints and entire-graph. neatroots is not mentioned on the page, so evidence should be shown in neatlogs cloud wherever it can be.
- Demo video: 20%, judged on how clearly it explains the agent and the tool use.
- Building in public: 15%, links tagged #neatHack.
- Usefulness and originality: 10%.

Entries are made by quoting the official neatlogs post with the team, name, project, public repo and demo. The window is Monday 12 October, 7:00 to 11:55 PM IST, the final cutoff is announced on Discord, and the organisers engage with the first 50 quote posts.

## Evidence to collect as we go

Before and after neatlogs traces with numbers, trace links or screenshots, an Entire checkpoint link and id, the cfo.ai plan, a run where an action failed along with what the agent did next, links to the #neatHack posts, and commits dated inside the window. `hackathon.md` at the repo root is the dated build log, and it gets a new entry whenever something is finished or found out.

## Milestones (IST), and what became of them

The plan was written before the build started. This is how it went, as of Sunday evening.

1. Saturday 10 PM: repo up, Entire on with the first checkpoint verified, neatlogs and neatroots receiving runs, the victim agent running, first #neatHack post. Done by 7:17 PM on Saturday, except the post: `evidence/` has no link to one. The repo was pushed on 12 October.
2. Sunday 3 AM: replay runner over worktrees, and plain bisect finding an always-failing planted bug across 20 commits. Done at 7:31 PM on Saturday.
3. Sunday 10 AM: the statistical bisect finding a bug that fails about 30% of the time, and the simulator chart. Done at 9:06 PM on Saturday.
4. Sunday 6 PM: motive, brief, ruling memory, fix and verify, case file page v1. Done on Saturday night, and reworked since.
5. Monday 2 AM: sealed-key eval on the grown victim, neatlogs cloud link, cfo.ai model through MCP, parallel replays on the AWS allowance. The eval is done. 232 traffic runs are in neatlogs cloud and `whodunit onset --cloud` reads the detection trend. The cfo.ai plan was built on 12 October. Nothing has been launched on AWS.
6. Monday noon: stretch target, README, evidence folder. The README and the evidence folder exist. The stretch target has not been started.
7. Monday 6 PM: demo video, which opens on "57 commits, which one did it?" and names the culprit inside 30 seconds. Submit at 7 PM. Not done.

## Where things stand, Monday 12 October, noon

Done and committed locally:

- Milestones 1 to 4, and the eval part of 5. `hackathon.md` has every step, including what went wrong.
- The victim has a real history: 55 commits made through `eval/ask.sh`, one fresh coding session per request. Five regressions were planted by a second session and sealed. `eval/sealed/README.md` has the result: 5 of 5 named, no wrong accusations, and 4 of 5 with a fix that cleared the bar.
- `whodunit investigate` runs a whole case. `cases/whole-history.toml` is the headline run and the one the video should show. It was run again from nothing on Monday morning: 98.3% after 20 replays, a first patch thrown out by the do-no-harm check, a second one kept.
- A review of the repo on Sunday afternoon listed claims the code or the records did not back, gaps in the method, and a rebuild of the case file. `hackathon.md` from 2:00 PM on Sunday works through it. All of the first part is done, six and a half of the seven gaps, and the case file.
- `pitch/` has the video script, post drafts and the business plan numbers, brought in line with Monday's run.
- `evidence/` has screenshots of the new pages, all on light paper.
- After noon on Monday the owner asked for the case file to be redone in an indie app design system. That is done, and "Case file design" below describes it. The records and every number on the pages are unchanged.

Left over from that review:

- The model that allows two change points is built and simulated, in `whodunit/lineup.py` and `eval/simulator/README.md`, and is not wired into the lineup. It needs alibi priors, skipped and voided replays, parallel rounds, resumed evidence and the clear-range check before it can replace the one there.
- `whodunit forward <case>` sends a case's failing and passing run to neatlogs cloud once the owner has run `neatroots cloud login`.
- A page links to a cloud trace once `NEATLOGS_TRACE_URL` gives the dashboard's address for one, and its link preview needs `WHODUNIT_SITE` for the casebook's public address.

Still to do, in this order:

1. cfo.ai. Done on 12 October: six pages, eight tables, four scenarios and a simulator, in the owner's workspace. `evidence/README.md` describes it. The owner had a read-only share link made, which is in `evidence/README.md`.
2. Screenshots from neatlogs cloud. Done on 12 October, three of them, in `evidence/`.
3. The push. Done on 12 October with the owner's yes: https://github.com/kinnuworks/whodunit, public, `main` and `entire/checkpoints/v1`. The owner mirrored the repo into Entire, so the checkpoint page for commit `ced2ecd21c3e`, checkpoint `bfbe27725663`, opens without an account. The casebook is published from `cases/` by `.github/workflows/pages.yml` at https://kinnuworks.github.io/whodunit/. Regenerate pages with `WHODUNIT_SITE=https://kinnuworks.github.io/whodunit uv run whodunit casebook`, or their link previews go back to a relative picture.
4. The video. A narrated motion film, 2 minutes 16 seconds, was made on 12 October and is described in `pitch/video/README.md`. The owner still has to watch it and upload it. `pitch/demo-script.md` is the earlier script for a screen recording with voice.
5. More #neatHack posts, from `pitch/posts.md`.

Rules that came out of the build:

- Two sessions in this folder at once end up in each other's checkpoints. Do unrelated work, such as research, from another folder.
- Do not edit `whodunit/` while a long `whodunit` run is in flight. Each case starts a new process that picks up the edit.
- neatroots returns at most 200 rows per query. Use `select_all` in `whodunit/neat.py`.
- A fix counts only when its failure rate is back within 5 points of the rate before the culprit. Do not loosen that. Report it as a count with its 95% upper bound, and do not call it proven: a fix that still fails 4 runs in 100 clears the same bar about one time in three.
- Damage is only the runs that fail the case's own check. A history can hold several regressions, and each case answers for its own.
- The ordinary traffic was sent by `eval/traffic.py`. Say so wherever a number comes from it.
- A brief is model-written and checked by rule for citations, ids, quotations and the measured rate. Nothing checks its arithmetic or its meaning, so read a brief before quoting it.
- A checkpoint can hold a thrown-away attempt at the same change, with a differently worded request. The motive has to come from the session that ran the commit. One sealed case quoted the wrong request for a day before `entire why` showed it.
- Gateway spend was about $14 of $20 at midday on Sunday, and about $16 by Monday noon by estimate. A full investigation costs 35 cents to a dollar with its do-no-harm check, and a rare bug can cost several dollars.
- Entire Brain is not installed. Its installer is a script piped from the network into a shell, which needs the owner's yes.

## Case file design

On 12 October the owner asked for the case file to be redone in a small design system made for indie apps, keeping the parts that fit Whodunit and dropping the rest. This replaces the typed paper file of 11 October.

`whodunit/casefile/foundation.css` is that system's stylesheet as it was given. Do not edit it. `whodunit/casefile/casefile.css` holds everything the page adds, and uses the foundation's tokens for every colour, radius and shadow.

- Mood cream, accent terracotta, set as `data-mood` and `data-accent` on the page. Paper `#FAF6EF`, card `#FFFEFC`, ink `#17150F`, muted ink `#6D6459`, hairline `#EBE3D7`. Terracotta `#D66B38` only fills small markers. Anything written in the accent uses its darker ink, `#A1411F`.
- Type from Google Fonts: Plus Jakarta Sans for everything read, Geist Mono for SHAs, counts and quoted evidence, and Instrument Serif italic for one word on the casebook.
- Light is the default. Dark is there only when someone picks it with the toggle, and every screenshot is taken in light.
- Taken from the system: the floating pill nav, a status badge, pill buttons, cards with a hairline ring, a soft stage under the lineup, and on the casebook a terminal window holding what `whodunit investigate` printed for the headline case.
- Left out, with the reason: the menu bar, popover and phone frames, because Whodunit is a command and a page. The blur on the nav, because glass is ruled out below. Icon tiles, the three-card grid, pricing, FAQ, social proof and scroll reveals, because the page is a case and has nothing to sell.
- The lineup keeps its own drawing: typed x and o marks, struck-through SHAs, hatching for an alibi and a pencil ring round the culprit.
- A case page's headline is the question the case asks, "57 commits since it last worked. Which one did it?", with what was reported under it. Every number on either page comes from a case record.
- Sample copy: "Suspects: 41. Cleared: 40." / "Motive: someone asked for friendlier replies." / "Alibi: never touched the agent." / empty state "No cases yet. Lucky you." / button "Open a case".

It should feel like a well-made object. That rules out pure white backgrounds, purple or blue gradients, glass effects, Inter as the only typeface, the three-card feature grid, sparkle icons, icons in rounded squares, fake KPI dashboards, stock hero sections and decorative emoji.

## Writing rules

These cover UI copy, the README, the pitch, scripts, commit messages and code comments.

- The voice is a kind, witty human. No "Supercharge", "Unlock", "Seamlessly" or "AI-powered".
- No em or en dashes, no "not X but Y" constructions, no one-line closers, no forced groups of three, no bold-label lists. Headings use sentence case.
- Repo text says "the coding agent" and names no assistant or vendor.
- Be specific: names, numbers, real copy.

## Working rules

- Commits carry no co-author trailer.
- These need the owner's yes each time: the first push to GitHub, any post on X, a PR or comment on someone else's repo, any write to cfo.ai, and launching anything on AWS.
- The repo went public on 12 October, with the owner's yes. Every session here is published with it.
- The owner does browser signups and enters any card or password personally.
- Report failures as plainly as successes. The eval is only worth something if the misses are in it.

<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->

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

1. Read neatlogs and neatroots to get the failing runs and the time the failures began.
2. List the suspect commits between the last good ref and the first bad one.
3. Replay the failing inputs against suspect commits in git worktrees. Agent failures are random, so repeat until the result is statistically confident.
4. Name the culprit and pull the Entire checkpoint behind it, which holds the original request and the session.
5. Ask the owner one question (revert, or keep the intent and patch) and remember the ruling.
6. Fix, replay to prove the fix, add the case as a permanent regression test, and open a PR or an Entire Trail.
7. Write the damage (bad runs and dollars) to cfo.ai.

Any description of the project opens with "which commit, and why". The fix comes after that.

## Layout

Python 3.12 through uv, in one repo.

- `whodunit/case.py`: a case is a symptom, the failing inputs, a good ref, a bad ref and a check.
- `whodunit/suspects.py`: the commits in `good..bad` with their Entire checkpoint ids. Commits that cannot reach the agent's code get a lower prior (path filter first, then entire-graph impact).
- `whodunit/replay.py`: one git worktree per commit under test. It runs the target's replay command with the case input, tags the run with the commit SHA and case id, and reads the verdict from neatroots findings or a local check. A commit that will not build is skipped, like `git bisect skip`.
- `whodunit/lineup.py`: the statistical bisect, described below.
- `whodunit/motive.py`: `entire checkpoint explain` and `entire why` for the culprit, which give the original request and the session.
- `whodunit/brief.py`: the model writes the root-cause brief from the culprit diff, the relevant slice of the session transcript and a diff of a failing run against a passing one. Every sentence cites a span id, a commit or a checkpoint.
- `whodunit/ruling.py`: the ask-once memory (revert or patch, per kind of change), stored as files in the repo and mirrored to Entire Brain.
- `whodunit/fix.py`: applies the fix on a branch, replays the case until the posterior says it is fixed, adds the case to `cases/` as a regression test, and opens the PR or Trail.
- `whodunit/damages.py`: counts bad runs and cost from traces and writes them to cfo.ai.
- `whodunit/casefile/`: the static HTML case file, which is the main demo surface, and the CLI command `whodunit open-case`.
- `whodunit/onset.py`: reads the agent's ordinary runs from neatroots and brackets the failure between a good and a bad ref with the same change-point model. `--cloud` asks neatlogs when a detection began firing.
- `whodunit/neat.py`, `whodunit/llm.py`, `whodunit/env.py`: the MCP client for neatroots and neatlogs, the one place a model is asked for text, and the `.env` loader.
- `whodunit/simulate.py` and `whodunit/chart.py`: the simulator and its SVG charts. Results live in `eval/simulator/`.
- `whodunit/cli.py`: the commands. Each step reads and writes one case record, `<case>.record.json`, next to the case file.
- `eval/`: `score.py` scores cases against a sealed answer key, `traffic.py` sends everyday requests through a history, and `SECOND-SESSION.md` briefs the session that grows the victim.
- `tests/planted.py`: throwaway histories with a known culprit (an overpayment, a lookup that fails one run in three, a prompt change that needs a real model).
- `victims/refund-agent/`: the demo target. It starts from the refund agent in neatroots' `examples/` (Apache-2.0, and the README must say so) and grows to 40 or more commits through real coding-agent requests in a separate session, so the history and its checkpoints are genuine.

### The statistical bisect

Model a single change point c. The failure rate is p_good before c and p_bad from c onward. Estimate both rates by running the two endpoints several times and keeping Beta posteriors. Hold a posterior over c. Each round, replay the commit with the highest expected information gain and update with the Bernoulli outcome. The even split is kept as an option and does about as well. The prior on the good rate is about 5%, loosely held, which matters far more than the choice of picker. Stop at 95% on one commit or when the replay budget runs out, and in the second case report the remaining suspects with their probabilities.

Unit-test it against a simulator. Publish the curve of accuracy against replay budget, next to plain bisect, at failure rates from 100% down to 20%.

## Tool facts checked on 10 October 2026

### neatroots

Version 0.2.6 is installed at `~/.local/bin/neatroots` and serves on port 4100. It is a local collector with checks and replay, and its MCP endpoint is `http://localhost:4100/mcp`.

- Whole-agent replay: `neatroots rerun add <project> "<command>" --cwd <dir>`, then `neatroots replay <trace-id> [--input ...]`. The agent receives `NEATROOTS_REPLAY_INPUT`, `NEATROOTS_REPLAY_ID` and `NEATLOGS_ENDPOINT`.
- Checks are YAML files in `.neatroots/checks/`. The `rule` kinds (repeat, errors, count, threshold, match, run_end) need no model. `yes_no` questions return a probability and need neatroots' local model. On the evening of 10 October that model was found switched on (`qwen2.5:3b-16k` through Ollama on port 11434), and the built-in `ignored-tool-error` check now runs it on incoming runs. A burst of replays therefore queues model work on this machine, so keep replays to two or three at a time while it is on.
- `neatroots mock-llm` is a key-free stand-in LLM on port 4110.
- `neatroots status` reports "cloud no key", so importing cloud traces needs the project key configured first.
- MCP tools used here: `search_runs`, `get_run_outline`, `list_findings`, `compare_runs`, `rerun`, `replay`, `query_sql`, `import_cloud_trace`.

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

- Replays of the refund agent use the small Haiku model on the hackathon gateway (OpenAI-compatible, `LITELLM_BASE_URL` and `LITELLM_API_KEY` in `.env`, $20 budget). Three parallel calls on 10 October each returned in about 1.4 seconds with no throttling. The owner's own API key is the fallback and should be a one-setting switch.
- Most development runs should use `neatroots mock-llm` or a scripted fake LLM and cost nothing.
- Never change model or provider inside one case. The bisect compares failure rates across commits, and a model change would look like a regression.
- Investigation and fix run through the coding agent in headless mode. The repo must also work with a plain API key so other people can run it. Keep `ANTHROPIC_API_KEY` out of the shell that launches the coding agent, and load `.env` only inside the replay code.
- Grading starts with neatroots rule checks, which use no model. The bisect itself uses no model.
- Keep investigations to about 10 before Sunday 11 October, 4:30 PM IST, and run the full eval after that.

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

## Milestones (IST)

1. Saturday 10 PM: repo up, Entire on with the first checkpoint verified, neatlogs and neatroots receiving runs, the victim agent running, first #neatHack post.
2. Sunday 3 AM: replay runner over worktrees. Plain bisect finds an always-failing planted bug across 20 commits.
3. Sunday 10 AM: the statistical bisect finds a bug that fails about 30% of the time, and the simulator chart is done. This milestone matters most.
4. Sunday 6 PM: motive, brief, ruling memory, fix and verify, case file page v1.
5. Monday 2 AM: sealed-key eval on the grown victim, neatlogs cloud link (the detection trend dates the onset), cfo.ai model through MCP, parallel replays on the AWS allowance.
6. Monday noon: stretch target, README, evidence folder.
7. Monday 6 PM: demo video, which opens on "57 commits, which one did it?" and names the culprit inside 30 seconds. Submit at 7 PM.

If milestone 3 slips past Sunday 2 PM, drop the stretch target and the AWS runner and keep everything else.

## Where things stand, Sunday 11 October, midday

Read this before the milestones above, which were written before the build started.

Done and committed locally:

- Milestones 1 to 4, and the eval part of 5. `hackathon.md` has every step, including what went wrong.
- The victim has a real history: 55 commits made through `eval/ask.sh`, one fresh coding session per request. Five regressions were planted by a second session and sealed. `eval/sealed/README.md` has the result: 5 of 5 named, no wrong accusations, 4 of 5 fixed and proven.
- `whodunit investigate` runs a whole case. `cases/whole-history.toml` is the headline run and the one the video should show.
- `pitch/` has the video script, post drafts and the business plan numbers.

Still to do, in order of points:

1. cfo.ai. Required, and nothing is in it yet. `.mcp.json` names the server. A new session in this folder should offer it, and the owner signs in. Build the plan from `pitch/business-plan.md`: pricing, costs, revenue and runway, with the three scenarios. Each write needs the owner's yes.
2. Screenshots from neatlogs cloud. 232 traffic runs are there and the `Execution Failed` detection has fired 27 times. The owner is signed in to the dashboard and this session is not.
3. The push. The owner still has to read the list of personal items in the transcripts: home folder path, connector names, the titles of the private notes index, and `ownerAccountUuid` and `ownerOrganizationUuid` in `bridge-session` entries. After the push, turn on GitHub Pages for `cases/` so the casebook has a public address, and collect the Entire checkpoint link for commit `ced2ecd21c3e`, checkpoint `bfbe27725663`.
4. The video, from `pitch/demo-script.md`.
5. More #neatHack posts, from `pitch/posts.md`.

Rules that came out of the build:

- Two sessions in this folder at once end up in each other's checkpoints. Do unrelated work, such as research, from another folder.
- Do not edit `whodunit/` while a long `whodunit` run is in flight. Each case starts a new process that picks up the edit.
- neatroots returns at most 200 rows per query. Use `select_all` in `whodunit/neat.py`.
- A fix is proven only when its failure rate is back within 5 points of the rate before the culprit. Do not loosen that.
- Gateway spend was about $14 of $20 at midday on Sunday. A full investigation costs 20 cents to a dollar, and a rare bug can cost several dollars.
- Entire Brain is not installed. Its installer is a script piped from the network into a shell, which needs the owner's yes.

## Case file design

This direction is a proposal and the owner has not signed it off yet.

The metaphor is a detective's typed case file with a two-colour typewriter ribbon.

- Light: paper `#F3EDDF`, surface `#E9E0CC`, ink `#201B15`, muted ink `#6B6156`, rule `#D8CDB6`, and one accent, ribbon red `#B4261F`.
- Dark: background `#1B1714`, surface `#26201A`, ink `#EDE4D3`, accent `#E5604F`.
- Type from Google Fonts: Young Serif for titles, Alegreya Sans for interface text, Courier Prime for typed evidence.
- Scale 13, 15, 17, 21, 27, 34, 44, 58 px. Line heights 1.1 for display, 1.2 for headings, 1.55 for body, 1.45 for Courier.
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
- The repo stays private until just before submission (the owner's ruling on 10 October). Sessions are still written as if public, because the checkpoints go up with it.
- The owner does browser signups and enters any card or password personally.
- Report failures as plainly as successes. The eval is only worth something if the misses are in it.

<!-- entire-graph:begin -->
This repo has the entire-graph code graph installed. Before exploring code with
grep/find/whole-file reads, read .entire/graph-agent.md — resolution-first guidance
for using graph retrieval, focused source inspection, and verification.
@.entire/graph-agent.md
<!-- entire-graph:end -->

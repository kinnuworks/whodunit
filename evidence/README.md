# Evidence

What has been collected so far, with ids that can be looked up. Every screenshot was taken on light paper on Monday 12 October 2026, from the pages `uv run whodunit casebook` writes.

## Traces

- neatlogs cloud trace `61e879c364435c4104745d26d0546c59`: the refund agent on the gateway's small model refunding order 1002 for 18.50. 6 spans, 2,792 tokens. Found again through `search_traces` over MCP.
- neatroots run `ffbdcba417f8d972ea97531b6dc53bd2`: the first full run with the scripted model. 3 model calls, 2 tool calls.
- neatroots run `5b20f1eb00bd75e9a6e8624c5e05d38f`: a whole-agent replay started by `neatroots replay`, with a new input.
- Case `planted-flaky-lookup`: failing run `d7b0d700a484` at the culprit and passing run `6987e974e28a` at its parent, same input. Both outlines are in `planted-flaky-lookup.record.json`.
- neatroots raised 4 findings by itself on the flaky lookup failures, check `ignored-tool-error`, probability 0.82 to 0.89.

- neatlogs cloud trace `b842b67dfae39c67c1a3aa76772f5229`, workflow `whodunit`: the headline investigation itself, run on 12 October. One root span, a span for the lineup with one child per round, and spans for the motive, the brief, the ruling, both fix attempts with their replays and do-no-harm checks, and the damages.
- neatlogs cloud trace `1c87143bc68b3c01ed9767dca855b8e4`: a probe of the same tracing on a planted ten-commit case with no model. It can be deleted.
- The failing run and the passing run each brief cites are in neatlogs cloud as of the evening of 12 October, twelve runs for the six cases, sent by `whodunit forward` after the owner ran `neatroots cloud login`. Each record lists its two ids under `evidence.cloud`, and each case page prints them. For the headline case they are `1d39ba32bd8f62e32931d2699af63589` (failing, on the culprit) and `113f05166f1f303b3a5a09a97a5a5594` (passing, on its parent). Three of the twelve were asked for again through the cloud's own MCP server and came back with their spans. The pages print the ids without links until `NEATLOGS_TRACE_URL` gives the dashboard's address for a trace.

## Entire checkpoints

- `fc9699a4e609` on commit 601c1fc, the first checkpoint in this repo.
- `f8f2b3618deb` on commit d210212, the refund agent. Entire shows no prompt for this one, and `whodunit motive d210212` recovers it from the session by commit time.

- `bfbe27725663` on commit `ced2ecd21c3e`, the headline culprit. `entire why` puts all 4 of its changed lines behind this commit, this checkpoint and the request the page quotes.
- `d248e108a420` on commit `d4fb1587c066` holds two sessions with two differently worded requests. The case file first quoted the one whose change was thrown away. The build log entry of 11 October, 6:24 PM, has how `entire why` showed it.

The repo was pushed on 12 October and is public at https://github.com/kinnuworks/whodunit. The culprit commit, with its `Entire-Checkpoint: bfbe27725663` trailer, is at https://github.com/kinnuworks/whodunit/commit/ced2ecd21c3ed165a1a729e17f68d2000cdc19ca, and the checkpoints themselves are on the `entire/checkpoints/v1` branch. The Entire page for it is https://entire.io/gh/kinnuworks/whodunit/commit/ced2ecd21c3ed165a1a729e17f68d2000cdc19ca and opens without an account. `entire-checkpoint.jpg` is that page: the commit, checkpoint `bfbe27725663`, and the request that was typed. Each case page now links its culprit to its own Entire page.

## Before and after

- `casefile-whole-history.png`: the headline case, whole page. 57 suspects, the culprit named at 98.3% after 20 replays across 5 commits, the request quoted from checkpoint `bfbe27725663` and checked against the transcript. Before the fix, 11 of 14 runs from the culprit on went wrong, which is 7 of 8 replays and 4 of 6 ordinary runs. After the kept fix, 0 failures in 30 replays, at most 6.2% at 95%. Failing run `1d39ba32bd8f`, passing run `113f05166f1f`.
- `lineup-whole-history.png`: the top of that page. The status badge, the facts card and the lineup, with the culprit ringed.
- `motive-whole-history.png`: its Motive section, with the request quoted from the Entire checkpoint.
- `fix-whole-history.png`: its Fix section, with both tries.
- `casefile-whole-history-phone.png`: the same page at 375 px wide. Only the lineup scrolls sideways.
- `casefile-turned-away.png`: a case closed by a revert after two patches fell short.
- `casefile-half-done-batch.png`: the case that is open and not fixed, with its badge left hollow.
- The casebook is live at https://kinnuworks.github.io/whodunit/, and the headline case at https://kinnuworks.github.io/whodunit/whole-history.casefile.html.
- `casebook.png`: the casebook. Up top is what `whodunit investigate` printed for the headline case, made from its record, and under it the docket of all six cases. The page is `../cases/index.html`.
- `planted-flaky-lookup.record.json` and `planted-friendly-prompt.record.json`: the records of the first two full cases, from 10 October, with machine paths replaced by placeholders. Their fixes were accepted on 8 and 6 clean replays under the first, lenient standard, which would not clear today's bar. The screenshots of their old pages are gone, and they are not drawn with the new page, because it would stamp them closed.

## A fix that failed, and what the agent did next

- `../cases/whole-history.record.json`, under `attempts`: the first patch went 30 replays without a failure on its own case. The do-no-harm check then replayed 13 other requests on it, and "Please refund order 1001 for customer cust_9." went wrong in 8 of 8 replays, against 5 of 8 before the patch. That is worse at the 95% level, though only just: the chance that it is no worse comes to 4.4%. Whodunit threw the patch out, wrote a second with the first and its damage in view, and kept that one: 0 failures in 30 replays and none of the 13 made worse.
- `../cases/turned-away.record.json`, under `attempts`: the first patch failed 5 of 12 replays, the second failed 4 of 18, and Whodunit then reverted the culprit and replayed the revert 30 times without a failure.
- `../cases/half-done-batch.record.json`: two patches that fell short of the bar and a revert that conflicts. Left open.
- The four fixes kept before the do-no-harm check existed were checked afterwards, against 12 or 13 other requests each. None made another request worse.

## Sealed eval

- `../eval/sealed/README.md`: five planted regressions on a history grown by a second session. 3 of 5 named inside 120 replays, 5 of 5 after more, no wrong accusations. The answer key's hash was committed in 4c45f7f before any case ran.

## Simulator

- `../eval/simulator/accuracy-clean-baseline.svg` and `accuracy-flaky-baseline.svg`: accuracy against replay budget, next to plain bisect, at failure rates from 100% down to 10%. `tables.md` gives wrong accusations as a share of accusations made, per cell.
- `../eval/simulator/README.md` also has four smaller runs: how often a fix that is not really fixed clears the bar, cases shaped like the sealed eval's two rare ones, ranges where no commit did it, and ranges with two culprits.

## A failure and what happened next

- The first flaky run on the real agent was thrown away. The machine was overloaded, replays hit the timeout and were counted as failures, and the timeout left agent processes running. The build log entry for 10 October has the detail. Since 11 October a timeout gets one more try with double the limit, and a provider error is voided.
- The first two root-cause briefs for `planted-flaky-lookup` named the right commit and misread why it fails. The third is right. All three are described in the build log.
- A review on 11 October found claims the code did not back. The build log from 2:00 PM that day goes through each one.

## The cfo.ai plan

Built on 12 October through the cfo.ai MCP server, in the owner's workspace, with the owner's yes. It has six pages (Whodunit plan, Assumptions, Customers and revenue, Costs and margin, Cash and runway, Simulator), eight tables, four scenarios (Base, Downside, Downside with no founder draw, Upside) and three live blocks. `../pitch/business-plan.md` has the inputs and the runway table.

- `cfo-cash-by-case.jpg`: cash by month in the base, downside and upside cases, as cfo.ai renders it.
- `cfo-simulator.jpg`: the simulator, with sliders for the Team price, usage, the cost of an investigation and the founder draw. With the sliders where the plan has them it gives the plan's own $23,141 after month 12.
- The cost of an investigation is not typed in. The model takes the mean of the six measured replay costs in its first table and adds the brief and patch.
- The four cases were worked out by hand in a script before anything was written, and the saved model matches each one to the cent: $23,141, minus $5,300, $12,700 and $70,178 after month 12.

The owner asked for a read-only link to the six pages on 12 October: https://app.cfo.ai/s/aQEB_E_N_TMjakaV

The plan is read by the code now. `../pitch/plan.json` holds the Team price, the investigations it includes, the cost of an investigation and the worker's cost, read from the model's tables on 12 October with the owner's yes, and `../whodunit/plan.py` derives the $1.37 that `whodunit investigate` takes as its default spend limit. The README has the formula and which of the six cases it would have stopped.

## neatlogs cloud

Taken from the dashboard on 12 October, in the owner's browser, with the sidebar that shows the owner's name cut off.

- `neatlogs-traces.jpg`: the traces list, 240 in the last 14 days. The top row is the investigation itself. Below it are the refund agent's scripted runs, two of them flagged by the `Execution Failed` detection.
- `neatlogs-investigation-trace.jpg`: trace `b842b67dfae39c67c1a3aa76772f5229`, workflow `whodunit investigate`, 17 steps in 10 minutes 45 seconds. The four lineup rounds, motive, brief, ruling, both fix attempts with their do-no-harm checks, and damages are each a span.
- `neatlogs-failing-run.jpg`: one scripted refund request where `lookup_order` errored four times and the detection flagged each. The model's name is on screen in this one.

## A standing check from the headline case

The headline bug, as something to watch for: `issue_refund` called in a run where no `lookup_order` came before it.

- `uv run python ../eval/standing_check.py` counts it exactly from the runs in neatroots, with no model. On 12 October, over 2,724 finished refund-agent runs: 113 of the 765 runs on commits from the culprit on that do not carry the kept fix, 1 of the 1,699 on commits before the culprit, and 0 of the 56 on the kept fix, commit `7e8120e`. Another 204 runs carry commits from the planted throwaway repos, and none of those is flagged. These are every recorded run, replays and scripted traffic together.
- `../.neatroots/checks/refund-without-lookup.yaml` is the same thing as a neatroots check, id `refund-without-lookup`. neatroots' rules cannot say "this tool with none of that tool before it", so it is a yes or no question for the small local model. Previewed on the latest 200 refund-agent runs it flagged 22. The exact count for the latest 200 is 12. Of the ten flagged runs the preview listed, five had refunded with no lookup and five had looked the order up first. A first wording, with a narrower choice of evidence, flagged none.
- It is a neatroots check and not a detection in neatlogs cloud. No tool here creates a cloud detection, so `whodunit onset --cloud` has not been pointed at it.

## Posts tagged #neatHack

- Day 1, 10 October: https://x.com/heykinnu/status/2108892698963071343
- Bingo, 11 October: https://x.com/heykinnu/status/2109010623833297271
- The pitch, 12 October: https://x.com/heykinnu/status/2109552985152119291
- The submission, 12 October, 8:56 PM IST, with the demo film attached: https://x.com/heykinnu/status/2109666939660648948

# Evidence

What has been collected so far, with ids that can be looked up. Times are IST on 10 October 2026.

## Traces

- neatlogs cloud trace `61e879c364435c4104745d26d0546c59`: the refund agent on the gateway's small model refunding order 1002 for 18.50. 6 spans, 2,792 tokens. Found again through `search_traces` over MCP.
- neatroots run `ffbdcba417f8d972ea97531b6dc53bd2`: the first full run with the scripted model. 3 model calls, 2 tool calls.
- neatroots run `5b20f1eb00bd75e9a6e8624c5e05d38f`: a whole-agent replay started by `neatroots replay`, with a new input.
- Case `planted-flaky-lookup`: failing run `d7b0d700a484` at the culprit and passing run `6987e974e28a` at its parent, same input. Both outlines are in `planted-flaky-lookup.record.json`.
- neatroots raised 4 findings by itself on the flaky lookup failures, check `ignored-tool-error`, probability 0.82 to 0.89.

## Entire checkpoints

- `fc9699a4e609` on commit 601c1fc, the first checkpoint in this repo.
- `f8f2b3618deb` on commit d210212, the refund agent. Entire shows no prompt for this one, and `whodunit motive d210212` recovers it from the session by commit time.

The checkpoint links will take the form `https://entire.io/gh/OWNER/REPO/commit/FULL_SHA` once the repo has a remote. It has none yet, by the owner's ruling.

## Before and after

- `casefile-v1-planted-flaky-lookup.png`: the case file page for the first full case. Before the fix, replays failed about 39% of the time from the culprit on (48 replays across 11 commits). After the revert, 0 failures in 8 replays, 95.8% likely fixed.
- `planted-flaky-lookup.record.json`: the record that page is drawn from. Machine paths are replaced with placeholders.

## Simulator

- `../eval/simulator/accuracy-clean-baseline.svg` and `accuracy-flaky-baseline.svg`: accuracy against replay budget, next to plain bisect, at failure rates from 100% down to 20%.

## A failure and what happened next

- The first flaky run on the real agent was thrown away. The machine was overloaded, replays hit the timeout and were counted as failures, and the timeout left agent processes running. The build log entry for 10 October has the detail, and `run_command` in `whodunit/replay.py` is the fix.
- The first two root-cause briefs for `planted-flaky-lookup` named the right commit and misread why it fails. The third is right. All three are described in the build log.

## Not collected yet

- Links to the #neatHack posts.
- The cfo.ai plan.
- A case on the genuine history, with a motive from a real request.

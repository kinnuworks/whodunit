# Sealed eval, 11 October 2026

Five regressions were planted in the refund agent's history by a second coding session, through ordinary requests to fresh coding sessions. It wrote the answer key, and the key's SHA-256 was committed in 4c45f7f before Whodunit ran on any case. `eval/score.py` checks the key against that hash before scoring. The key was added to git only after every case had been run.

Replays ran on the hackathon gateway's small model, three at a time.

## Result

With 120 replays allowed per case: 3 of 5 solved, 0 wrong accusations, 2 cases where nobody was named.

The two open cases were then resumed from their own replays with up to 200 more allowed: 5 of 5 solved, 0 wrong accusations.

| Case | Rate the second session measured | Rate Whodunit estimated | At 120 replays | In the end | Replays | Commits replayed | Suspects |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: |
| cents-off | 100% | 93% | solved | solved | 21 | 5 | 13 |
| wrong-order-refunded | 30% | 12% | nobody named | solved | 168 | 9 | 12 |
| half-done-batch | 25% | 14% | nobody named | solved | 168 | 10 | 15 |
| strangers-paid | 72% | 59% | solved | solved | 30 | 5 | 11 |
| turned-away | 100% | 93% | solved | solved | 24 | 6 | 14 |

The rate Whodunit estimates is a posterior mean, so after only a few replays it sits below 100% even for a bug that fails every time.

## What it cost

Replay spend on the gateway, estimated from token counts at list prices, came to about $1.91 for all five cases:

- cents-off: about $0.08 (61,267 tokens)
- wrong-order-refunded: about $0.57 (438,034 tokens)
- half-done-batch: about $1.04 (795,110 tokens)
- strangers-paid: about $0.10 (78,530 tokens)
- turned-away: about $0.12 (100,111 tokens)

## What this does and does not show

- No commit was wrongly accused, at either budget. Five cases cannot show how often that would hold. The simulator puts a number on it for cases shaped like the two rare ones: with 320 replays allowed, about 4% of accusations name the wrong commit, and with 120 about 13%. See `eval/simulator/README.md`. On `half-done-batch` the top suspect at 120 replays was the wrong commit, at 53%, and Whodunit named nobody. That is the behaviour the 95% bar is for.
- The two cases it could not close at 120 replays are the two that fail least often. Whodunit put them at 12% and 14%, where the second session had measured 30% and 25% from a handful of probes. A bug that rare needs a lot of replays whatever the method.
- The ranges are short, 11 to 15 suspects. On ranges this size a careful scan from the oldest commit would have replayed about as many commits as Whodunit did, so this eval says little about savings on long histories. The simulator in `eval/simulator` covers 40 suspects.
- Five cases is a small sample. It is enough to say the pipeline works on a history it did not write, and not enough to put a number on accuracy.
- Each case has one planted regression inside its range, by design. Two regressions that touch the same inputs in one range are outside what the model assumes.

## What happened after the culprits were named

The owner's ruling was patch for all three kinds of change involved. A fix is kept when its failure rate is 95% likely to be back within 5 points of the rate before the culprit. The last column gives what the replays of the kept fix showed and the 95% upper bound on its failure rate. Clearing the bar is not proof: in simulation a fix that still fails 4 runs in 100 clears it about one time in three.

| Case | Outcome | Tries | Replays of the final fix, and the most it could still fail at 95% |
| --- | --- | ---: | --- |
| cents-off | patch kept | 1 | 0 failures in 30, at most 6.2% |
| strangers-paid | patch kept | 1 | 0 failures in 30, at most 6.2% |
| wrong-order-refunded | patch kept | 1 | 0 failures in 36, at most 5.2% |
| turned-away | two patches fell short, then a revert was kept | 3 | 0 failures in 30, at most 6.2% |
| half-done-batch | not fixed | 3 | two patches left 5 failures in 90 each, at most 10.6%, and the revert conflicts |

So four of five were closed, one of them only by giving up on the patch the owner asked for, and one was left open and says so.

## The same culprit across the whole history

`cases/whole-history.toml` takes the `strangers-paid` regression and widens the range to the whole grown history, 57 suspects. With alibis from entire-graph for 22 of them and 18 ordinary runs as evidence, 20 replays across 5 commits named the culprit at 99.8%. A scan from the oldest suspect would have tested 37 commits. This is the run that speaks to savings on a longer history, and it is one run.

## Against plain bisect with retries

The same five cases were then given to plain bisect, with each commit replayed up to 5 times over and called bad on the first failure. It ran once per case, so this is one sample and not a rate.

| Case | Plain bisect, 5 retries | Its replays | Statistical bisect | Its replays |
| --- | --- | ---: | --- | ---: |
| cents-off | right | 15 | right | 21 |
| strangers-paid | right | 15 | right | 30 |
| turned-away | right | 25 | right | 24 |
| wrong-order-refunded | wrong commit named | 19 | right | 168 |
| half-done-batch | could not start: the bad ref passed 10 replays in a row | 10 | right | 168 |

On the three bugs that fail most of the time, plain bisect was right and used 55 replays in all against 75. That matches the simulator: with a clean baseline, and this one was clean (0 failures in 211 replays of commits before a culprit), plain bisect with retries is the cheaper tool.

On the two bugs that fail about one run in eight, it went wrong in the two ways it can. For `wrong-order-refunded` a bad commit passed all 5 tries, the search went the wrong way, and it named an innocent commit three places from the real one, with nothing to say it was unsure. For `half-done-batch` the bad ref itself passed 10 replays in a row, so there was nothing to bisect.

More retries would have fixed both, at a cost. The trouble is that the number has to be picked before the failure rate is known. The statistical bisect does not need it picked: it spent 21 to 30 replays on the frequent bugs and 168 on the rare ones, and on the rare ones it said "not sure yet" at 120 instead of naming someone.

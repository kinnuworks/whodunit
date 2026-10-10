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

- No commit was wrongly accused, at either budget. On `half-done-batch` the top suspect at 120 replays was the wrong commit, at 53%, and Whodunit named nobody. That is the behaviour the 95% bar is for.
- The two cases it could not close at 120 replays are the two that fail least often. Whodunit put them at 12% and 14%, where the second session had measured 30% and 25% from a handful of probes. A bug that rare needs a lot of replays whatever the method.
- The ranges are short, 11 to 15 suspects. On ranges this size a careful scan from the oldest commit would have replayed about as many commits as Whodunit did, so this eval says little about savings on long histories. The simulator in `eval/simulator` covers 40 suspects.
- Five cases is a small sample. It is enough to say the pipeline works on a history it did not write, and not enough to put a number on accuracy.
- Each case has one planted regression inside its range, by design. Two regressions that touch the same inputs in one range are outside what the model assumes.

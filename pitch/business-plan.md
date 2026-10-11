# Business plan inputs

These are the numbers and assumptions to build the cfo.ai model from. The measured ones come from this repo's runs on 10 and 11 October 2026. The assumed ones are marked and are the owner's to change.

## What is being sold

Whodunit Cloud: hosted investigations for teams that run an AI agent in production. The command line tool stays open source and free with your own keys. The paid product is the hosted replay workers, the case file pages, the regression checks in CI, and the standing rulings shared across a team.

## Unit costs, measured

Six full investigations on the refund agent, with replays on a small hosted model at list price:

| Case | Replays | Replay cost |
| --- | ---: | ---: |
| whole-history | 50 | $0.18 |
| cents-off | 65 | $0.25 |
| strangers-paid | 74 | $0.25 |
| turned-away | 119 | $0.71 |
| wrong-order-refunded | 240 | $0.85 |
| half-done-batch | 558 | $3.53 |

- Median replay cost per investigation: about $0.48. Mean: about $0.96. The worst case is a rare bug that was never fixed.
- Brief and patch calls on a larger model: about $0.10 to $0.30 per investigation.
- Replay worker: one t3.large at about $61 a month runs three replays at a time. Assumed: one worker per 15 paying teams.
- So the cost of one investigation is about $1.20 on average for an agent on a small model. An agent on a large model costs roughly 5 to 15 times more to replay, which is why replays are billed at cost above the included amount.

## What a regression costs the customer, measured

From ordinary traffic through the refund agent's history:

- One prompt change refunded 120.00 to the wrong people in 4 of 6 matching requests.
- One "friendlier replies" change withheld 360.00 across 6 customers who were owed it.
- These are from a few hundred simulated requests. A real shop would see them at its own volume until someone noticed.

## Pricing, assumed

| Plan | Price | Included |
| --- | ---: | --- |
| Open source | $0 | The CLI, your own keys, your own machine |
| Team | $249 a month per agent | 40 investigations, hosted replays on a small model, CI regression checks |
| Scale | $999 a month per agent | 250 investigations, private replay worker, single sign-on |
| Extra investigations | $8 each | |
| Replays on the customer's larger model | at cost plus 20% | |

Gross margin on Team at full use: 40 investigations at $1.20 is $48, plus about $4 of worker share, against $249. About 79%.

## Costs, assumed

| Item | Monthly |
| --- | ---: |
| Founder draw, months 1 to 6 | $0 |
| Founder draw, month 7 on | $3,000 |
| Replay workers and hosting | $150, plus $61 per 15 teams |
| Model spend for development and evals | $300 |
| Tools (tracing, checkpoints, finance) | $150 |
| Legal and accounting | $100 |

## Revenue scenarios, assumed

| | Downside | Base | Upside |
| --- | ---: | ---: | ---: |
| Design partners by month 3 (free) | 2 | 5 | 8 |
| Paying Team agents at month 6 | 2 | 8 | 15 |
| Paying Team agents at month 12 | 6 | 25 | 60 |
| Scale agents at month 12 | 0 | 3 | 8 |
| Monthly churn | 6% | 3% | 2% |
| Monthly revenue at month 12 | $1,494 | $9,222 | $22,932 |

## Runway, assumed

Starting cash of $15,000. In the base case the business is cash-positive on its running costs from about month 5, and the founder draw from month 7 is covered by month 9. In the downside case the cash lasts about 14 months with no draw, and about 9 months with one.

## Levers worth a simulator

- Investigations per agent per month. It drives both the value and the cost.
- The share of customers whose agents run on a large model.
- Replays per investigation, which falls when production traces are used as evidence. The whole-history case needed 20 replays where a comparable sealed case needed 30.
- Price per agent.

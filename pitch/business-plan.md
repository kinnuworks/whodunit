# Business plan inputs

These are the numbers and assumptions to build the cfo.ai model from. The measured ones come from this repo's runs on 10 and 11 October 2026. The assumed ones are marked and are the owner's to change.

One thing to keep in view when quoting any of it: no real customer has used the refund agent. Its ordinary traffic was sent by `eval/traffic.py`, a script that plays customers against each commit, and the shop and its orders are test data. The replay costs below are real spend on real model calls. The refund amounts are what a script's requests cost a test shop.

## What is being sold

Whodunit Cloud: hosted investigations for teams that run an AI agent in production. The command line tool stays open source and free with your own keys. The paid product is the hosted replay workers, the case file pages, the regression checks in CI, and the standing rulings shared across a team.

## Unit costs, measured

Six full investigations on the refund agent, with replays on a small hosted model at list price:

| Case | Replays | Replay cost |
| --- | ---: | ---: |
| cents-off | 89 | $0.34 |
| strangers-paid | 112 | $0.39 |
| whole-history | 176 | $0.80 |
| turned-away | 171 | $0.95 |
| wrong-order-refunded | 274 | $1.00 |
| half-done-batch | 558 | $3.53 |

- Median replay cost per investigation: about $0.87. Mean: about $1.17. The worst case is a rare bug that was never fixed. These are higher than the first version of this table, because every kept fix is now also replayed against 12 or 13 other requests, and the headline case needed a second patch.
- Brief and patch calls on a larger model: about $0.10 to $0.30 per investigation.
- Replay worker: one t3.large at about $61 a month runs three replays at a time. Assumed: one worker per 15 paying teams.
- So the cost of one investigation is about $1.37 on average for an agent on a small model. An agent on a large model costs roughly 5 to 15 times more to replay, which is why replays are billed at cost above the included amount.

## What a regression costs the customer, counted from scripted traffic

The requests were sent by `eval/traffic.py`, not by customers, so these show the size of the thing and are not a measurement of any real shop. Each line counts only the runs that failed that case's own check:

- One prompt change refunded 120.00 to the wrong people, in 4 of the 6 scripted requests that asked for it.
- One "friendlier replies" change withheld 360.00, across all 6 scripted requests that were owed a refund: three of 90.00 and three of 30.00.
- These come from a few hundred scripted requests spread over the history. A real shop would see them at its own volume until someone noticed.

## Pricing, assumed

| Plan | Price | Included |
| --- | ---: | --- |
| Open source | $0 | The CLI, your own keys, your own machine |
| Team | $249 a month per agent | 40 investigations, hosted replays on a small model, CI regression checks |
| Scale | $999 a month per agent | 250 investigations, private replay worker, single sign-on |
| Extra investigations | $8 each | |
| Replays on the customer's larger model | at cost plus 20% | |

Gross margin on Team at full use: 40 investigations at $1.37 is $55, plus about $4 of worker share, against $249. About 76%.

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

## Runway, as the cfo.ai model works it out

The model is in the owner's cfo.ai workspace: six pages, eight tables, four scenarios and a simulator. Month 1 is October 2026. Starting cash is $15,000 and nothing is raised. The first three months are free pilots. Paying Team agents then rise in a straight line to the month 6 target and on to the month 12 target, Scale agents start after month 6, and the founder draw starts in month 7.

What an agent costs to serve is worked out from use. At half use a Team agent runs 20 investigations a month and a Scale agent 125, at $1.37 each: the $1.17 mean of the six measured cases plus $0.20 for the brief and the patch. Fifteen Team agents share a $61 worker and each Scale agent has its own. An earlier version of this table charged every agent $26 a month, which was far too little for Scale.

| | Revenue covers costs from | Lowest cash | Cash at month 12 |
| --- | --- | ---: | ---: |
| Downside, no draw | month 9 | $11,311 | $12,700 |
| Downside, with the draw | never in the year | runs out in month 10 | minus $5,300 |
| Base, with the draw | month 5 | $12,730 | $23,141 |
| Upside, with the draw | month 4 | $12,900 | $70,178 |

In the base case the month the draw starts goes back into the red, by about $1,000, and the month after is positive again.

So the plan survives the downside only if the founder takes no draw, and that is the decision the model makes visible. Every figure in this table was worked out by hand in a script first, and the cfo.ai model gives the same numbers to the cent.

Left out of the model: replays billed at cost plus 20% for customers on a large model, and extra investigations at $8. Churn sets how many agents have to be signed each month to hit the targets. It does not lower the targets.

## Levers worth a simulator

- Investigations per agent per month. It drives both the value and the cost.
- The share of customers whose agents run on a large model.
- Replays per investigation, which falls when production traces are used as evidence. The whole-history case needed 20 replays where a comparable sealed case needed 30.
- Price per agent.

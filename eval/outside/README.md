# A history somebody else wrote, 12 October 2026

Everything else in this repo is measured on a refund agent whose history was grown here. This is one run on a repo that was not: [support-agent-demo](https://github.com/jaxsonsprinkles/support-agent-demo) by Jaxson Sprinkles, a customer-support agent built by another neatHack team as the target for their own tool, [AgentBisect](https://github.com/jaxsonsprinkles/agentbisect). The agent, its 30 commits, the coding sessions behind them, the eval cases and the seeded regressions are all theirs. None of its code or data is copied here. Each case file under `cases/outside/` holds one customer message and the checks from one of their eval cases, and names which.

## How it was kept blind

- The range was given: `1b40b27` (good) to `0ecffc0` (bad), 25 commits.
- Their answer key is published in the AgentBisect repo. That repo, the target's README and its history before the good ref were not opened until the predictions were committed and pushed.
- [predictions.json](predictions.json) went in with commit `d1bf1b0`, pushed at 5:19 PM IST. The key was cloned after that. The file has not been edited since.

## What Whodunit named

| Case | Their eval case | Named | Probability | Replays | Commits replayed | Replay spend |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| [refund-amount](../../cases/outside/refund-amount.toml) | rw1 | `b0be626` Take and return issue_refund amounts in integer cents to match Stripe | 97.9% | 22 | 7 of 25 | $0.16 |
| [escalation-skipped](../../cases/outside/escalation-skipped.toml) | es2, without its two argument checks | `b0be626`, the same commit | 97.9% | 22 | 7 of 25 | $0.19 |
| [out-of-window](../../cases/outside/out-of-window.toml) | ro1 | nobody: the range is clear | | 12 | 2 of 25 | $0.05 |

Both lineups that named a commit saw the same thing: 12 passes in 12 replays at the good ref and at commits 12, 13 and 14, and 10 failures in 10 at commits 15, 18 and 25. Commit 15 is `b0be626`. One attempt in the first lineup hit the gateway's rate limit, was voided and was run again.

The third case fails at both ends, 6 of 6 and 6 of 6, so the lineup named nobody and said no commit in the range did it.

The motive step worked on their repo, which I had not expected. Their checkpoint branch is published, so the request behind `b0be626` came out of its Entire checkpoint, was found word for word in the session transcript, and `entire why` put all 12 changed lines that were checked behind that commit and checkpoint. The request asked for refund amounts in cents "to match Stripe", with the change kept to the refund tool and its tests.

## What the key says

[ground_truth.json](https://github.com/jaxsonsprinkles/agentbisect/blob/main/evidence/ground_truth.json) maps each of their 24 eval cases to one of three seeded regressions, R1, R2 and R3, or to "control". It names no commits. Their notes beside it (`evidence/rerun-summary.md` and `evidence/rerun3-summary.md`) say what the three are: R3 is the refund amount in cents, at `b0be626`. R1 and R2 are changes that make every run use more tokens, one through a tool schema and one through a rule about `search_help`, and their notes point at `59c8b10` for R2 and name no commit for R1. They also say R1 and R2 "only show as budget failures", meaning a run is counted as broken when it uses more than one and a half times the tokens it used at the good ref.

Scored against that:

- refund-amount: right. The key puts rw1 under R3, and Whodunit named R3's commit.
- escalation-skipped: not backed by the key. The key puts es2 under R2, the token regression, and Whodunit named R3's commit. What the replays show is a different symptom from the one the key means. Before `b0be626` the agent sent an 800.00 refund request to a person every time, and from that commit on it issued the refund itself every time. That commit reworded the tool's own rule that refunds over $500 must be escalated. So this may be a side effect of R3 that the key does not list, or it may be something only the model on this gateway does. Nobody has reverted the commit to find out, and I am not counting it as a hit.
- out-of-window: agrees with the key. ro1 is a control, and Whodunit named nobody.
- R1 and R2: not found, and not looked for. Every request their key files under R1 or R2 still called the right tools and said the right things at the bad ref, twice each, except es1, which fails the same way at both ends. A check on tools and replies cannot see a run that is right and costs more. The token counts were there to see: their request ro1 used 2,904 input tokens at the good ref and 4,576 at the bad one. No case was opened on them, because the cases were to come from the repo's own checks.

So, plainly: of three seeded regressions, Whodunit named the commit behind one. It made two accusations, one confirmed by the key and one the key does not back. It called one range clear, correctly.

Their notes also record a behaviour at the tip commit, cancelling an unshipped order when the customer only asked where it was, which their tool caught. All five of their order-status requests passed 2 times in 2 here at the tip, so no case was opened for it.

## What it cost

All of it ran on the hackathon gateway's small model, three replays at a time for the first screening run and two after that, with token counts taken from what the agent prints and priced at $1 and $5 per million.

- Screening their 24 eval inputs at the bad ref twice, and the ones that failed at the good ref twice: 67 runs, 359,913 input tokens and 13,379 output tokens, about $0.43.
- The three lineups: 56 replays, about $0.41.
- About $0.83 in all, against a cap of $2.50 the owner set.

## What had to change in Whodunit

- A check that is not about refunds. `kind = "calls"` reads the JSON an agent prints and checks which tools it called, which it did not, the first call, counts, order, arguments, and what the reply says or matches. The case says where in the JSON the calls and the reply are. An expectation it does not know is refused, so a misspelt one cannot pass by being ignored.
- Reading a result that is pretty-printed over many lines. The refund agent prints one line.
- Handing an agent its key under the agent's own name. `[env_from]` in a case maps the agent's variable to the name of one in the runner's `.env`. Only names are written down.
- A longer wait after a provider error, set per case, because this gateway limits by the minute and the first screening run lost 15 attempts to that at three at a time.
- Token counts on each replay, when the agent reports them.
- A record keeps the address of the repo it was run on, so the page links the culprit's own Entire page.

No file in their repo was edited. The gateway was reached through environment variables alone.

## What did not carry over

- Alibis. The agent sits at the root of its repo, so the path filter excuses nobody, and entire-graph was not set up in the clone. All 25 commits started equal. A README-only commit was as suspect as the rest.
- Traces. The agent's own tracing was switched off for these replays so that its runs went to nobody's neatlogs project. So there is no failing run set against a passing one, and no brief.
- Damages. Those are still read from the refund agent's tool spans.
- The fix. It was not run, on purpose. Their repo is theirs to fix.
- The model. Their notes say they ran the agent on its pinned model through their own proxy. These replays used the gateway's small model, which may not be the same version. Their notes report one case failing at the good ref, es2. Here es2 fails there too, and so do ro1 and es1.

## What was not checked

- Whether the skipped escalation really starts at `b0be626` on their pinned model. That needs their setup, or a revert, and neither was done.
- Whether a token check would have found R1 and R2. It was not built.
- The lineups were run once each. At temperature 0 the agent is close to deterministic, which is why 22 replays were enough, and why these two cases say little about the statistical part of the bisect.

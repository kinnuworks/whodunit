# Drafts for #neatHack posts

Each stands alone. Attach the file named under it. Edit freely, these are drafts.

## 1, the question

git bisect assumes a bad commit fails every time. AI agents don't. A prompt change might break 1 run in 3.

So we built Whodunit: it replays the failing request against suspect commits, keeps a probability for each, and names one only at 95%.

57 commits. 20 replays. 99.8%. #neatHack

Attach: `evidence/casefile-whole-history.png`, cropped to the Suspects section.

## 2, the motive

The culprit was a commit called "Let the agent skip lookup_order when the customer gives order number and amount".

Who would ask for that? @EntireHQ checkpoints keep the session. Someone did: "simple refunds feel slow."

Reasonable request. It also removed the only ownership check. #neatHack

Attach: the Motive and Brief sections of the same page.

## 3, the honest chart

We simulated 500 cases per point to see when our statistical bisect beats plain bisect with retries.

When good commits never fail: plain bisect wins. We put that in the README.

When good commits fail 5% of the time on their own: plain bisect collapses to 4%. Ours reaches 84%. #neatHack

Attach: `eval/simulator/accuracy-flaky-baseline.svg` as an image.

## 4, the eval

We didn't want to grade our own homework.

A second coding session grew the agent by 53 commits, planted 5 regressions through ordinary requests like "make replies friendlier", and committed the SHA-256 of the answer key before we ran.

Result: 5 of 5 named, 0 wrong accusations, $1.91 of replays. #neatHack

Attach: the table from `eval/sealed/README.md`.

## 5, the failure

Our own fix check was too lenient. A patch passed 3 replays, we called it proven, and then it failed 2 of 8.

Now a fix has to bring the failure rate back to where it was before the culprit. About 30 clean replays.

One of our five cases still isn't fixed. The case file says so. #neatHack

Attach: the "What it took" part of `cases/turned-away.casefile.html`.

## 6, the damage

Reading damage from @neatlogs traces instead of guessing:

4 of 6 ordinary runs refunded someone else's order. 120.00 gone.
6 of 6 turned away a customer who was owed 60.00 each.

Finding the commit cost 18 cents. #neatHack

Attach: the Damages sections of two case files.

## 7, the head to head

We gave the same 5 sealed cases to plain bisect with 5 retries per commit.

3 right, and cheaper than us: 55 replays against our 75.
1 innocent commit named, with full confidence.
1 it couldn't start, because the broken version passed 10 times in a row.

Ours: 5 right, 0 wrong. On rare bugs it said "not sure yet" until it was. #neatHack

Attach: the last table in `eval/sealed/README.md`.

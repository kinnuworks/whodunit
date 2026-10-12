# Drafts for #neatHack posts

Each stands alone. Attach the file named under it. Edit freely, these are drafts.

## Short versions, each under 280 characters

These six fit a standard post. The longer drafts further down need an account that allows long posts. Tool names are written plainly here, so add the handles if you are sure of them.

### 1. The question

git bisect assumes a bad commit fails every time. AI agents don't. A prompt change can break 1 run in 3.

Whodunit replays the failing request on suspect commits and names one only at 95%.

57 commits since it last worked. 20 replays later: 98.3% on one of them. #neatHack

Attach: `evidence/lineup-whole-history.png`.

### 2. The motive

The culprit: "Let the agent skip lookup_order when the customer gives order number and amount".

Who asks for that? The Entire checkpoint kept the session. Someone had typed: "simple refunds feel slow".

A fair request. It also removed the only ownership check. #neatHack

Attach: `evidence/motive-whole-history.png`.

### 3. The patch that passed and was thrown out

Our fixer's first patch went 30 replays without one failure. A day earlier we would have kept it.

Then Whodunit replayed 13 other requests on the patched agent. An ordinary refund that failed 5 times in 8 now failed 8 in 8.

Patch thrown out. The second one was kept. #neatHack

Attach: `evidence/fix-whole-history.png`.

### 4. The sealed eval

We didn't want to mark our own homework. A second coding session planted 5 regressions through ordinary requests and committed the answer key's SHA-256 before we ran.

First pass: 3 of 5 named, nobody wrongly accused. With more replays: 5 of 5. One isn't fixed yet. #neatHack

Attach: `evidence/casebook.png`.

### 5. The honest chart

When does a statistical bisect beat git bisect with retries? We simulated 500 cases per point.

If good commits never fail, plain bisect is cheaper. Our README says so.

If they fail 5% of the time, on a 30% bug at 320 replays: plain is right 4% of the time, ours 86%. #neatHack

Attach: `eval/simulator/accuracy-flaky-baseline.png`.

### 6. Today

Today on Whodunit: the case file got a new coat. Cream paper, one terracotta accent, and the culprit still ringed in pencil.

Bug of the day: our screenshot script kept the old picture and reported success. We only caught it by opening the file. #neatHack

Attach: `evidence/casefile-whole-history-phone.png`.

## Longer drafts

### 1, the question

git bisect assumes a bad commit fails every time. AI agents don't. A prompt change might break 1 run in 3.

So we built Whodunit: it replays the failing request against suspect commits, keeps a probability for each, and names one only at 95%.

57 commits. 20 replays. 98.3%. #neatHack

Attach: `evidence/lineup-whole-history.png`.

### 2, the motive

The culprit was a commit called "Let the agent skip lookup_order when the customer gives order number and amount".

Who would ask for that? @EntireHQ checkpoints keep the session. Someone did: "simple refunds feel slow."

Reasonable request. It also removed the only ownership check. #neatHack

Attach: the Motive and Brief sections of the same page.

### 3, the honest chart

We simulated 500 cases per point to see when our statistical bisect beats plain bisect with retries.

When good commits never fail: plain bisect wins. We put that in the README.

When good commits fail 5% of the time on their own: plain bisect collapses to 4%. Ours reaches 86%. #neatHack

Attach: `eval/simulator/accuracy-flaky-baseline.svg` as an image.

### 4, the eval

We didn't want to grade our own homework.

A second coding session grew the agent by 53 commits, planted 5 regressions through ordinary requests like "make replies friendlier", and committed the SHA-256 of the answer key before we ran.

Result: 5 of 5 named, 0 wrong accusations, $1.91 of replays. #neatHack

Attach: the table from `eval/sealed/README.md`.

### 5, the failure

Our own fix check was too lenient. A patch passed 3 replays, we called it proven, and then it failed 2 of 8.

Now a fix has to bring the failure rate back to where it was before the culprit, and the page says what was seen: "0 failures in 30 replays. At most 6.2% at 95%."

One of our five cases still isn't fixed. The case file says so. #neatHack

Attach: the "What it took" part of `cases/turned-away.casefile.html`.

### 6, the damage

Reading damage from @neatlogs traces instead of guessing:

4 of 6 scripted customer requests got someone else's order refunded. 120.00 gone, in a test shop.
6 of 6 who were owed a refund got a kind reply and no money. 360.00 held back: three of 90.00 and three of 30.00.

The whole investigation cost about 80 cents. #neatHack

Attach: the Damages sections of two case files.

### 7, the head to head

We gave the same 5 sealed cases to plain bisect with 5 retries per commit.

3 right, and cheaper than us: 55 replays against our 75.
1 innocent commit named, with full confidence.
1 it couldn't start, because the broken version passed 10 times in a row.

Ours: 5 right, 0 wrong. On rare bugs it said "not sure yet" until it was. #neatHack

Attach: the last table in `eval/sealed/README.md`.

### 8, the patch that passed and was thrown out

Our fixer's first patch went 30 replays without a single failure. We almost shipped it.

Then Whodunit replayed 13 other requests on the patched agent. An ordinary refund went from failing 5 times in 8 to failing 8 in 8.

A fix is checked against its own bug. It should also be checked against everything else. #neatHack

Attach: the "What it took" part of `cases/whole-history.casefile.html`.

### 9, no commit did it

Sometimes git bisect has no right answer. A model changes behind an alias and every commit breaks at once, the last good one too.

Our lineup used to pin that on the first suspect, at 96.6%. Now it replays both ends first, says "No commit did it", and tells you what changed. #neatHack

Attach: `eval/simulator/README.md`, the table under "When no commit did it".

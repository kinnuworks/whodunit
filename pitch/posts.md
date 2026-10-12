# Drafts for #neatHack posts

Each stands alone. Attach the file named under it. Edit freely, these are drafts.

## Short versions, each under 280 characters

These six fit a standard post and are written the way the owner types. The longer drafts further down need an account that allows long posts. Tool names are written plainly here, so add the handles if you are sure of them.

### 1. The question

git bisect assumes a bad commit fails every time. agents don't, a prompt change can break 1 run in 3.

so i built whodunit. it replays the failing request on suspect commits and only names one once it's 95% sure.

57 commits, 20 replays, landed on one at 98.3% #neatHack

Attach: `evidence/lineup-whole-history.png`.

### 2. The motive

the commit that broke my refund agent: "Let the agent skip lookup_order when the customer gives order number and amount".

Entire kept the session so i could see why. someone typed "simple refunds feel slow".

fair enough, but that lookup was the only ownership check #neatHack

Attach: `evidence/motive-whole-history.png`.

### 3. The patch that passed and was thrown out

the first patch my fixer wrote went 30 replays with 0 failures. a day earlier i would've kept it.

then whodunit replayed 13 other requests on the patched agent, and a normal refund that used to fail 5 times in 8 was failing 8 in 8.

threw it out, kept the second patch #neatHack

Attach: `evidence/fix-whole-history.png`.

### 4. The sealed eval

didn't trust myself to grade this, so a second coding session planted 5 regressions through normal requests and committed the answer key's SHA-256 before i ran it.

first pass named 3 of 5, nobody wrongly accused. more replays got it to 5 of 5. one still isn't fixed #neatHack

Attach: `evidence/casebook.png`.

### 5. The honest chart

simulated 500 cases per point to see when my statistical bisect beats git bisect with retries.

if good commits never fail, plain bisect is cheaper. the README says so.

if they fail 5% of the time, on a 30% bug at 320 replays plain is right 4% of the time, mine 86% #neatHack

Attach: `eval/simulator/accuracy-flaky-baseline.png`.

### 6. Today

redid the whodunit case page today. cream paper, one terracotta accent, culprit still gets circled in pencil.

dumbest bug of the day: my screenshot script kept the old image and said it worked. only caught it because i opened the file #neatHack

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

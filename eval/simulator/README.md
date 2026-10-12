# Simulator results

How often does the lineup name the right commit, for a given number of replays? This folder answers that with simulated cases, where the culprit is known.

Each case has 40 suspect commits and one culprit picked at random. Every point is 500 cases, for bugs that fail from 100% of the time down to 10%. Three methods get the same cases and the same replay budget:

- The statistical bisect in `whodunit/lineup.py`. It names a commit only when it is 95% sure, and otherwise hands back the suspects that remain with their probabilities.
- Plain bisect with repeats. It replays each commit as many times as the budget allows and calls the commit bad on the first failure.
- Plain bisect with one replay per commit, which is what `git bisect run` does.

To regenerate everything here, run `uv run python -m whodunit.simulate --out eval/simulator`. It takes about ten minutes. `tables.md` has every number behind the charts, `results.json` has the raw counts, and `fix-bar.json`, `short-range.json`, `no-culprit.json` and `two-culprits.json` hold the four smaller runs described further down.

## When good commits never fail

![Accuracy against replay budget when good commits never fail](accuracy-clean-baseline.svg)

Plain bisect with repeats wins here at every budget. For a bug that fails 30% of the time, 80 replays get it to 97% while the statistical bisect names the right commit in 67% of cases. The statistical bisect needs 160 replays to reach 93%.

The reason is that plain bisect with repeats assumes a single failure convicts a commit, and in this world that is true. The statistical bisect does not assume it. It starts out believing a good commit fails about 5% of the time and spends replays finding out.

Two things are worth knowing before picking plain bisect on that basis. Its mistakes are silent: with 40 replays on the 30% bug it names the wrong commit in 26% of cases and gives no sign of it, where the statistical bisect names the wrong one in 2% and says "not sure yet" in the rest. And the dashed line shows the statistical bisect's top suspect is right in 91% of cases at 80 replays, so most of its "not sure yet" answers are pointing at the culprit already.

Plain bisect with one replay per commit is right 10% of the time on the 30% bug, at any budget.

## When good commits fail 5% of the time on their own

![Accuracy against replay budget when good commits fail 5% of the time](accuracy-flaky-baseline.svg)

Agents are rarely this clean. Give every good commit a 5% chance of failing by itself and plain bisect with repeats falls apart, and more replays make it worse. On the 30% bug it is right in 31% of cases with 40 replays and 4% with 320, because every extra replay of an innocent commit is another chance for a stray failure to convict it. Even a bug that fails every time is found in only 46% of cases at 40 replays.

The statistical bisect holds up. On the 30% bug it names the right commit in 62% of cases with 160 replays and 86% with 320. On a bug that fails every time it is right in 99% of cases and uses about 21 replays.

## Wrong accusations, out of accusations made

The first version of this page gave wrong accusations as a share of all cases, which ran from 0% to 7%. That flatters the method wherever it mostly names nobody. If it names a commit in 10 cases out of 500 and 5 of those are wrong, that is 1% of cases and half of its accusations. The second number is the one that says whether an accusation can be trusted, so `tables.md` now has it for every cell. Pooled over the ten budgets, for the statistical bisect:

| The bug fails | Good commits never fail | Good commits fail 5% of the time |
| ---: | ---: | ---: |
| 100% | 0 of 4,515 wrong, 0% | 39 of 4,301, 0.9% |
| 80% | 43 of 4,130, 1.0% | 70 of 3,842, 1.8% |
| 60% | 67 of 3,652, 1.8% | 122 of 3,208, 3.8% |
| 40% | 99 of 3,010, 3.3% | 153 of 2,359, 6.5% |
| 30% | 105 of 2,516, 4.2% | 113 of 1,659, 6.8% |
| 20% | 112 of 1,824, 6.1% | 122 of 720, 16.9% |
| 10% | 74 of 685, 10.8% | 70 of 90, 77.8% |

So "named at 95%" means what it says for bugs that fail about a third of the time or more. Below that it does not. For a bug that fails one run in ten on a clean baseline, about one accusation in nine is wrong across the budgets, and the small budgets are the worst: 11 wrong of 40 at 120 replays, 13 of 85 at 160, 17 of 318 at 320. When good commits also fail 5% of the time, a 10% bug is out of reach. The statistical bisect names nobody in 95% of cases even with 320 replays, 22 of the 26 commits it does name are innocent, and its top suspect is right in 13% of cases.

For comparison, plain bisect always names someone, so its wrong accusations are simply its wrong answers: 19% of them on a clean baseline across the whole grid, and 80% when good commits fail 5% of the time.

The model's own probability is off here because its priors are. It takes the failure rate of good commits to be about 5% and anything from rare to always for bad ones, so a rate of 10% sits closer to its idea of a good commit than of a bad one, and a few stray failures in a row can look like a change point.

### The sealed eval's two rare cases

Two of the five sealed cases fail about 12% and 14% of the time. Both went unnamed at 120 replays and were named, correctly, at 168. `short-range.json` simulates cases shaped like them: 13 suspects, a clean baseline, a bug that fails 12% of the time, 2,000 cases per row.

| Replays allowed | Named and right | Named and wrong | Nobody named | Wrong, of accusations made |
| ---: | ---: | ---: | ---: | ---: |
| 120 | 24% | 3.6% | 72% | 71 of 554, 13% |
| 168 | 46% | 3.4% | 51% | 68 of 978, 7% |
| 320 | 77% | 3.5% | 20% | 69 of 1,607, 4% |

Those cases were allowed up to 320 replays. With that much, an accusation in conditions like theirs is wrong about one time in 23, close to what the 95% bar promises. With only 120 it would have been wrong about one time in eight. The eval's result, five named and none wrongly, fits this and is far too small to confirm it.

## When no commit did it

Sometimes the range is innocent. A model is changed behind an alias, or a dependency that was never pinned moves, and every commit starts failing, the last good ref included. The lineup used to assume a culprit was in there somewhere. With every one of 20 commits failing it named the first suspect at 96.6%.

It now replays both ends as they behave today and weighs two stories against each other: the good ref is healthy and the bad ref is something else, or both fail at one rate. If the second is 95% likely, it names nobody and says the range is clear. `no-culprit.json` has 500 cases per row, 40 suspects, 160 replays allowed.

| What is going on | Said the range is clear | Accused a commit | Named nobody |
| --- | ---: | ---: | ---: |
| No culprit. Every commit fails every time | 100% | 0% | 0% |
| No culprit. Every commit fails 60% of the time | 97% | 1.8% | 1% |
| No culprit. Every commit fails 33% of the time | 45% | 3.0% | 52% |
| No culprit. Every commit fails 20% of the time | 8% | 3.0% | 89% |
| No culprit. Every commit fails 10% of the time | 0% | 2.6% | 97% |
| A culprit that fails every time, good commits fail 5% | 0% | 100% | 0% |
| A culprit that fails 30% of the time, good commits fail 5% | 0% | 67% | 33% |
| A culprit that fails 10% of the time, good commits fail 5% | 0% | 2.2% | 98% |

So when everything fails often, it says so. When everything fails only now and then, it mostly names nobody, which is the safe answer, and it accuses an innocent commit in about 3% of cases. In 1,500 cases that did have a culprit it never called the range clear.

Adding this check moved the numbers for a flaky baseline a little, because a good ref that fails once in its warm-up now gets a few more replays. Wrong accusations there went down slightly, and the tables on this page are the new ones. The clean-baseline numbers did not change at all.

## Two culprits in one range

The lineup assumes one change point. A range can hold two: a first commit that makes a case fail some of the time and a later one that makes it fail more. `two-culprits.json` sets three methods against each other on 200 cases a row with 20 suspects. This table is the row for 320 replays allowed.

- Today's lineup, with its single change point.
- "One or two": a model that holds every single commit and every pair of commits as a hypothesis at once, with an exact probability for each, and names a suspect when it is 95% likely to be a change point.
- Today's lineup first, and a second look with that model when what it gathered makes two changes the likelier story.

| What is going on | Method | Named every culprit, and nobody else | Named one of the two | Named an innocent commit | Named nobody | Replays |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| One change, fails every time | Today's lineup | 100% | | 0.0% | 0% | 19 |
| | One or two | 100% | | 0.0% | 0% | 20 |
| | Today's, then a second look | 100% | | 0.0% | 0% | 19 |
| One change, fails half the time | Today's lineup | 96% | | 4.5% | 0% | 34 |
| | One or two | 98% | | 2.0% | 0% | 50 |
| | Today's, then a second look | 98% | | 2.5% | 0% | 46 |
| One change, fails 30% of the time | Today's lineup | 94% | | 2.0% | 4% | 74 |
| | One or two | 94% | | 0.5% | 5% | 83 |
| | Today's, then a second look | 92% | | 2.0% | 6% | 81 |
| Two changes, 50% then every time | Today's lineup | 0% | 86% | 14.0% | 0% | 28 |
| | One or two | 55% | 40% | 2.5% | 2% | 60 |
| | Today's, then a second look | 48% | 42% | 8.0% | 2% | 56 |
| Two changes, 30% then 90% | Today's lineup | 0% | 76% | 23.5% | 0% | 44 |
| | One or two | 50% | 32% | 8.5% | 10% | 92 |
| | Today's, then a second look | 44% | 42% | 7.0% | 8% | 83 |
| Two changes, 20% then 60% | Today's lineup | 0% | 88% | 10.5% | 1% | 77 |
| | One or two | 40% | 48% | 6.5% | 6% | 122 |
| | Today's, then a second look | 26% | 62% | 10.5% | 2% | 97 |

With two regressions, today's lineup cannot name both, and in 10 to 24% of cases it names a commit that did nothing. The model that allows two names both in 40 to 55% of cases and an innocent commit in 2.5 to 8.5%. With one regression it is as accurate and a little more careful, and it costs 10 to 15 more replays. At 80 replays it names fewer cases than today's lineup, and the file has those rows. The second look does no better than the joint model, and it is taken in a quarter to two fifths of cases that had only one regression.

So the simulator supports the joint model, and it is not in the lineup yet. It has no alibi priors, no handling of skipped or voided replays, no parallel rounds, no resumed evidence and no clear-range check, and the published curves above would all need running again with it. What is in the lineup today is cheaper: each input of a case gets a posterior of its own, and a case whose inputs point at different commits is flagged as a likely pair of regressions.

## How much a kept fix shows

`whodunit fix` keeps a fix once its failure rate is 95% likely to be back within 5 points of the rate before the culprit. With a clean baseline that is 30 replays without a failure. `fix-bar.json` has how often a fix that is not really fixed clears the same bar, from 2,000 simulated fixes per row, replayed three at a time with up to 90 replays allowed.

| The fix still fails | Kept, after 12 clean replays before the culprit | Kept, after 24 |
| ---: | ---: | ---: |
| never | 100% | 100% |
| 1% of the time | 89% | 90% |
| 2% | 72% | 68% |
| 4% | 38% | 35% |
| 6% | 19% | 17% |
| 10% | 4% | 4% |

So a kept fix is not a proven one. A patch that still fails 4 runs in 100 is kept about one time in three. That is why the case file reports the count with the 95% upper bound on the failure rate after the fix, "0 failures in 30 replays. At most 6.2% at 95%.", and does not say proven. Telling a 2% leftover from a clean fix would take a few hundred replays, which nobody would pay for on every case.

## Where it falls short

- A bug that fails 20% of the time on a flaky baseline is named in only 48% of cases, even with 320 replays. The top suspect is right in 70%.
- A bug that fails 10% of the time on a clean baseline is named in 60% of cases with 320 replays, where plain bisect with repeats gets 99%. With 160 replays it is 14% against 85%.
- The 95% bar is not met for rare bugs. See the section on wrong accusations above: for a bug that fails 20% of the time or less, more than one accusation in twenty is wrong, and on a flaky baseline far more. The model assumes one change point and two fixed failure rates, and the prior on the good rate is a guess.
- These are simulated commits with independent replays. Real replays share a model provider and a machine, so their failures can come in bursts, which this does not capture.
- Small budgets are spent mostly on warming up. Below about 30 replays the statistical bisect rarely names anyone unless the bug fails every time.

## What changed from the first design

Two things, both found by simulating the 30% bug across 40 suspects with 300 replays allowed.

The first version put a uniform prior on both failure rates, so it had to learn from scratch that good commits mostly pass. It solved 59% of cases. Starting from the belief that a good commit fails about 5% of the time, loosely held, took that to 93%.

The brief said to test the commit that splits the posterior mass most evenly. The code now defaults to the replay with the highest expected information gain, and keeps the even split as `how="split"`. With the uniform prior the difference was large, 92% against 59%. With the current prior it is small: 282 cases solved against 280 out of 300, using 79 replays on average against 83. So the prior did the work, and the choice of picker barely matters.

# Whodunit

57 commits since it last worked. Which one did it?

Whodunit answers two questions about an AI agent that used to work and now fails: which commit broke it, and why that commit was made. Then it fixes the commit, proves the fix by replaying the failures, and counts what the breakage cost.

It was built for neatHack between 10 and 12 October 2026. `hackathon.md` is the dated build log, including the parts that went wrong.

## Why plain bisect is not enough

`git bisect` assumes a bad commit fails every time. Agents do not behave that way. A prompt change might break one run in three, and a commit that is perfectly fine might still fail one run in twenty. Test a bad commit once, see it pass, and bisect walks off in the wrong direction without telling you.

Whodunit replays the failing inputs against suspect commits and keeps a probability for each suspect being the first bad one. It names a commit only when it is 95% sure. If the replay budget runs out first, it hands back the suspects still in the lineup with their probabilities.

How well that works is measured two ways. [eval/sealed](eval/sealed/README.md) is five regressions planted by a separate session with a sealed answer key: three were named inside 120 replays, all five after more, and no commit was wrongly accused. Plain bisect with five retries, on the same five, got three right with fewer replays, named an innocent commit on the fourth and could not start on the fifth. [eval/simulator](eval/simulator/README.md) is simulated cases with a known culprit. The short version: when good commits never fail, plain bisect with repeats is cheaper. When good commits fail 5% of the time on their own, it falls apart and the statistical bisect does not. The simulator also shows where the 95% stops meaning 95%: for a bug that fails one run in ten, about one accusation in nine is wrong on a clean baseline, and nearly all of the few it makes are wrong on a flaky one.

## How a case runs

A case is a small TOML file: a symptom, the failing inputs with what each should have produced, the last good ref and the first bad ref. It can be written by hand, or from one failing run:

```bash
uv run whodunit open-case --from-trace <trace id>
```

That reads the run from neatroots or neatlogs cloud, takes the input from its root span and the bad ref from its tags, takes the expected result from the nearest earlier run of the same input that passed, and brackets the range with every run of that input. If no earlier run passed, it asks what the request should have produced. It writes the case file and stops.

One command then runs all of it:

```bash
uv run whodunit investigate cases/whole-history.toml --from-traffic refund-agent
```

It stops only when it needs the owner's ruling. Each step is also a command of its own (`lineup`, `brief`, `ruling`, `fix`, `damages`, `open-case`), and each adds to one record next to the case file. The case file page is drawn from that record.

On the refund agent's real history, 57 commits grown by a separate coding session, that command named the culprit at 99.8% after 20 replays, quoted the request that caused it, patched it, replayed the patch 30 times without a failure (at most 6.2% at 95%) and counted 120.00 in refunds that had gone to the wrong people. [evidence/casefile-whole-history.png](evidence/casefile-whole-history.png) is the page it wrote.

0. Before any replay, two things narrow the field. entire-graph says which commits could not have reached the agent (a README edit, a helper script the agent never calls), and those start with less suspicion. And ordinary runs that already asked what the case asks are evidence that is already paid for. On the headline case 22 of the 57 commits had an alibi. Run once more with no alibis and no ordinary runs, the case took 30 replays across 8 commits where it had taken 20 across 5. That is one run each way, with both taken away together, so it is a hint at what the head start saves and no more.
1. The lineup starts by replaying both ends as they behave today. If the last good ref now fails about as often as the first bad one, no commit did it: the lineup names nobody, says the range is clear, and reports what differs between old passing runs of the good ref and today's, from the model id and lockfile hash the runs recorded. Otherwise it checks every suspect commit out into its own git worktree and replays the case inputs there. Each replay is a real run of the agent, traced to neatroots and tagged with the commit and the case. A commit that will not build is skipped, as `git bisect skip` does. A replay that hits a provider or network error is voided and run again, and is never evidence about the commit.
2. The motive comes from Entire. A commit made by a coding agent carries a checkpoint, and the checkpoint holds the session. Whodunit finds the prompt that led to the commit and what the coding agent did next.
3. The brief is written by a model from the culprit's diff, that slice of the session, and a failing run set against a passing one. Every sentence has to cite a span, a commit or a checkpoint that is really in the evidence. An id written inside a sentence has to be real too, and so do words in quotation marks. Sentences that fail are cut. The brief is also held against what the lineup measured: one that says the bug fails every time when it was measured at 81% is sent back and asked for again with the rates in view.
4. The ruling is the owner's. It is asked once per kind of change (a prompt change, a tool change, a dependency) and remembered under `rulings/`.
5. The fix is a revert or a patch on a local branch. It is kept only when its failure rate is 95% likely to be back within 5 points of the rate before the culprit, which takes about 30 clean replays. What gets reported is the count and the 95% upper bound on the failure rate after the fix, for example "0 failures in 30 replays. At most 6.2% at 95%." That is the honest size of the claim: in simulation a fix that still fails 4 runs in 100 clears the same bar about one time in three. A fix that clears the bar on its own case is then replayed against the inputs of every other case under `cases/` and a short list of ordinary requests in `cases/ordinary.toml`. One that breaks a request that used to work is not kept, however clean its own replays were. A patch that falls short either way is tried once more with what went wrong in view, and after that the culprit is reverted. The case is kept under `cases/` as a regression test that `whodunit check` can replay against any ref.
6. The damages are counted from the traces. Only runs that fail the case's own check count: they asked what the case asks, on the culprit or later, and paid out something else. What they cost the shop is read from the refund tool's spans, and what they cost in tokens from the model spans. In this repo the ordinary runs were sent by `eval/traffic.py`, a script that plays customers, so the amounts are a test shop's and no real customer was involved.

The investigation is itself one trace. `whodunit investigate` sends it to neatlogs cloud, tagged with the case id: a span for each round of the lineup with the commit replayed, the verdicts and the top three suspects, and spans for the motive, the brief, the ruling, each fix attempt, its replays and the do-no-harm check. That needs the Neatlogs SDK (`uv sync --extra trace`) and `NEATLOGS_API_KEY` in `.env`. Without either, nothing is sent and everything else works the same. `WHODUNIT_TRACE=neatroots` sends it to the local collector, and `off` sends it nowhere. The failing run and the passing run a brief cites are sent to the cloud by neatroots, once `neatroots cloud login` has stored the project key.

Whodunit never pushes, opens a pull request or writes to anyone's finance model by itself. Those stay with the owner.

## Try it

You need Python 3.12, [uv](https://docs.astral.sh/uv/), git and a running neatroots.

```bash
uv sync
uv run pytest -m "not slow"                    # the fast tests, no model and no keys

# A throwaway repo with 20 commits, the refund agent and a planted bug:
uv run python tests/planted.py /tmp/planted
uv run python victims/refund-agent/fake_llm.py &
uv run whodunit lineup /tmp/planted/case.toml --repo /tmp/planted --method plain
```

Add `flaky-lookup 40 27` to the `planted.py` line for 40 commits with a bug at commit 27 that fails about one run in three, and drop `--method plain` to use the statistical bisect.

`uv run python -m whodunit.simulate --out eval/simulator` regenerates the simulator charts, and `uv run whodunit casebook` rewrites every case file and the index at `cases/index.html`.

## What is in here

- `whodunit/` is the tool. `lineup.py` holds both bisects, `replay.py` the worktree runner, `motive.py` the Entire lookups, `brief.py` the evidence and the brief, `ruling.py`, `fix.py` and `damages.py` the closing steps, `trace.py` the investigation's own trace, and `casefile/` the page.
- `victims/refund-agent/` is the agent under investigation. It started as the `refund-agent` example that ships with neatroots, which is licensed under Apache-2.0. The licence is in that folder and the changes are listed in its README.
- `eval/simulator/` has the accuracy curves, the tables behind them and what they show.
- `tests/planted.py` builds histories with a known culprit. The tests and the demo use the same builder.
- `AGENTS.md` is the working brief for anyone writing code here.

## Licence

Whodunit is licensed under Apache-2.0. The text is in [LICENSE](LICENSE). The refund agent in `victims/refund-agent/` began as an example from neatroots, which is under the same licence, and keeps its own copy.

## Models and keys

Keys live in `.env`, which git ignores. `.env.example` lists them. The code that needs a key reads the file itself.

Replays of the refund agent use a scripted model by default and cost nothing. `REFUND_LLM=gateway` or `REFUND_LLM=own` switches them to a real model. Keep one model for the whole of a case, because a model change in the middle would look like a regression.

The brief and the patch use `WHODUNIT_LLM`: `gateway`, `own`, `agent` for a coding agent in headless mode, or `none` for a fixed template with no model.

A case page links to a trace in neatlogs cloud only when `NEATLOGS_TRACE_URL` gives the dashboard's address for one, with `{trace_id}` where the id goes. Without it the page prints the trace ids and makes no link up.

## What it does not do yet

- The statistical bisect assumes one change point. Two regressions in the same range will confuse it.
- When the good ref fails about as often as the bad one under today's environment, no commit is named and the case says the range is clear. That catches a change that broke every commit at once, such as a model swapped behind an alias. A change outside the repo that breaks only the newer commits still looks like a regression in one of them.
- An accusation is less reliable than its 95% for bugs that fail rarely. In simulation the share of accusations that name the wrong commit is under 5% for bugs that fail 30% of the time or more on a clean baseline, 6% at 20% and 11% at 10%. [eval/simulator](eval/simulator/README.md) has the table.
- A replay that ends in a provider or network error is voided, run again and never counted. That relies on the agent saying so, with an exit code of its own or a recognisable last line on stderr, both listed in the case file. An agent that swallows such an error and prints a wrong answer would still be counted as failing.
- A replay that runs out of time gets one more try with double the limit, and counts as a failure only if it runs out again. A machine overloaded for longer than that can still frame a commit.
- Damages are estimates from token counts and list prices.
- The do-no-harm check is only as wide as the requests it is given: the other cases' inputs and five ordinary ones. A fix could still break something nobody listed.
- One of the five sealed cases is still open. Two patches improved it and neither brought it back to baseline, and the revert conflicts with later commits.
- The damages in the shop's currency depend on a tool span named `issue_refund`, so that part is specific to this agent.
- About one coding session in nine lost its Entire checkpoint while the history was grown. For those commits the motive falls back to the commit message.

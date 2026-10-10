# Whodunit

41 commits since it last worked. Which one did it?

Whodunit answers two questions about an AI agent that used to work and now fails: which commit broke it, and why that commit was made. Then it fixes the commit, proves the fix by replaying the failures, and counts what the breakage cost.

It was built for neatHack between 10 and 12 October 2026. `hackathon.md` is the dated build log, including the parts that went wrong.

## Why plain bisect is not enough

`git bisect` assumes a bad commit fails every time. Agents do not behave that way. A prompt change might break one run in three, and a commit that is perfectly fine might still fail one run in twenty. Test a bad commit once, see it pass, and bisect walks off in the wrong direction without telling you.

Whodunit replays the failing inputs against suspect commits and keeps a probability for each suspect being the first bad one. It names a commit only when it is 95% sure. If the replay budget runs out first, it hands back the suspects still in the lineup with their probabilities.

How well that works, measured on simulated cases with a known culprit, is in [eval/simulator](eval/simulator/README.md). The short version: when good commits never fail, plain bisect with repeats is cheaper. When good commits fail 5% of the time on their own, it falls apart and the statistical bisect does not.

## How a case runs

A case is a small TOML file: a symptom, the failing inputs with what each should have produced, the last good ref and the first bad ref.

```bash
uv run whodunit lineup cases/my-case.toml      # replay against the suspects and name the culprit
uv run whodunit brief cases/my-case.toml       # what the commit was asked to do, and a root-cause brief
uv run whodunit ruling cases/my-case.toml      # one question for the owner: revert, or keep the intent and patch
uv run whodunit fix cases/my-case.toml         # apply it on a branch and replay until the fix is proven
uv run whodunit damages cases/my-case.toml     # bad runs and what they cost
uv run whodunit open-case cases/my-case.toml   # the case file, as one HTML page
```

Each step adds to one record next to the case file, and the case file page is drawn from that record.

1. The lineup checks every suspect commit out into its own git worktree and replays the case inputs there. Each replay is a real run of the agent, traced to neatroots and tagged with the commit and the case. A commit that will not build is skipped, as `git bisect skip` does.
2. The motive comes from Entire. A commit made by a coding agent carries a checkpoint, and the checkpoint holds the session. Whodunit finds the prompt that led to the commit and what the coding agent did next.
3. The brief is written by a model from the culprit's diff, that slice of the session, and a failing run set against a passing one. Every sentence has to cite a span, a commit or a checkpoint that is really in the evidence. Sentences that do not are cut.
4. The ruling is the owner's. It is asked once per kind of change (a prompt change, a tool change, a dependency) and remembered under `rulings/`.
5. The fix is a revert or a patch on a local branch. It is replayed until it is 95% likely fixed or 95% likely not, and the case is kept under `cases/` as a regression test that `whodunit check` can replay against any ref.
6. The damages are counted from the traces: how many runs went bad since the failures began, and an estimate of what they cost.

Whodunit never pushes, opens a pull request or writes to anyone's finance model by itself. Those stay with the owner.

## Try it

You need Python 3.12, [uv](https://docs.astral.sh/uv/), git and a running neatroots.

```bash
uv sync
uv run pytest -m "not slow"                    # 85 tests, no model and no keys

# A throwaway repo with 20 commits, the refund agent and a planted bug:
uv run python tests/planted.py /tmp/planted
uv run python victims/refund-agent/fake_llm.py &
uv run whodunit lineup /tmp/planted/case.toml --repo /tmp/planted --method plain
```

Add `flaky-lookup 40 27` to the `planted.py` line for 40 commits with a bug at commit 27 that fails about one run in three, and drop `--method plain` to use the statistical bisect.

`uv run python -m whodunit.simulate --out eval/simulator` regenerates the simulator charts.

## What is in here

- `whodunit/` is the tool. `lineup.py` holds both bisects, `replay.py` the worktree runner, `motive.py` the Entire lookups, `brief.py` the evidence and the brief, `ruling.py`, `fix.py` and `damages.py` the closing steps, and `casefile/` the page.
- `victims/refund-agent/` is the agent under investigation. It started as the `refund-agent` example that ships with neatroots, which is licensed under Apache-2.0. The licence is in that folder and the changes are listed in its README.
- `eval/simulator/` has the accuracy curves, the tables behind them and what they show.
- `tests/planted.py` builds histories with a known culprit. The tests and the demo use the same builder.
- `AGENTS.md` is the working brief for anyone writing code here.

## Models and keys

Keys live in `.env`, which git ignores. `.env.example` lists them. The code that needs a key reads the file itself.

Replays of the refund agent use a scripted model by default and cost nothing. `REFUND_LLM=gateway` or `REFUND_LLM=own` switches them to a real model. Keep one model for the whole of a case, because a model change in the middle would look like a regression.

The brief and the patch use `WHODUNIT_LLM`: `gateway`, `own`, `agent` for a coding agent in headless mode, or `none` for a fixed template with no model.

## What it does not do yet

- The statistical bisect assumes one change point. Two regressions in the same range will confuse it.
- A replay that times out counts as a failure, so a badly overloaded machine can frame an innocent commit.
- Damages are estimates from token counts and list prices.
- The model-written patch has been through one real case, a prompt regression on a planted history. That is not many.
- Both full cases so far are on planted histories, which have no Entire checkpoints, so neither has a motive.

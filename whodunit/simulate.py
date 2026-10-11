"""A simulator for the lineup: how often is the right commit named, for a given replay budget?

    python -m whodunit.simulate --out eval/simulator

Each simulated case has `suspects` commits and one culprit chosen at random. A commit before
the culprit fails at `good_rate`, and the culprit and everything after it fails at `bad_rate`.
Three methods get the same case and the same budget of replays:

- statistical: the statistical bisect in whodunit.lineup.
- plain, repeated: plain bisect that replays each commit up to k times and calls it bad on the
  first failure, with k as large as the budget allows.
- plain, once: plain bisect with one replay per commit, which is what `git bisect run` does.
"""

import argparse
import json
import math
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from .lineup import FAIL, PASS, plain_bisect, statistical_bisect

RATES = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2, 0.1)  # two of the sealed cases turned out to fail about one run in eight
BUDGETS = (10, 20, 30, 40, 60, 80, 120, 160, 240, 320)
METHODS = ("statistical", "plain_repeated", "plain_once")


@dataclass
class Cell:
    method: str
    bad_rate: float
    good_rate: float
    budget: int
    suspects: int
    trials: int
    right: int = 0
    wrong: int = 0
    nobody: int = 0
    top_right: int = 0  # the most likely suspect was the culprit, whether or not anyone was named
    replays: int = 0  # total over all trials

    @property
    def accuracy(self) -> float:
        return self.right / self.trials


def one_case(method: str, suspects: int, culprit: int, bad_rate: float, good_rate: float, budget: int, rng: random.Random):
    """Returns (accused index or None, most likely suspect or None, replays used)."""
    used = 0

    def trial(position: int) -> str:
        nonlocal used
        used += 1
        return FAIL if rng.random() < (bad_rate if position >= culprit else good_rate) else PASS

    if method == "statistical":
        found = statistical_bisect(suspects, trial, budget)
        return found.culprit, None if found.note else found.remaining[0], found.replays
    steps = max(1, math.ceil(math.log2(suspects)))
    repeats = 1 if method == "plain_once" else max(1, budget // steps)

    def test(index: int) -> str:
        for _ in range(repeats):
            if trial(index) == FAIL:
                return FAIL
        return PASS

    accused = plain_bisect(suspects, test).culprit
    return accused, accused, used


def run_cell(cell: Cell, seed: int = 0) -> Cell:
    for n in range(cell.trials):
        # The culprit depends on the trial alone, so every method and budget meets the same cases.
        culprit = random.Random(f"culprit-{seed}-{n}").randrange(cell.suspects)
        rng = random.Random(f"{seed}-{cell.method}-{cell.bad_rate}-{cell.good_rate}-{cell.budget}-{n}")
        accused, top, used = one_case(cell.method, cell.suspects, culprit, cell.bad_rate, cell.good_rate, cell.budget, rng)
        cell.replays += used
        cell.top_right += top == culprit
        if accused is None:
            cell.nobody += 1
        elif accused == culprit:
            cell.right += 1
        else:
            cell.wrong += 1
    return cell


def sweep(suspects: int = 40, trials: int = 500, good_rate: float = 0.0, rates=RATES, budgets=BUDGETS, workers: int | None = None) -> list[Cell]:
    cells = [Cell(m, r, good_rate, b, suspects, trials) for r in rates for b in budgets for m in METHODS]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_cell, cells, chunksize=4))


def to_rows(cells: list[Cell]) -> list[dict]:
    """One dict per cell. `wrong_of_accused` is the share of accusations that named the wrong commit, or None if nobody was accused."""
    return [{
        **asdict(c), "accuracy": round(c.accuracy, 4), "mean_replays": round(c.replays / c.trials, 1),
        "wrong_of_accused": round(c.wrong / (c.right + c.wrong), 4) if c.right + c.wrong else None,
    } for c in cells]


def fix_bar(rates=(0.0, 0.01, 0.02, 0.04, 0.06, 0.10), baselines=((0, 12), (0, 24)), trials: int = 2000, seed: int = 0) -> list[dict]:
    """How often a fix that still fails at a given rate clears the bar for keeping it.

    The bar is the one `whodunit fix` uses: replay three at a time, up to 90 times, and keep the
    fix once its failure rate is 95% likely to be within 5 points of the rate before the
    culprit. `baselines` are (failures, passes) seen before the culprit, both clean.
    """
    from .fix import verify

    rows = []
    for good in baselines:
        for rate in rates:
            rng = random.Random(f"fix-bar-{seed}-{good}-{rate}")
            kept = replays = 0
            for _ in range(trials):
                checked = verify(lambda: FAIL if rng.random() < rate else PASS, good, (8, 0), parallel=3)
                kept += checked.fixed
                replays += checked.replays
            rows.append({"baseline_passes": good[1], "fix_fails": rate, "trials": trials, "kept": kept, "kept_share": round(kept / trials, 4), "mean_replays": round(replays / trials, 1)})
    return rows


def short_range(trials: int = 2000) -> list[dict]:
    """The sealed eval's two rare bugs, as near as a simulation gets: 13 suspects, a clean baseline, a bug that fails 12% of the time.

    The budgets are the ones those cases met: 120 replays, where nobody was named, 168, where
    both were, and 320, the most they were allowed.
    """
    cells = [Cell("statistical", 0.12, 0.0, budget, 13, trials) for budget in (120, 168, 320)]
    with ProcessPoolExecutor() as pool:
        return to_rows(list(pool.map(run_cell, cells)))


def _drift_cell(job: tuple[float, float, int, int, int]) -> dict:
    """One row of no_culprit(): `rate` is how often every commit fails, or how often the bad side fails when there is a culprit."""
    rate, good_rate, culprit, trials, budget = job
    clear = accused = 0
    for n in range(trials):
        rng = random.Random(f"drift-{rate}-{good_rate}-{culprit}-{n}")
        found = statistical_bisect(40, lambda position: FAIL if rng.random() < (rate if culprit < 0 or position >= culprit else good_rate) else PASS, budget)
        clear += found.clear
        accused += found.culprit is not None
    return {"fails": rate, "good_commits_fail": good_rate, "has_a_culprit": culprit >= 0, "trials": trials, "budget": budget,
            "said_clear": clear, "accused_a_commit": accused, "named_nobody": trials - clear - accused}


def no_culprit(trials: int = 500, budget: int = 160) -> list[dict]:
    """What the lineup says when no commit did it, and how often it says so when one did.

    In the first rows every one of 40 commits fails at the same rate, the good ref included, as
    after a change outside the repo. In the last rows there is a real culprit at suspect 20, on
    a baseline where good commits fail 5% of the time, and "clear" would be the wrong answer.
    """
    jobs = [(rate, rate, -1, trials, budget) for rate in (1.0, 0.6, 0.33, 0.2, 0.1)] + [(rate, 0.05, 20, trials, budget) for rate in (1.0, 0.3, 0.1)]
    with ProcessPoolExecutor() as pool:
        return list(pool.map(_drift_cell, jobs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="eval/simulator")
    parser.add_argument("--suspects", type=int, default=40)
    parser.add_argument("--trials", type=int, default=500)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, good_rate in (("clean_baseline", 0.0), ("flaky_baseline", 0.05)):
        rows = to_rows(sweep(args.suspects, args.trials, good_rate))
        results[name] = {"suspects": args.suspects, "trials": args.trials, "good_rate": good_rate, "cells": rows}
        print(f"{name}: {len(rows)} cells")
    (out / "results.json").write_text(json.dumps(results, indent=1) + "\n")
    (out / "fix-bar.json").write_text(json.dumps(fix_bar(), indent=1) + "\n")
    (out / "short-range.json").write_text(json.dumps(short_range(), indent=1) + "\n")
    (out / "no-culprit.json").write_text(json.dumps(no_culprit(), indent=1) + "\n")
    from .chart import write_charts

    write_charts(results, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

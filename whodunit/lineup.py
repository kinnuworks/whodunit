"""The lineup: narrowing the suspects down to one commit.

Plain bisect is right when the bug fails every time, and is the baseline. The statistical
bisect further down is for bugs that fail only some of the time.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Sequence

PASS, FAIL, SKIP = "pass", "fail", "skip"
VOID = "void"  # a replay that hit a provider or network error. It is never evidence.


@dataclass
class Lineup:
    culprit: int | None  # index into the suspects, or None if skips left more than one
    remaining: list[int]  # the suspects that could still be the first bad commit
    tested: list[tuple[int, str]] = field(default_factory=list)  # (index, verdict) in the order they ran
    posterior: list[float] | None = None  # P(first bad) per suspect, from the statistical bisect
    replays: int | None = None  # replays that returned a verdict
    rates: tuple[float, float] | None = None  # estimated failure rate before and from the top suspect
    note: str = ""  # why nobody was named, when the evidence itself was the problem


def plain_bisect(count: int, test: Callable[[int], str]) -> Lineup:
    """Find the first failing suspect among `count`, oldest first.

    The commit before suspect 0 is known good and the last suspect is known bad. `test(i)` returns
    pass, fail or skip. A skipped commit cannot be judged, so the search steps to its nearest
    untested neighbour, as `git bisect skip` does. If only skipped commits separate the last
    pass from the first fail, they all stay in `remaining`.
    """
    if count < 1:
        raise ValueError("there are no suspects")
    good, bad = -1, count - 1  # the first bad commit is in (good, bad]
    skipped: set[int] = set()
    tested: list[tuple[int, str]] = []
    while True:
        open_ = [i for i in range(good + 1, bad) if i not in skipped]
        if not open_:
            break
        middle = (good + bad) / 2
        pick = min(open_, key=lambda i: (abs(i - middle), i))
        verdict = test(pick)
        tested.append((pick, verdict))
        if verdict == PASS:
            good = pick
        elif verdict == FAIL:
            bad = pick
        else:
            skipped.add(pick)
    remaining = list(range(good + 1, bad + 1))
    return Lineup(culprit=bad if len(remaining) == 1 else None, remaining=remaining, tested=tested)


def linear_scan_cost(culprit: int) -> int:
    """How many commits a scan from the oldest suspect tests before it meets the culprit."""
    return culprit + 1



# The statistical bisect, for bugs that fail only some of the time.
#
# One change point c: every suspect before c fails at rate p_good, and c and everything after
# it fails at rate p_bad. Neither rate is known. Both get a Beta prior, and because a Beta prior
# with pass and fail counts integrates in closed form, the probability of the evidence under
# "c is the first bad commit" is exact. No sampling and no model.

GOOD_PRIOR = (0.5, 9.5)  # Beta prior on the failure rate before the change: about 5%, loosely held
BAD_PRIOR = (1.0, 1.0)  # and from the change onward: anything from rare to always


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _entropy(q: float) -> float:
    return 0.0 if q <= 0.0 or q >= 1.0 else -(q * math.log(q) + (1.0 - q) * math.log(1.0 - q))


class ChangePoint:
    """What the replays so far say about which suspect is the first bad one.

    Position -1 is the last good ref. Positions 0 to count-1 are the suspects, oldest first,
    and the last of them is the bad ref.
    """

    def __init__(self, count: int, priors: Sequence[float] | None = None, good_prior=GOOD_PRIOR, bad_prior=BAD_PRIOR):
        self.good_prior, self.bad_prior = good_prior, bad_prior
        if count < 1:
            raise ValueError("there are no suspects")
        self.count = count
        weights = list(priors) if priors is not None else [1.0] * count
        if len(weights) != count or min(weights) < 0 or sum(weights) <= 0:
            raise ValueError("priors must be one weight per suspect, none negative")
        self.log_prior = [math.log(w) if w > 0 else -math.inf for w in weights]
        self.fails = [0] * (count + 1)  # slot 0 is the good ref
        self.passes = [0] * (count + 1)

    def observe(self, position: int, failed: bool) -> None:
        (self.fails if failed else self.passes)[position + 1] += 1

    @property
    def replays(self) -> int:
        return sum(self.fails) + sum(self.passes)

    def _sides(self):
        """For each suspect c: fails and passes on the good side and on the bad side, if c is the first bad one."""
        total_f, total_p = sum(self.fails), sum(self.passes)
        good_f, good_p = self.fails[0], self.passes[0]
        for c in range(self.count):
            yield good_f, good_p, total_f - good_f, total_p - good_p
            good_f += self.fails[c + 1]
            good_p += self.passes[c + 1]

    def posterior(self) -> list[float]:
        """P(suspect i is the first bad commit), for each suspect."""
        (ga, gb), (ba, bb) = self.good_prior, self.bad_prior
        logs = [
            self.log_prior[c] + _log_beta(ga + gf, gb + gp) + _log_beta(ba + bf, bb + bp)
            for c, (gf, gp, bf, bp) in enumerate(self._sides())
        ]
        top = max(logs)
        weights = [math.exp(v - top) for v in logs]
        norm = sum(weights)
        return [w / norm for w in weights]

    def rates(self, culprit: int | None = None) -> list[tuple[float, float]] | tuple[float, float]:
        """Posterior mean failure rate (before, from) each suspect, or for one suspect."""
        (ga, gb), (ba, bb) = self.good_prior, self.bad_prior
        every = [((ga + gf) / (ga + gb + gf + gp), (ba + bf) / (ba + bb + bf + bp)) for gf, gp, bf, bp in self._sides()]
        return every if culprit is None else every[culprit]

    def pick(self, posterior: Sequence[float], skipped: set[int] = frozenset(), how: str = "gain") -> int | None:
        """Which suspect to replay next. The last suspect is never picked, since it is bad either way.

        "gain" picks the replay expected to tell us the most about which suspect is the first bad
        one (the mutual information between its outcome and c). "split" picks the suspect that
        divides the posterior mass most evenly, as plain bisect does. A pass at a commit that
        fails 30% of the time says little and a failure says a lot, which "gain" accounts for.
        In simulation the two end up close; see eval/simulator/README.md.
        """
        if how == "split":
            best, best_gap, mass = None, None, 0.0
            for i in range(self.count - 1):
                mass += posterior[i]
                if i in skipped:
                    continue
                gap = abs(mass - 0.5)
                if best_gap is None or gap < best_gap:
                    best, best_gap = i, gap
            return best
        rates = self.rates()
        # Replaying suspect i fails at the bad rate if c <= i and at the good rate if c > i.
        later_q = [0.0] * (self.count + 1)  # sum over c > i of P(c) * good rate
        later_h = [0.0] * (self.count + 1)
        for c in range(self.count - 1, -1, -1):
            later_q[c] = later_q[c + 1] + posterior[c] * rates[c][0]
            later_h[c] = later_h[c + 1] + posterior[c] * _entropy(rates[c][0])
        best, best_gain, q, h = None, -1.0, 0.0, 0.0
        for i in range(self.count - 1):
            q += posterior[i] * rates[i][1]
            h += posterior[i] * _entropy(rates[i][1])
            if i in skipped:
                continue
            gain = _entropy(q + later_q[i + 1]) - (h + later_h[i + 1])
            if gain > best_gain:
                best, best_gain = i, gain
        return best

def statistical_bisect(
    count: int,
    trial: Callable[[int], str],
    budget: int,
    priors: Sequence[float] | None = None,
    confidence: float = 0.95,
    warmup: int = 6,
    parallel: int = 1,
    how: str = "gain",
    good_prior: tuple[float, float] = GOOD_PRIOR,
    bad_prior: tuple[float, float] = BAD_PRIOR,
    on_round: Callable[[list[int], list[str], list[float]], None] | None = None,
    evidence: Sequence[tuple[int, bool]] = (),
) -> Lineup:
    """Find the first bad suspect when a bad commit only fails some of the time.

    `trial(position)` runs one replay and returns pass, fail, skip or void. Position -1 is the
    good ref. `budget` is the most replays to spend, counting the warm-up runs at both ends.
    Stops when one suspect holds `confidence` of the posterior, or when the budget is gone, in
    which case `remaining` lists the suspects still in play, most likely first.

    A void replay hit a provider or network error. It is not counted as a pass or a failure
    and does not use up the budget. If three rounds in a row are all void, the lineup stops
    and says the provider kept failing.

    `evidence` is what is already known, as (position, failed) pairs: replays from an earlier
    run of the same case, or the agent's ordinary traffic. It shapes the posterior from the
    start and does not count against the budget.
    """
    state = ChangePoint(count, priors, good_prior, bad_prior)
    for position, failed in evidence:
        state.observe(position, failed)
    known = state.replays
    tested: list[tuple[int, str]] = []
    skipped: set[int] = set()
    bad = count - 1
    void_rounds = 0  # rounds in a row in which every replay was voided
    down = "the model provider or the network kept failing, so the replays could not be judged"

    def run(positions: list[int]) -> list[str]:
        nonlocal void_rounds
        positions = positions[: max(0, budget - (state.replays - known))]
        if parallel > 1 and len(positions) > 1:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                verdicts = list(pool.map(trial, positions))
        else:
            verdicts = [trial(p) for p in positions]
        for position, verdict in zip(positions, verdicts):
            tested.append((position, verdict))
            if verdict == SKIP:
                skipped.add(position)
            elif verdict != VOID:
                state.observe(position, verdict == FAIL)
        if positions:
            void_rounds = void_rounds + 1 if all(v == VOID for v in verdicts) else 0
        if on_round and positions:
            on_round(positions, verdicts, state.posterior())
        return verdicts

    def finish(note: str = "") -> Lineup:
        posterior = state.posterior()
        ranked = sorted(range(count), key=lambda i: -posterior[i])
        top = ranked[0]
        named = top if posterior[top] >= confidence and not note else None
        remaining = [top] if named is not None else [i for i in ranked if posterior[i] >= 0.01]
        return Lineup(
            culprit=named, remaining=remaining, tested=tested, posterior=posterior,
            replays=state.replays, rates=state.rates(top), note=note,
        )

    # Warm up at both ends, so the two failure rates start from evidence. Ends that earlier
    # evidence already covers need less of it.
    warmup = max(1, min(warmup, budget // 4))
    seen_good = state.fails[0] + state.passes[0]
    seen_bad = state.fails[bad + 1] + state.passes[bad + 1]
    first = []
    for n in range(warmup):
        if seen_good + n < warmup:
            first.append(-1)
        if seen_bad + n < warmup:
            first.append(bad)
    run(first)
    if -1 in skipped or bad in skipped:
        return finish("the good ref or the bad ref will not build")
    # An end that lost warm-up replays to a provider error gets them again, a few times at most.
    for _ in range(3):
        short = [-1] * max(0, warmup - state.fails[0] - state.passes[0]) + [bad] * max(0, warmup - state.fails[bad + 1] - state.passes[bad + 1])
        if not short or void_rounds >= 3:
            break
        run(short)
    if void_rounds >= 3 or state.fails[0] + state.passes[0] == 0 or state.fails[bad + 1] + state.passes[bad + 1] == 0:
        return finish(down)
    extra = 0
    while state.fails[bad + 1] == 0 and extra < 2 * warmup and state.replays - known < budget and void_rounds < 3:
        run([bad] * max(1, parallel))  # a rare failure may simply not have shown yet
        extra += max(1, parallel)
    if void_rounds >= 3:
        return finish(down)
    if state.fails[bad + 1] == 0:
        return finish(f"the bad ref passed all {state.passes[bad + 1]} of its replays")

    while state.replays - known < budget:
        posterior = state.posterior()
        if max(posterior) >= confidence:
            break
        position = state.pick(posterior, skipped, how)
        if position is None:
            break
        run([position] * max(1, parallel))
        if void_rounds >= 3:
            return finish(down)
    return finish()

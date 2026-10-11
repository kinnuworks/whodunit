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
    clear: bool = False  # the good ref fails about as often as the bad one today, so no commit in the range did it


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


def same_at_both_ends(good: tuple[int, int], bad: tuple[int, int], good_prior=GOOD_PRIOR, bad_prior=BAD_PRIOR) -> float:
    """P(the good ref and the bad ref fail at one and the same rate), from today's replays of each.

    `good` and `bad` are (failures, passes). Two stories are weighed against each other. In
    one, the good ref is a healthy commit and the bad ref fails at some other rate, which is
    what the lineup assumes. In the other, both ends share a single rate, which is what the
    replays look like when something outside the repo changed: a model behind an alias, a
    dependency that was never pinned. Both have a closed form, like everything else here.
    """
    (gf, gp), (bf, bp) = good, bad
    one_rate = _log_beta(bad_prior[0] + gf + bf, bad_prior[1] + gp + bp) - _log_beta(*bad_prior)
    two_rates = (_log_beta(good_prior[0] + gf, good_prior[1] + gp) - _log_beta(*good_prior)
                 + _log_beta(bad_prior[0] + bf, bad_prior[1] + bp) - _log_beta(*bad_prior))
    top = max(one_rate, two_rates)
    return math.exp(one_rate - top) / (math.exp(one_rate - top) + math.exp(two_rates - top))


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
    around: Callable[[list[int], Callable[[], list[str]]], list[str]] | None = None,
) -> Lineup:
    """Find the first bad suspect when a bad commit only fails some of the time.

    `trial(position)` runs one replay and returns pass, fail, skip or void. Position -1 is the
    good ref. `budget` is the most replays to spend, counting the warm-up runs at both ends.
    Stops when one suspect holds `confidence` of the posterior, or when the budget is gone, in
    which case `remaining` lists the suspects still in play, most likely first.

    A void replay hit a provider or network error. It is not counted as a pass or a failure
    and does not use up the budget. If three rounds in a row are all void, the lineup stops
    and says the provider kept failing.

    The warm-up replays the good ref as it behaves today. If it now fails about as often as
    the bad ref, no commit in the range did it, and the result says so with `clear` set and
    nobody named. Evidence from before today is not used for that judgement.

    `evidence` is what is already known, as (position, failed) pairs: replays from an earlier
    run of the same case, or the agent's ordinary traffic. It shapes the posterior from the
    start and does not count against the budget.

    `around(positions, go)` wraps one round: it has to call `go()`, which runs the replays and
    returns their verdicts, and return those verdicts. It is how a round gets a span of its own
    in the investigation's trace.
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
        positions = positions[: max(0, budget - (state.replays - known))]
        if not positions:
            return []
        return around(positions, lambda: replay(positions)) if around else replay(positions)

    def replay(positions: list[int]) -> list[str]:
        nonlocal void_rounds
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

    def finish(note: str = "", clear: bool = False) -> Lineup:
        posterior = state.posterior()
        ranked = sorted(range(count), key=lambda i: -posterior[i])
        top = ranked[0]
        named = top if posterior[top] >= confidence and not note else None
        remaining = [top] if named is not None else [] if clear else [i for i in ranked if posterior[i] >= 0.01]
        return Lineup(
            culprit=named, remaining=remaining, tested=tested, posterior=posterior,
            replays=state.replays, rates=state.rates(top), note=note, clear=clear,
        )

    def today(position: int) -> tuple[int, int]:
        """(failures, passes) at one end, from this run's replays only."""
        seen = [verdict for at, verdict in tested if at == position]
        return seen.count(FAIL), seen.count(PASS)

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
    # Did any commit do it? If the good ref fails today, it may be failing as often as the bad one. A few
    # more replays at both ends settle it either way, and then the question is closed before the bisect starts.
    more = 0
    while today(-1)[0] and 0.05 < same_at_both_ends(today(-1), today(bad), good_prior, bad_prior) < 0.95 \
            and more < 2 * warmup and state.replays - known < budget and void_rounds < 3:
        step = max(1, parallel)
        run([-1] * step + [bad] * step)
        more += step
    (good_f, good_p), (bad_f, bad_p) = today(-1), today(bad)
    if good_f and same_at_both_ends((good_f, good_p), (bad_f, bad_p), good_prior, bad_prior) >= 0.95:
        return finish(f"the last good ref now fails about as often as the first bad one, {good_f} of {good_f + good_p} replays against "
                      f"{bad_f} of {bad_f + bad_p}, so no commit in this range did it", clear=True)
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


# One change point or two.
#
# The model above assumes a single change. Two regressions in one range break that: a first
# commit that makes a case fail some of the time and a later one that makes it fail more. Here
# both stories are held at once. A hypothesis is either one change point c, or a pair c1 < c2
# with three stretches of commits, each with a failure rate of its own. Every hypothesis has
# an exact probability for the evidence, from the same Beta integrals, so the posterior over
# all of them is exact and so is the Bayes factor for two changes against one.


@dataclass
class Changes:
    culprits: tuple[int, ...] | None  # one suspect, or two, when a single hypothesis holds `confidence`
    two: float  # P(there are two change points), from the evidence
    bayes_factor: float  # evidence for two changes over one. Above 1 favours two.
    top: tuple[int, ...]  # the most likely hypothesis, named or not
    top_probability: float
    replays: int
    tested: list[tuple[int, str]] = field(default_factory=list)


def chance_of_two(count: int, evidence: Sequence[tuple[int, bool]], prior_two: float = 0.5) -> tuple[float, tuple[int, ...]]:
    """(P(two change points), the likeliest pair) for evidence a lineup has already gathered."""
    state = OneOrTwo(count, prior_two=prior_two)
    for position, failed in evidence:
        state.observe(position, failed)
    weights = state.weights()
    ones = len(state.singles)
    pair = max(range(ones, len(weights)), key=weights.__getitem__)
    return sum(weights[ones:]), state.hypotheses[pair]


class OneOrTwo:
    """The posterior over "one change at c" and "changes at c1 and c2", for `count` suspects."""

    def __init__(self, count: int, good_prior=GOOD_PRIOR, bad_prior=BAD_PRIOR, prior_two: float = 0.5):
        if count < 2:
            raise ValueError("two change points need at least two suspects")
        self.count, self.good_prior, self.bad_prior = count, good_prior, bad_prior
        self.fails = [0] * (count + 1)  # slot 0 is the good ref
        self.passes = [0] * (count + 1)
        self.singles = [(c,) for c in range(count)]
        self.pairs = [(a, b) for a in range(count - 1) for b in range(a + 1, count)]
        # The two stories start level, and within each every place for the change is as likely as any other.
        self.log_prior = [math.log((1 - prior_two) / len(self.singles))] * len(self.singles) + [math.log(prior_two / len(self.pairs))] * len(self.pairs)
        self.hypotheses = self.singles + self.pairs

    def observe(self, position: int, failed: bool) -> None:
        (self.fails if failed else self.passes)[position + 1] += 1

    @property
    def replays(self) -> int:
        return sum(self.fails) + sum(self.passes)

    def _stretches(self):
        """For each hypothesis, (failures, passes) in each stretch of commits it divides the range into."""
        cf, cp = [0], [0]
        for f, p in zip(self.fails, self.passes):
            cf.append(cf[-1] + f)
            cp.append(cp[-1] + p)
        end = self.count + 1
        for cuts in self.hypotheses:
            edges = [0, *(c + 1 for c in cuts), end]
            yield [(cf[b] - cf[a], cp[b] - cp[a]) for a, b in zip(edges, edges[1:])]

    def weights(self) -> list[float]:
        """P(hypothesis | evidence), in the order of `self.hypotheses`."""
        logs = []
        for prior, stretches in zip(self.log_prior, self._stretches()):
            total = prior
            for n, (f, p) in enumerate(stretches):
                a, b = self.good_prior if n == 0 else self.bad_prior
                total += _log_beta(a + f, b + p) - _log_beta(a, b)
            logs.append(total)
        top = max(logs)
        raw = [math.exp(v - top) for v in logs]
        norm = sum(raw)
        return [w / norm for w in raw]

    def rates(self) -> list[list[float]]:
        """The expected failure rate in each stretch, for each hypothesis."""
        out = []
        for stretches in self._stretches():
            out.append([((self.good_prior if n == 0 else self.bad_prior)[0] + f) / (sum(self.good_prior if n == 0 else self.bad_prior) + f + p) for n, (f, p) in enumerate(stretches)])
        return out

    def pick(self, weights: Sequence[float]) -> int | None:
        """The suspect whose replay is expected to say the most about which hypothesis is true."""
        rates = self.rates()
        best, best_gain = None, -1.0
        for i in range(self.count - 1):  # the last suspect is in the last stretch whatever the hypothesis
            mix = spread = 0.0
            for weight, cuts, rate in zip(weights, self.hypotheses, rates):
                if weight < 1e-9:
                    continue
                q = rate[sum(i >= c for c in cuts)]
                mix += weight * q
                spread += weight * _entropy(q)
            gain = _entropy(mix) - spread
            if gain > best_gain:
                best, best_gain = i, gain
        return best


def one_or_two_bisect(count: int, trial: Callable[[int], str], budget: int, confidence: float = 0.95, warmup: int = 6, prior_two: float = 0.5,
                      evidence: Sequence[tuple[int, bool]] = ()) -> Changes:
    """Like statistical_bisect, without assuming there is only one change.

    `evidence` is what is already known, as (position, failed) pairs, for instance every replay
    an ordinary lineup made before this one took a second look. It does not count against the
    budget, and with it the warm-up is skipped.

    A suspect is named when it is `confidence` likely to be a change point, counting every
    hypothesis it appears in. While one change is the likelier story, the search stops as soon
    as its commit is named. While two are likelier, it goes on until both are. `two` in the
    result says how likely a second change is, whoever was named. `trial(position)` is as for
    statistical_bisect.
    """
    state = OneOrTwo(count, prior_two=prior_two)
    tested: list[tuple[int, str]] = []

    def run(position: int) -> None:
        verdict = trial(position)
        tested.append((position, verdict))
        if verdict in (PASS, FAIL):
            state.observe(position, verdict == FAIL)

    def read(weights: list[float]) -> tuple[float, tuple[int, ...], float, tuple[int, ...] | None]:
        """(P(two changes), the leading hypothesis of the likelier story, its weight, who can be named)."""
        ones = len(state.singles)
        two = sum(weights[ones:])
        lead = max(range(ones, len(weights)) if two > 0.5 else range(ones), key=weights.__getitem__)
        guilt = [0.0] * count  # P(this suspect is a change point), over every hypothesis that has it
        for weight, cuts in zip(weights, state.hypotheses):
            for c in cuts:
                guilt[c] += weight
        named = state.hypotheses[lead] if all(guilt[c] >= confidence for c in state.hypotheses[lead]) else None
        return two, state.hypotheses[lead], weights[lead], named

    for position, failed in evidence:
        state.observe(position, failed)
    known = state.replays
    for _ in range(0 if evidence else max(1, min(warmup, budget // 4))):
        run(-1)
        run(count - 1)
    weights = state.weights()
    two, lead, share, named = read(weights)
    while state.replays - known < budget and named is None:
        position = state.pick(weights)
        if position is None:
            break
        run(position)
        weights = state.weights()
        two, lead, share, named = read(weights)
    return Changes(
        culprits=named, two=two, bayes_factor=two / max(1e-12, 1 - two) * (1 - prior_two) / prior_two,
        top=lead, top_probability=share, replays=state.replays, tested=tested,
    )

import math

import pytest

from whodunit.lineup import FAIL, PASS, SKIP, plain_bisect


def oracle(culprit, skipped=()):
    def test(i):
        if i in skipped:
            return SKIP
        return FAIL if i >= culprit else PASS
    return test


@pytest.mark.parametrize("count", range(1, 42))
def test_finds_every_culprit(count):
    for culprit in range(count):
        found = plain_bisect(count, oracle(culprit))
        assert found.culprit == culprit
        assert found.remaining == [culprit]
        assert len(found.tested) <= math.ceil(math.log2(count)) if count > 1 else not found.tested


def test_never_tests_the_known_bad_end():
    found = plain_bisect(20, oracle(7))
    assert 19 not in [i for i, _ in found.tested]


def test_steps_around_a_skipped_commit():
    found = plain_bisect(20, oracle(13, skipped={9, 4}))
    assert found.culprit == 13
    assert (9, SKIP) in found.tested


def test_skips_next_to_the_culprit_leave_a_range():
    # 11 and 12 will not build, so the first bad commit is one of 11, 12, 13.
    found = plain_bisect(20, oracle(13, skipped={11, 12}))
    assert found.culprit is None
    assert found.remaining == [11, 12, 13]


def test_no_suspects_is_an_error():
    with pytest.raises(ValueError):
        plain_bisect(0, oracle(0))


# The statistical bisect, against simulated commits.

import random

from whodunit.lineup import ChangePoint, statistical_bisect


def flaky(culprit, bad_rate, good_rate=0.0, seed=0, skipped=()):
    rng = random.Random(seed)

    def trial(position):
        if position in skipped:
            return SKIP
        return FAIL if rng.random() < (bad_rate if position >= culprit else good_rate) else PASS
    return trial


def tally(count, bad_rate, budget, cases=120, good_rate=0.0, **kw):
    right = wrong = nobody = 0
    for n in range(cases):
        culprit = random.Random(n * 7919).randrange(count)
        found = statistical_bisect(count, flaky(culprit, bad_rate, good_rate, seed=n), budget, **kw)
        assert found.replays <= budget
        if found.culprit is None:
            nobody += 1
        elif found.culprit == culprit:
            right += 1
        else:
            wrong += 1
    return right, wrong, nobody


def test_posterior_starts_at_the_prior():
    assert ChangePoint(4).posterior() == pytest.approx([0.25] * 4)
    assert ChangePoint(3, priors=[1, 0, 1]).posterior() == pytest.approx([0.5, 0, 0.5])


def test_a_failure_moves_the_mass_to_that_commit_and_earlier():
    state = ChangePoint(10)
    for _ in range(6):
        state.observe(-1, False)
        state.observe(9, True)
    before = state.posterior()
    state.observe(4, True)
    after = state.posterior()
    assert sum(after[:5]) > sum(before[:5]) and sum(after[:5]) > 0.9


def test_always_failing_bug_is_found_every_time_and_cheaply():
    right, wrong, nobody = tally(40, 1.0, budget=40)
    assert (right, wrong, nobody) == (120, 0, 0)


def test_bug_that_fails_30_percent_of_the_time():
    right, wrong, nobody = tally(20, 0.3, budget=200)
    assert right >= 100  # most cases are solved inside the budget
    assert wrong <= 8  # a 95% bar should be wrong about 1 time in 20


def test_flaky_baseline_does_not_cause_a_flood_of_wrong_accusations():
    right, wrong, nobody = tally(20, 0.4, budget=200, good_rate=0.05)
    assert right >= 85 and wrong <= 9


def test_budget_runs_out_with_suspects_ranked():
    found = statistical_bisect(40, flaky(25, 0.2, seed=3), budget=30)
    assert found.culprit is None and not found.note
    assert [found.posterior[i] for i in found.remaining] == sorted((found.posterior[i] for i in found.remaining), reverse=True)
    assert sum(found.posterior) == pytest.approx(1.0)


def test_a_bad_ref_that_never_fails_is_reported():
    found = statistical_bisect(10, lambda position: PASS, budget=60)
    assert found.culprit is None and "passed all" in found.note


def test_skipped_commits_are_never_replayed_twice():
    found = statistical_bisect(20, flaky(12, 1.0, skipped={11, 5}), budget=80)
    assert [i for i, v in found.tested if v == SKIP].count(11) <= 1
    # 11 will not build, so 11 and 12 cannot be told apart and nobody is named.
    assert found.culprit is None and set(found.remaining) == {11, 12}


def test_priors_speed_things_up_when_they_point_the_right_way():
    def mean_replays(priors):
        total = 0
        for n in range(60):
            total += statistical_bisect(30, flaky(17, 0.5, seed=n), 300, priors=priors).replays
        return total / 60
    helpful = [1.0 if 15 <= i <= 19 else 0.05 for i in range(30)]
    assert mean_replays(helpful) < mean_replays(None)


def test_parallel_rounds_stay_inside_the_budget():
    found = statistical_bisect(20, flaky(9, 0.5, seed=1), budget=50, parallel=4)
    assert found.replays <= 50


def test_earlier_evidence_is_free_and_shapes_the_posterior():
    first = statistical_bisect(30, flaky(17, 0.25, seed=5), budget=40)
    assert first.culprit is None
    known = [(position, verdict == FAIL) for position, verdict in first.tested if verdict != SKIP]
    calls = []

    def trial(position):
        calls.append(position)
        return flaky(17, 0.25, seed=6 + len(calls))(position)
    second = statistical_bisect(30, trial, budget=25, evidence=known)
    assert len(calls) <= 25  # the budget covers new replays only
    assert second.replays == len(known) + len(calls)
    assert -1 not in calls  # the good ref was already warmed up


def test_wrong_accusations_are_counted_against_accusations_made():
    from whodunit.chart import table_markdown, wrong_of_accused
    from whodunit.simulate import Cell, to_rows

    rows = to_rows([Cell("statistical", 0.1, 0.05, 160, 40, 500, right=90, wrong=10, nobody=400), Cell("statistical", 0.1, 0.05, 20, 40, 500, nobody=500)])
    assert rows[0]["wrong_of_accused"] == 0.1 and rows[1]["wrong_of_accused"] is None  # 10 of 100 accusations, where 10 of 500 cases would read as 2%
    assert wrong_of_accused(rows[0]) == "10% (10 of 100)" and wrong_of_accused(rows[1]) == "nobody named"
    assert "Statistical bisect: wrong, of accusations made | nobody named | 10% (10 of 100) |" in table_markdown({"cells": rows})


def test_a_voided_replay_is_never_evidence():
    from whodunit.lineup import VOID

    calls = {"n": 0}
    inner = flaky(12, 1.0, seed=3)  # a bug that fails every time, so only the voids could send this wrong

    def trial(position):
        calls["n"] += 1
        return VOID if calls["n"] % 3 == 0 else inner(position)  # every third replay hits a provider error
    found = statistical_bisect(20, trial, budget=200)
    judged = [verdict for _, verdict in found.tested if verdict in (PASS, FAIL)]
    assert found.culprit == 12 and found.replays == len(judged) < calls["n"]


def test_the_lineup_stops_when_the_provider_keeps_failing():
    from whodunit.lineup import VOID

    calls = []

    def trial(position):
        calls.append(position)
        return VOID
    found = statistical_bisect(20, trial, budget=200)
    assert found.culprit is None and "kept failing" in found.note and found.replays == 0
    assert len(calls) < 60  # it gives up, and does not spin


def test_when_the_good_ref_fails_as_often_as_the_bad_one_no_commit_is_named():
    # Something outside the repo changed, and every commit fails now, the good ref included.
    calls = []

    def trial(position):
        calls.append(position)
        return FAIL
    found = statistical_bisect(20, trial, budget=120)
    assert found.culprit is None and found.clear and "no commit in this range did it" in found.note
    assert set(calls) == {-1, 19} and len(calls) <= 14  # it stops at the two ends, and soon


def test_a_drift_that_fails_a_third_of_the_time_everywhere_is_not_pinned_on_a_commit():
    import random

    named = clear = 0
    for seed in range(40):
        rng = random.Random(seed)
        found = statistical_bisect(20, lambda position: FAIL if rng.random() < 0.33 else PASS, budget=160)
        named += found.culprit is not None
        clear += found.clear
    assert clear >= 20 and named <= 4  # mostly it says the range is clear, and it seldom accuses anyone


def test_a_real_regression_is_not_mistaken_for_a_clear_range():
    for seed in range(30):
        found = statistical_bisect(20, flaky(12, 0.6, seed=seed), budget=200)
        assert not found.clear


def stepped(first, second, low, high, seed=0):
    """Two regressions: from `first` the case fails at `low`, and from `second` at `high`."""
    rng = random.Random(seed)

    def trial(position):
        rate = high if position >= second else low if position >= first else 0.0
        return FAIL if rng.random() < rate else PASS
    return trial


def test_two_change_points_have_an_exact_posterior():
    from whodunit.lineup import OneOrTwo

    state = OneOrTwo(6)
    for position, fails, passes in ((-1, 0, 8), (0, 0, 8), (1, 0, 8), (2, 4, 4), (3, 4, 4), (4, 8, 0), (5, 8, 0)):
        for _ in range(fails):
            state.observe(position, True)
        for _ in range(passes):
            state.observe(position, False)
    weights = state.weights()
    assert abs(sum(weights) - 1) < 1e-9 and len(weights) == 6 + 15
    best = max(range(len(weights)), key=weights.__getitem__)
    assert state.hypotheses[best] == (2, 4) and weights[best] > 0.9  # clean, then half, then always: two changes, at 2 and at 4
    plain = OneOrTwo(6)
    for position, fails, passes in ((-1, 0, 8), (0, 0, 8), (1, 0, 8), (2, 8, 0), (3, 8, 0), (4, 8, 0), (5, 8, 0)):
        for _ in range(fails):
            plain.observe(position, True)
        for _ in range(passes):
            plain.observe(position, False)
    weights = plain.weights()
    assert plain.hypotheses[max(range(len(weights)), key=weights.__getitem__)] == (2,)  # one step is one change, and the pairs do not steal it
    assert sum(weights[6:]) < 0.2


def test_the_joint_lineup_names_both_culprits_or_the_one_there_is():
    from whodunit.lineup import one_or_two_bisect

    both = one_or_two_bisect(12, stepped(4, 9, 0.4, 1.0, seed=2), budget=300)
    assert both.culprits == (4, 9) and both.two > 0.95 and both.bayes_factor > 19
    one = one_or_two_bisect(12, flaky(7, 1.0, seed=2), budget=300)
    assert one.culprits == (7,) and one.two < 0.5 and one.replays < 100  # one culprit, named without waiting to rule every pair out

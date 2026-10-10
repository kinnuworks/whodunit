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

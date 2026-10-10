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

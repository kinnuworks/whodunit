"""The lineup: narrowing the suspects down to one commit.

For now this holds plain bisect, which is right when the bug fails every time. It is also the
baseline the statistical bisect gets compared against.
"""

from dataclasses import dataclass, field
from typing import Callable

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass
class Lineup:
    culprit: int | None  # index into the suspects, or None if skips left more than one
    remaining: list[int]  # the suspects that could still be the first bad commit
    tested: list[tuple[int, str]] = field(default_factory=list)  # (index, verdict) in the order they ran


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


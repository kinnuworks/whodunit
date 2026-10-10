import random

from whodunit.onset import find_onset


def make_traffic(commits=12, culprit=8, per_commit=15, bad_rate=0.4, good_rate=0.0, seed=1):
    rng = random.Random(seed)
    runs, clock = [], 1_000_000.0
    for n in range(commits):
        for _ in range(per_commit):
            clock += 60_000
            bad = rng.random() < (bad_rate if n >= culprit else good_rate)
            runs.append({"commit": f"{n:040d}", "started_ms": clock, "bad": bad, "input_preview": f"refund order {rng.choice([1001, 1002])}"})
    return runs


def test_onset_brackets_the_culprit_from_traffic_alone():
    runs = make_traffic()
    onset = find_onset("refund-agent", runs)
    shas = [c["sha"] for c in onset.commits]
    assert onset.bad == shas[-1]
    assert shas.index(onset.good) < 8  # the good ref is before the culprit
    assert shas.index(onset.good) >= 5  # and traffic has already cleared the early commits
    assert onset.likeliest == shas[8] and onset.probability > 0.5
    first_bad = next(r for r in runs if r["bad"])
    assert onset.first_failure_ms == first_bad["started_ms"]
    assert set(onset.failing_inputs) <= {"refund order 1001", "refund order 1002"} and onset.failing_inputs


def test_a_stray_failure_on_a_good_commit_does_not_move_the_onset():
    runs = make_traffic(good_rate=0.0)
    runs[20]["bad"] = True  # one flake at commit 1
    onset = find_onset("refund-agent", runs)
    shas = [c["sha"] for c in onset.commits]
    assert onset.likeliest == shas[8]
    assert onset.first_failure_ms > runs[20]["started_ms"]


def test_no_failures_and_single_commit_are_reported():
    quiet = find_onset("refund-agent", make_traffic(bad_rate=0.0))
    assert quiet.good is None and "No bad runs" in quiet.note
    one = find_onset("refund-agent", make_traffic(commits=1, culprit=0))
    assert "two commits" in one.note

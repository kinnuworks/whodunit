import json
import subprocess

import pytest

from tests.planted import refund_agent_history, shop_history, stub_history
from whodunit.case import Case, CaseInput, judge, last_json_line
from whodunit.cli import main
from whodunit.lineup import plain_bisect
from whodunit.replay import FAIL, PASS, SKIP, Runner
from whodunit.suspects import list_suspects


def test_last_json_line_ignores_log_noise():
    out = 'warming up\n{"refunds": []}\n2026-10-10 - neatlogs - INFO - shutdown complete\n'
    assert last_json_line(out) == {"refunds": []}
    assert last_json_line("no json here") is None


def test_refund_check_compares_amounts(tmp_path):
    case = Case(id="c", symptom="s", good="a", bad="b", inputs=())
    want = CaseInput("refund 1001", {"refunds": [{"order_id": "1001", "refunded": 42.0}]})
    assert judge(case, want, '{"refunds": [{"order_id": "1001", "refunded": 42}]}', tmp_path)[0]
    assert not judge(case, want, '{"refunds": [{"order_id": "1001", "refunded": 46.2}]}', tmp_path)[0]
    assert not judge(case, want, '{"refunds": []}', tmp_path)[0]
    assert not judge(case, want, "Traceback", tmp_path)[0]


def test_suspects_are_oldest_first_with_priors(tmp_path):
    made = stub_history(tmp_path / "repo")
    case = Case.load(made["case"])
    suspects = list_suspects(made["repo"], case.good, case.bad, case.target)
    assert [s.sha for s in suspects] == made["shas"][1:]
    assert suspects[3].subject == "Update the notes (4)"
    assert not suspects[3].touches_target and suspects[3].prior < suspects[0].prior
    assert suspects[12].touches_target
    assert all(s.checkpoint is None for s in suspects)


def test_checkpoint_trailer_is_read(tmp_path):
    made = stub_history(tmp_path / "repo", suspects=2, culprit=2)
    subprocess.run(
        ["git", "-C", str(made["repo"]), "-c", "user.name=P", "-c", "user.email=p@example.invalid", "commit", "-q", "--allow-empty",
         "-m", "Friendlier replies\n\nEntire-Checkpoint: abc123def456"], check=True,
    )
    suspects = list_suspects(made["repo"], made["shas"][0], "HEAD", "agent")
    assert suspects[-1].checkpoint == "abc123def456"


def test_plain_bisect_over_worktrees_finds_the_planted_commit(tmp_path):
    made = stub_history(tmp_path / "repo", suspects=20, culprit=13, broken=(6, 10))
    case = Case.load(made["case"])
    suspects = list_suspects(made["repo"], case.good, case.bad, case.target)
    with Runner(made["repo"], case) as runner:
        assert runner.test_commit(case.good)[0] == PASS
        assert runner.test_commit(case.bad)[0] == FAIL
        assert runner.test_commit(made["shas"][6])[0] == SKIP
        found = plain_bisect(len(suspects), lambda i: runner.test_commit(suspects[i].sha)[0])
        tags = {r.sha for r in runner.replays}
    assert suspects[found.culprit].sha == made["culprit"]
    assert suspects[found.culprit].subject == "Add a goodwill bonus to refunds"
    assert len(tags) < 10  # far fewer commits than the 20 suspects
    assert not (made["repo"] / ".whodunit" / "worktrees").exists() or not any((made["repo"] / ".whodunit" / "worktrees").iterdir())


def test_cli_names_the_culprit(tmp_path, capsys):
    made = stub_history(tmp_path / "repo", suspects=20, culprit=5)
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--method", "plain", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["culprit"]["sha"] == made["culprit"]
    assert report["suspects"] == 20 and report["linear_scan_commits"] == 5


def test_cli_refuses_a_case_whose_bad_ref_passes(tmp_path, capsys):
    made = stub_history(tmp_path / "repo", suspects=6, culprit=99)
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--method", "plain"]) == 2
    assert "does not fail" in capsys.readouterr().out


def test_cli_statistical_names_the_culprit_with_a_probability(tmp_path, capsys):
    made = stub_history(tmp_path / "repo", suspects=12, culprit=5, broken=(3,))
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "60", "--parallel", "3", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["culprit"]["sha"] == made["culprit"]
    assert report["culprit"]["probability"] >= 0.95
    assert report["replays"] <= 60 and report["failure_rate_from"] > 0.8


def test_cli_statistical_says_so_when_the_bad_ref_never_fails(tmp_path, capsys):
    made = stub_history(tmp_path / "repo", suspects=6, culprit=99)
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "40"]) == 1
    assert "the bad ref passed all" in capsys.readouterr().out


def test_a_timeout_stops_the_agent_and_its_children(tmp_path):
    import sys
    import time

    from whodunit.replay import run_command

    marker = tmp_path / "still-alive"
    child = f"import time, pathlib; time.sleep(3); pathlib.Path({str(marker)!r}).write_text('x')"
    parent = f"import subprocess, sys; subprocess.run([sys.executable, '-c', {child!r}])"
    with pytest.raises(subprocess.TimeoutExpired):
        run_command([sys.executable, "-c", parent], tmp_path, {}, timeout=1)
    time.sleep(4)
    assert not marker.exists()


@pytest.mark.slow
def test_real_refund_agent_across_20_commits(tmp_path):
    """The milestone 2 run: the real agent, a scripted model, 20 suspects, one of which will not build."""
    import socket
    import sys
    import time

    from tests.planted import VICTIM, VICTIM_BASE

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    fake_llm = tmp_path / "fake_llm.py"
    fake_llm.write_text(subprocess.run(["git", "-C", str(VICTIM), "show", f"{VICTIM_BASE}:victims/refund-agent/fake_llm.py"], capture_output=True, text=True, check=True).stdout)
    fake = subprocess.Popen([sys.executable, str(fake_llm), str(port), str(tmp_path / "requests.jsonl")])
    try:
        time.sleep(0.5)
        made = refund_agent_history(tmp_path / "repo", fake_llm_port=port)
        case = Case.load(made["case"])
        suspects = list_suspects(made["repo"], case.good, case.bad, case.target)
        with Runner(made["repo"], case) as runner:
            assert runner.test_commit(case.good)[0] == PASS
            assert runner.test_commit(made["broken"])[0] == SKIP
            found = plain_bisect(len(suspects), lambda i: runner.test_commit(suspects[i].sha)[0])
        assert suspects[found.culprit].sha == made["culprit"]
    finally:
        fake.terminate()


def outage(tmp_path, commit, count, what):
    """The environment that makes the stub agent fail or hang for its first `count` runs at one commit."""
    return {"STUB_OUTAGE": f"{commit[:12]}|{count}|{tmp_path / 'outage-count'}|{what}"}


def with_env(case, env, **changes):
    import dataclasses

    return dataclasses.replace(case, env={**case.env, **env}, **changes)


def test_a_provider_error_is_voided_and_run_again(tmp_path):
    from whodunit.replay import VOID

    made = stub_history(tmp_path / "repo", suspects=3, culprit=3)
    innocent = made["shas"][1]
    for what in ("exit 75", "exit 1"):  # the agent's own exit code, and an older agent that only leaves a traceback
        (tmp_path / "outage-count").unlink(missing_ok=True)
        case = with_env(Case.load(made["case"]), outage(tmp_path, innocent, 2, what))
        with Runner(made["repo"], case) as runner:
            runner.void_waits = (0.0, 0.0)
            result = runner.replay(innocent, case.inputs[0])
        assert (result.verdict, result.voided) == (PASS, 2), what  # two attempts hit the outage, the third was judged
    (tmp_path / "outage-count").unlink()
    case = with_env(Case.load(made["case"]), outage(tmp_path, innocent, 99, "exit 75"))
    with Runner(made["repo"], case) as runner:
        runner.void_waits = (0.0, 0.0)
        result = runner.replay(innocent, case.inputs[0])
    assert result.verdict == VOID and result.voided == 3 and "provider" in result.reason
    # An exit the case does not list is the agent's own failure, as before.
    (tmp_path / "outage-count").unlink()
    case = with_env(Case.load(made["case"]), outage(tmp_path, innocent, 99, "exit 3"), void_stderr=())
    with Runner(made["repo"], case) as runner:
        assert runner.replay(innocent, case.inputs[0]).verdict == FAIL


def test_a_timeout_gets_one_more_try_with_double_the_limit(tmp_path):
    made = stub_history(tmp_path / "repo", suspects=3, culprit=3)
    slow_once = with_env(Case.load(made["case"]), outage(tmp_path, made["shas"][1], 1, "sleep 4"), timeout=1.5)
    with Runner(made["repo"], slow_once) as runner:
        result = runner.replay(made["shas"][1], slow_once.inputs[0])
    assert (result.verdict, result.timeouts) == (PASS, 1)  # a slow moment on the machine, and no evidence against the commit
    (tmp_path / "outage-count").unlink()
    hangs = with_env(Case.load(made["case"]), outage(tmp_path, made["shas"][1], 99, "sleep 30"), timeout=1.0)
    with Runner(made["repo"], hangs) as runner:
        result = runner.replay(made["shas"][1], hangs.inputs[0])
    assert (result.verdict, result.timeouts) == (FAIL, 2) and "timed out twice" in result.reason  # a commit that hangs is a real bug


def test_a_burst_of_provider_errors_does_not_frame_a_commit(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("whodunit.replay.VOID_WAITS", (0.0, 0.0))  # no need to wait out an outage that is made up
    # The provider goes down for six runs just after the warm-up, whichever commit is being replayed then.
    # Before voiding, those six counted as failures and the lineup named an innocent commit at 95%.
    made = stub_history(tmp_path / "repo", suspects=12, culprit=11)
    made["case"].write_text(made["case"].read_text() + f'''
[env]
STUB_OUTAGE = "|12+6|{tmp_path / "outage-count"}|exit 1"
''')
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "60", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["culprit"]["sha"] == made["culprit"]
    record = json.loads(made["case"].with_name("case.record.json").read_text())
    assert report["voided"] == sum(r["voided"] for r in record["replays"]) == 6
    assert all(r["verdict"] != "fail" for r in record["replays"] if r["sha"] != made["culprit"] and r["sha"] != made["shas"][-1])


def test_inputs_that_point_at_different_commits_are_flagged(tmp_path, capsys):
    # Two regressions in one range. Suspect 4 overpays order 1001 and suspect 9 refunds order 2002 to a stranger.
    # A single change point cannot describe that, and the case's two inputs say so between them.
    made = shop_history(tmp_path / "repo", suspects=12, culprit=9, bonus_at=4)
    main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "120", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert len(report["per_input"]) == 2 and all(one["failures"] > 0 for one in report["per_input"])
    split = report["inputs_disagree"]
    assert split["same"] <= 0.05 and made["bonus"] in split["commits"] and len(set(split["commits"])) == 2
    by_input = {one["input"]: one for one in report["per_input"]}
    assert by_input["Please refund order 1001 for customer cust_9."]["top"] == made["bonus"]
    page_record = json.loads(made["case"].with_name("case.record.json").read_text())
    from whodunit import casefile
    assert "point at different commits" in casefile.render(page_record)


def test_inputs_that_agree_are_not_flagged(tmp_path, capsys):
    made = shop_history(tmp_path / "repo", suspects=10, culprit=6)
    assert main(["lineup", str(made["case"]), "--repo", str(made["repo"]), "--budget", "80", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "inputs_disagree" not in report and len(report["per_input"]) == 1

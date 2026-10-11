from datetime import datetime, timezone

from whodunit.motive import checkpoint_link, find_motive, read_transcript
from tests.planted import git, stub_history


def at(minute):
    return f"2026-10-10T12:{minute:02d}:00.000Z"


def prompt(minute, text, **extra):
    return {"type": "user", "uuid": f"u{minute:07d}", "timestamp": at(minute), "message": {"content": text}, **extra}


def assistant(minute, *blocks):
    return {"type": "assistant", "uuid": f"a{minute:07d}", "timestamp": at(minute), "message": {"content": list(blocks)}}


def said(text):
    return {"type": "text", "text": text}


def tool(name, **given):
    return {"type": "tool_use", "name": name, "input": given}


ENTRIES = [
    prompt(1, "Add an order export"),
    assistant(2, said("Adding the export."), tool("Edit", file_path="/repo/agent/export.py", new_string="def export(): ...")),
    prompt(10, "Make the replies friendlier"),
    {"type": "user", "uuid": "meta", "timestamp": at(11), "isMeta": True, "message": {"content": [{"type": "text", "text": "Base directory for this skill"}]}},
    {"type": "user", "uuid": "tool", "timestamp": at(12), "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
    assistant(13, said("I will soften the system prompt."), tool("Read", file_path="/repo/agent/agent.py")),
    assistant(14, tool("Edit", file_path="/repo/agent/agent.py", new_string="Be warm and generous."), tool("Edit", file_path="/repo/notes.md", new_string="x")),
    assistant(15, tool("Bash", command="git commit -m friendlier", description="Commit the change")),
    prompt(30, "Now add a changelog"),
    assistant(31, said("Writing the changelog.")),
]


def test_request_is_the_last_prompt_before_the_commit():
    found = read_transcript(ENTRIES, datetime(2026, 10, 10, 12, 16, tzinfo=timezone.utc), {"agent/agent.py"})
    assert found["request"] == "Make the replies friendlier"
    assert found["earlier_requests"] == ["Add an order export"]
    kinds = [(s.kind, s.file) for s in found["steps"]]
    assert kinds == [("said", None), ("read", "agent/agent.py"), ("edited", "agent/agent.py"), ("ran", None)]
    assert found["steps"][2].text == "Be warm and generous."
    assert all(s.id for s in found["steps"])


def test_injected_context_and_tool_results_are_not_requests():
    found = read_transcript(ENTRIES, datetime(2026, 10, 10, 12, 12, 30, tzinfo=timezone.utc), set())
    assert found["request"] == "Make the replies friendlier"


def test_no_prompt_before_the_commit():
    found = read_transcript(ENTRIES, datetime(2026, 10, 10, 11, 0, tzinfo=timezone.utc), set())
    assert found["request"] is None


def test_commit_without_a_checkpoint_says_so(tmp_path):
    made = stub_history(tmp_path / "repo", suspects=2, culprit=1)
    motive = find_motive(made["repo"], made["culprit"])
    assert motive.checkpoint is None and motive.request is None
    assert "no Entire checkpoint" in motive.note
    assert checkpoint_link(made["repo"], made["culprit"]) is None


def test_the_checkpoint_link_is_worked_out_when_the_page_is_drawn(tmp_path, monkeypatch):
    import json
    import subprocess

    from whodunit.cli import main

    made = stub_history(tmp_path / "repo", suspects=2, culprit=1)
    record_file = tmp_path / "c.record.json"
    record = {"case": {"id": "c", "repo": str(made["repo"])}, "suspects": [],
              "motive": {"sha": made["culprit"], "subject": "s", "checkpoint": "abc123def456", "request": "Make it friendlier", "request_time": "2026-10-10T12:00:00+00:00"}}
    record_file.write_text(json.dumps(record))
    monkeypatch.chdir(tmp_path)
    assert main(["open-case", "c.toml", "--record", str(record_file), "--no-open"]) == 0
    assert "entire.io" not in (tmp_path / "c.casefile.html").read_text()  # no remote yet, so no link, and none is made up
    subprocess.run(["git", "-C", str(made["repo"]), "remote", "add", "origin", "git@github.com:someone/whodunit.git"], check=True)
    assert main(["open-case", "c.toml", "--record", str(record_file), "--no-open"]) == 0
    assert f'https://entire.io/gh/someone/whodunit/commit/{made["culprit"]}' in (tmp_path / "c.casefile.html").read_text()
    assert "link" not in json.loads(record_file.read_text())["motive"]  # the record is not touched, so it cannot go stale


def test_a_quote_is_checked_against_the_transcript():
    from whodunit.motive import quoted_verbatim

    assert quoted_verbatim("Make the replies friendlier", ENTRIES)
    assert quoted_verbatim("Make the  replies\nfriendlier", ENTRIES)  # line breaks and runs of spaces do not count as changes
    assert not quoted_verbatim("Make the replies much friendlier", ENTRIES)
    assert not quoted_verbatim("Base directory for this skill", ENTRIES)  # injected context is in the transcript, and nobody typed it
    scrubbed = [prompt(1, "Tidy /Users/someone/project/agent.py please")]
    assert not quoted_verbatim("Tidy agent.py please", scrubbed)  # a path was removed for the page, so the quote is no longer word for word
    assert not quoted_verbatim("", ENTRIES)


def test_the_lines_a_commit_changed_are_read_from_its_diff(tmp_path):
    from whodunit.motive import changed_lines

    made = stub_history(tmp_path / "repo", suspects=3, culprit=2)
    lines = changed_lines(made["repo"], made["culprit"])
    assert lines and all(name == "agent/agent.py" for name, _ in lines)
    source = git(made["repo"], "show", f"{made['culprit']}:agent/agent.py").split("\n")
    assert any(source[number - 1] == "BONUS = 5" for _, number in lines)  # the line the culprit wrote, by its number after the commit


def test_line_level_provenance_agrees_or_says_where_it_does_not(tmp_path, monkeypatch):
    import json

    from whodunit import motive

    made = stub_history(tmp_path / "repo", suspects=3, culprit=2)
    asked = []

    def why(repo, *args):
        if args[0] != "why":
            return None
        asked.append(args[1])
        line = int(args[1].rsplit(":", 1)[1])
        other = line % 2 == 0 and why.split
        return json.dumps({"line": {"line_number": line, "commit_sha": "d" * 40 if other else made["culprit"], "checkpoint_id": "ffff00001111" if other else "abc123def456",
                                    "prompt": "Add a goodwill bonus"}})
    why.split = False
    monkeypatch.setattr(motive, "entire", why)
    found = motive.line_provenance(made["repo"], made["culprit"], "abc123def456", "Add a goodwill bonus\nto refunds")
    assert found["lines"] == len(asked) >= 1 and found["agree"] == found["lines"] and found["disagree"] == [] and found["request_agrees"]
    assert all(target.startswith("agent/agent.py:") for target in asked)
    assert not (made["repo"] / ".whodunit" / "why").exists() or not any((made["repo"] / ".whodunit" / "why").iterdir())  # the checkout it made is gone
    why.split = True
    asked.clear()
    monkeypatch.setattr(motive, "changed_lines", lambda repo, sha, limit=12: [("agent/agent.py", 2), ("agent/agent.py", 3)])
    mixed = motive.line_provenance(made["repo"], made["culprit"], "abc123def456", "Add a goodwill bonus")
    assert (mixed["lines"], mixed["agree"]) == (2, 1) and mixed["disagree"] == [{"file": "agent/agent.py", "line": 2, "commit": "d" * 12, "checkpoint": "ffff00001111"}]
    monkeypatch.setattr(motive, "entire", lambda repo, *args: None)
    assert "could not be asked" in motive.line_provenance(made["repo"], made["culprit"], "abc123def456", "x")["note"]


def test_the_page_says_the_quote_was_checked_only_when_it_was():
    from whodunit import casefile

    record = {"case": {"id": "c"}, "suspects": [], "motive": {"sha": "c" * 40, "subject": "s", "checkpoint": "abc123def456", "request": "Make it friendlier",
                                                             "request_time": "2026-10-10T12:00:00+00:00"}}
    assert "quote checked against the transcript" not in casefile.render(record).lower()
    record["motive"]["quote_checked"] = True
    record["motive"]["provenance"] = {"lines": 4, "agree": 4, "disagree": [], "request_agrees": True, "note": ""}
    page = casefile.render(record)
    assert "Quote checked against the transcript." in page and "all 4 changed lines" in page
    record["motive"]["quote_checked"] = False
    record["motive"]["provenance"] = {"lines": 4, "agree": 3, "disagree": [{"file": "agent.py", "line": 9, "commit": "d" * 12, "checkpoint": "ffff00001111"}], "request_agrees": True, "note": ""}
    page = casefile.render(record)
    assert "Quote checked against the transcript." not in page and "3 of the 4 changed lines" in page and "agent.py:9" in page


def test_the_session_that_ran_the_commit_is_the_one_whose_request_is_quoted():
    # Two sessions in one checkpoint edited the same file. The first was a dropped attempt: it edited, tried to
    # commit and was put back. The second, reworded, made the commit. Scoring by edits and by "ran something
    # called commit" picked the dropped one, and its request was quoted as the motive of a commit it never made.
    from whodunit.motive import made_the_commit, pick_session

    sha, subject = "d4fb1587c0664b1d6c7bd482028ba9c26eba9adb", "Try digit-swap and digit-double corrections on order lookup misses"
    made_at = datetime(2026, 10, 10, 12, 20, 52, tzinfo=timezone.utc)  # git keeps whole seconds
    dropped = [
        prompt(15, "Support keeps seeing customers mistype their order number. Can you change the system prompt?"),
        assistant(16, tool("Edit", file_path="/repo/agent/agent.py", new_string="try variations")),
        assistant(17, tool("Bash", command="git add agent.py && git commit -m 'Guess mistyped order numbers'", description="Stage and commit")),
    ]
    kept = [
        prompt(18, "Customers often mistype order numbers. Add a rule: try a few likely corrections."),
        assistant(19, tool("Edit", file_path="/repo/agent/agent.py", new_string="digit-swap")),
        # The commit command is issued a few milliseconds into the second git records, so it looks later than the commit.
        {"type": "assistant", "uuid": "a0000020", "timestamp": "2026-10-10T12:20:52.019Z",
         "message": {"content": [tool("Bash", command=f'git commit -m "{subject}"', description="Create the commit")]}},
        {"type": "user", "uuid": "t0000020", "timestamp": "2026-10-10T12:20:52.400Z",
         "message": {"content": [{"type": "tool_result", "content": f"[main {sha[:7]}] {subject}\n 1 file changed"}]}},
    ]
    assert made_the_commit(kept, sha, subject) and not made_the_commit(dropped, sha, subject)
    for order in ([dropped, kept], [kept, dropped]):
        chosen, found, why = pick_session(order, made_at, {"agent/agent.py"}, sha, subject)
        assert order[chosen] is kept and found["request"].startswith("Customers often mistype") and "ran the commit" in why
    # With nothing to say who committed, the session that edited the commit's files is still preferred.
    chosen, found, why = pick_session([[prompt(1, "Write a changelog")], dropped], made_at, {"agent/agent.py"}, "e" * 40, "Some other subject")
    assert chosen == 1 and "edited" in why

from datetime import datetime, timezone

from whodunit.motive import checkpoint_link, find_motive, read_transcript
from tests.planted import stub_history


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

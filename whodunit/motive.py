"""The motive: what was the culprit commit asked to do?

Entire keeps a checkpoint for a commit that followed coding-agent work, with the session
transcript behind it. This module finds the request that led to the commit and the part of
the session where the agent worked on it.
"""

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .suspects import git

MAX_TEXT = 1200  # characters kept from any one transcript entry


@dataclass
class Step:
    """One thing the coding agent said or did between the request and the commit."""

    id: str  # transcript entry id, shortened, so a brief can cite it
    kind: str  # said, edited, ran or read
    text: str
    file: str | None = None


@dataclass
class Motive:
    sha: str
    subject: str
    checkpoint: str | None = None
    session: str | None = None
    agent: str | None = None
    model: str | None = None
    request: str | None = None  # the prompt that led to the commit
    message: str = ""  # the commit message body, which is all there is when no session can be read
    request_id: str | None = None
    request_time: str | None = None
    earlier_requests: list[str] = field(default_factory=list)  # prompts before it in the same session, oldest first
    steps: list[Step] = field(default_factory=list)
    link: str | None = None
    note: str = ""  # why something is missing

    def to_dict(self) -> dict:
        return asdict(self)


def entire(repo: str | Path, *args: str) -> str | None:
    """Run the Entire CLI. Returns None if it is not installed or the call fails."""
    try:
        done = subprocess.run(["entire", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def checkpoint_link(repo: str | Path, sha: str) -> str | None:
    """https://entire.io/gh/OWNER/REPO/commit/FULL_SHA, if the repo has a GitHub remote."""
    try:
        url = git(repo, "remote", "get-url", "origin").strip()
    except RuntimeError:
        return None
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    return f"https://entire.io/gh/{match.group(1)}/{match.group(2)}/commit/{sha}" if match else None


def _when(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _prompt_text(entry: dict) -> str | None:
    """The text of a prompt a person typed, or None for tool results and injected context."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list) and not any(b.get("type") == "tool_result" for b in content):
        text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
        return text or None
    return None


def _steps(entry: dict, files: set[str]) -> list[Step]:
    """What an assistant entry said and did. Edits and reads are kept only for files in the commit."""
    out = []
    entry_id = (entry.get("uuid") or "")[:8]
    for block in entry.get("message", {}).get("content", []) or []:
        if block.get("type") == "text" and block.get("text", "").strip():
            out.append(Step(entry_id, "said", block["text"].strip()[:MAX_TEXT]))
        elif block.get("type") == "tool_use":
            name, given = block.get("name", ""), block.get("input", {}) or {}
            path = given.get("file_path") or ""
            touched = next((f for f in files if path.endswith(f)), None)
            if name in ("Edit", "Write", "NotebookEdit") and touched:
                change = given.get("new_string") or given.get("content") or ""
                out.append(Step(entry_id, "edited", change[:MAX_TEXT], touched))
            elif name == "Read" and touched:
                out.append(Step(entry_id, "read", touched, touched))
            elif name == "Bash" and (given.get("description") or given.get("command")):
                out.append(Step(entry_id, "ran", (given.get("description") or given["command"])[:300]))
    return out


def read_transcript(entries: list[dict], commit_time: datetime, files: set[str], max_steps: int = 40) -> dict:
    """Find the request behind a commit made at `commit_time`, and what the agent did about it.

    The request is the last prompt a person typed before the commit. A checkpoint can cover
    several commits from one long turn, so the commit time is what ties a prompt to a commit.
    """
    prompts = []
    for entry in entries:
        text, at = _prompt_text(entry), _when(entry.get("timestamp"))
        if text and at and at <= commit_time:
            prompts.append((at, text, (entry.get("uuid") or "")[:8]))
    if not prompts:
        return {"request": None, "earlier_requests": [], "steps": []}
    asked_at, request, request_id = prompts[-1]
    steps = []
    for entry in entries:
        at = _when(entry.get("timestamp"))
        if entry.get("type") == "assistant" and not entry.get("isSidechain") and at and asked_at <= at <= commit_time:
            steps += _steps(entry, files)
    # Keep everything that touched the commit's files, and fill the rest with what was said most recently.
    keep = [s for s in steps if s.file][-max_steps:]
    rest = [s for s in steps if not s.file][-max(0, max_steps - len(keep)):]
    order = {id(s): n for n, s in enumerate(steps)}
    chosen = sorted(keep + rest, key=lambda s: order[id(s)])
    return {
        "request": request, "request_id": request_id, "request_time": asked_at.isoformat(),
        "earlier_requests": [text for _, text, _ in prompts[:-1]][-5:], "steps": chosen,
    }


def find_motive(repo: str | Path, sha: str) -> Motive:
    """Everything Entire knows about why this commit was made."""
    full, subject, stamp, trailer = git(
        repo, "show", "-s", "--format=%H%x00%s%x00%cI%x00%(trailers:key=Entire-Checkpoint,valueonly,separator=%x20)", sha
    ).strip().split("\x00")
    body = git(repo, "show", "-s", "--format=%b", full)
    body = "\n".join(line for line in body.splitlines() if not re.match(r"^[A-Za-z-]+: ", line)).strip()  # drop trailers
    motive = Motive(sha=full, subject=subject, link=checkpoint_link(repo, full), message=body)
    if not trailer.strip():
        motive.note = "This commit has no Entire checkpoint, so there is no recorded request behind it."
        return motive
    motive.checkpoint = trailer.split()[0]
    meta = entire(repo, "checkpoint", "explain", "--checkpoint", motive.checkpoint, "--json")
    if meta is None:
        motive.note = f"The commit names Entire checkpoint {motive.checkpoint}, and Entire cannot find it, so the request behind this commit is not on record."
        return motive
    sessions = json.loads(meta).get("sessions") or [{}]
    motive.session, motive.agent, motive.model = (sessions[0].get(k) for k in ("session_id", "agent", "model"))
    raw = entire(repo, "checkpoint", "explain", "--checkpoint", motive.checkpoint, "--raw-transcript")
    if not raw:
        motive.note = "The checkpoint has no transcript."
        return motive
    entries = []
    for line in raw.splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    files = {f for f in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", full).split("\n") if f}
    found = read_transcript(entries, datetime.fromisoformat(stamp).astimezone(timezone.utc), files)
    if found["request"] is None:
        motive.note = "The transcript has no prompt from before this commit."
        return motive
    for key, value in found.items():
        setattr(motive, key, value)
    # A session transcript is full of absolute paths. The case file is public, so they go.
    here, home = str(Path(repo).resolve()), str(Path.home())

    def scrub(text: str) -> str:
        return text.replace(here + "/", "").replace(here, ".").replace(home, "~")

    motive.request = scrub(motive.request)
    motive.earlier_requests = [scrub(t) for t in motive.earlier_requests]
    for step in motive.steps:
        step.text = scrub(step.text)
    return motive

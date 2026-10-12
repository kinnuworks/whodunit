"""The motive: what was the culprit commit asked to do?

Entire keeps a checkpoint for a commit that followed coding-agent work, with the session
transcript behind it. This module finds the request that led to the commit and the part of
the session where the agent worked on it.

Two things are then checked before anything is quoted. The request has to be word for word in
the transcript. And `entire why`, asked about each line the commit changed, has to name the
same commit and the same checkpoint.
"""

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
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
    request: str | None = None  # the prompt that led to the commit
    message: str = ""  # the commit message body, which is all there is when no session can be read
    request_id: str | None = None
    request_time: str | None = None
    earlier_requests: list[str] = field(default_factory=list)  # prompts before it in the same session, oldest first
    steps: list[Step] = field(default_factory=list)
    note: str = ""  # why something is missing
    quote_checked: bool = False  # the request as shown is word for word in the session transcript, as something a person typed
    provenance: dict = field(default_factory=dict)  # what `entire why` says about the lines the commit changed; see line_provenance

    def to_dict(self) -> dict:
        return asdict(self)


def entire(repo: str | Path, *args: str) -> str | None:
    """Run the Entire CLI. Returns None if it is not installed or the call fails."""
    try:
        done = subprocess.run(["entire", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def remote_of(repo: str | Path) -> str:
    """The address of the repo's origin, or nothing if it has none."""
    try:
        return git(repo, "remote", "get-url", "origin").strip()
    except RuntimeError:
        return ""


def checkpoint_link(repo: str | Path, sha: str, remote: str = "") -> str | None:
    """https://entire.io/gh/OWNER/REPO/commit/FULL_SHA, if the repo has a GitHub remote.

    This is asked for when a page is drawn and is not kept in the record. A record written
    before the repo had a remote would otherwise carry an empty link for good. A record of a
    case in somebody else's repo keeps that repo's address as `remote`, because the clone it
    was run in may be gone by the time the page is drawn.
    """
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote or remote_of(repo))
    return f"https://entire.io/gh/{match.group(1)}/{match.group(2)}/commit/{sha}" if match else None


def quoted_verbatim(request: str | None, entries: list[dict]) -> bool:
    """Is the request, as it will be shown, word for word in the transcript as something a person typed?

    Line breaks and runs of spaces are not counted as differences. Anything else is: a request
    that had a path removed for the page, or was cut short, is no longer a quotation, and the
    page must not say it was checked.
    """
    shown = " ".join((request or "").split())
    if not shown:
        return False
    return any(shown in " ".join(text.split()) for text in (_prompt_text(entry) for entry in entries) if text)


def changed_lines(repo: str | Path, sha: str, limit: int = 12) -> list[tuple[str, int]]:
    """(file, line number after the commit) for lines the commit added or rewrote, at most `limit` of them.

    Lines are taken from every hunk in turn, so a commit with many hunks is sampled across all of them.
    """
    hunks: list[list[tuple[str, int]]] = []
    name = None
    for line in git(repo, "show", "--format=", "--unified=0", sha).splitlines():
        if line.startswith("+++ "):
            name = None if line.endswith("/dev/null") else line[6:]
        elif line.startswith("@@") and name:
            found = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            start, count = int(found.group(1)), int(found.group(2) or 1)
            if count:
                hunks.append([(name, n) for n in range(start, start + count)])
    out: list[tuple[str, int]] = []
    while hunks and len(out) < limit:
        for hunk in list(hunks):
            if hunk and len(out) < limit:
                out.append(hunk.pop(0))
            if not hunk:
                hunks.remove(hunk)
    return out


def line_provenance(repo: str | Path, sha: str, checkpoint: str, request: str | None, session: str | None = None) -> dict:
    """Ask `entire why` about the lines the commit changed, and see that it agrees with the checkpoint.

    The motive is found from the commit's checkpoint trailer and its session. This asks the
    same question a second way, line by line: which commit and which checkpoint does Entire put
    behind each changed line? It is asked in a checkout of the commit itself, which is removed
    afterwards. Returns {"lines", "agree", "disagree", "request_agrees", "note"}.
    """
    full = git(repo, "rev-parse", sha).strip()
    lines = changed_lines(repo, full)
    result = {"lines": 0, "agree": 0, "disagree": [], "request_agrees": None, "session_agrees": None, "note": ""}
    if not lines:
        result["note"] = "The commit added or rewrote no lines, so there was nothing to ask about."
        return result
    checkout = Path(repo).resolve() / ".whodunit" / "why" / full[:12]
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(checkout)], capture_output=True)
    checkout.parent.mkdir(parents=True, exist_ok=True)
    try:
        git(repo, "worktree", "add", "--detach", "--force", str(checkout), full)
        prompts, held = set(), set()
        for name, number in lines:
            raw = entire(checkout, "why", f"{name}:{number}", "--json")
            try:
                told = (json.loads(raw) if raw else {}).get("line") or {}
            except json.JSONDecodeError:
                told = {}
            if not told.get("commit_sha"):
                continue
            result["lines"] += 1
            if told["commit_sha"] == full and told.get("checkpoint_id") == checkpoint:
                result["agree"] += 1
                if told.get("prompt"):
                    prompts.add(" ".join(told["prompt"].split()))
                if told.get("session_id"):
                    held.add(told["session_id"])
            else:
                result["disagree"].append({"file": name, "line": number, "commit": told["commit_sha"][:12], "checkpoint": told.get("checkpoint_id") or ""})
        if not result["lines"]:
            result["note"] = "`entire why` could not be asked about the commit's lines."
        elif prompts and request:
            # The prompt Entire holds for those lines should be the request quoted on the page, or the start of it.
            shown = " ".join(request.split())
            result["request_agrees"] = all(shown.startswith(told.rstrip(".\u2026 ")) or told.startswith(shown) for told in prompts)
        if held and session:
            result["session_agrees"] = held == {session}
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(checkout)], capture_output=True)
        try:
            checkout.parent.rmdir()
        except OSError:
            pass
    return result


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
    # git records a commit to the whole second, and the command that made it is often issued a few
    # milliseconds into that second. Without the allowance that command looks later than the commit.
    commit_time = commit_time + timedelta(seconds=1)
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


def made_the_commit(entries: list[dict], sha: str, subject: str) -> bool:
    """Did this session run the commit? Its transcript then has the commit's subject in a `git commit`
    command, or the short SHA in what git printed back ("[main d4fb158] ...")."""
    for entry in entries:
        content = entry.get("message", {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                command = (block.get("input") or {}).get("command") or ""
                if "git" in command and "commit" in command and subject and subject in command:
                    return True
            elif block.get("type") == "tool_result":
                said = block.get("content")
                said = said if isinstance(said, str) else " ".join(part.get("text", "") for part in said or [] if isinstance(part, dict))
                if re.search(rf"\[[^\]\n]*\b{re.escape(sha[:7])}[0-9a-f]*\]", said):
                    return True
    return False


def pick_session(sessions: list[list[dict]], made_at: datetime, files: set[str], sha: str, subject: str) -> tuple[int | None, dict | None, str]:
    """Which session in a checkpoint is behind this commit: (its index, what read_transcript found in it, why it was picked).

    A checkpoint takes in every session open in the folder when the commit was made. The one
    wanted is the one that ran the commit. A session that only edited the same files may be an
    earlier attempt at the same change that was thrown away, with a differently worded request.
    """
    best, found, top, why = None, None, -1.0, ""
    for index, entries in enumerate(sessions):
        candidate = read_transcript(entries, made_at, files)
        if candidate["request"] is None:
            continue
        ran_it = made_the_commit(entries, sha, subject)
        edits = sum(1.0 for step in candidate["steps"] if step.kind == "edited")
        score = (100.0 if ran_it else 0.0) + edits
        if score > top:
            best, found, top = index, candidate, score
            why = "it ran the commit" if ran_it else "it edited the commit's files" if edits else "it is the only one with a prompt from before the commit"
    return best, found, why


def find_motive(repo: str | Path, sha: str) -> Motive:
    """Everything Entire knows about why this commit was made."""
    full, subject, stamp, trailer = git(
        repo, "show", "-s", "--format=%H%x00%s%x00%cI%x00%(trailers:key=Entire-Checkpoint,valueonly,separator=%x20)", sha
    ).strip().split("\x00")
    body = git(repo, "show", "-s", "--format=%b", full)
    body = "\n".join(line for line in body.splitlines() if not re.match(r"^[A-Za-z-]+: ", line)).strip()  # drop trailers
    motive = Motive(sha=full, subject=subject, message=body)
    if not trailer.strip():
        motive.note = "This commit has no Entire checkpoint, so there is no recorded request behind it."
        return motive
    motive.checkpoint = trailer.split()[0]
    meta = entire(repo, "checkpoint", "explain", "--checkpoint", motive.checkpoint, "--json")
    if meta is None:
        motive.note = f"The commit names Entire checkpoint {motive.checkpoint}, and Entire cannot find it, so the request behind this commit is not on record."
        return motive
    sessions = json.loads(meta).get("sessions") or [{}]
    files = {f for f in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", full).split("\n") if f}
    made_at = datetime.fromisoformat(stamp).astimezone(timezone.utc)
    # A checkpoint takes in every session that was open in the folder when the commit was made,
    # including ones that had nothing to do with it. pick_session says which one is wanted.
    transcripts = []
    for index in range(len(sessions)):
        raw = entire(repo, "checkpoint", "explain", "--checkpoint", motive.checkpoint, "--session-index", str(index), "--raw-transcript")
        entries = []
        for line in (raw or "").splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        transcripts.append(entries)
    chosen, found, why = pick_session(transcripts, made_at, files, full, subject)
    if found is None:
        motive.note = "The checkpoint has no transcript with a prompt from before this commit."
        return motive
    best_entries = transcripts[chosen]
    # The session's own id is in its transcript. The checkpoint's list is not always in the same order.
    motive.session = next((entry.get("sessionId") for entry in best_entries if entry.get("sessionId")), None) or sessions[chosen].get("session_id")
    if len(sessions) > 1:
        motive.note = (f"This checkpoint holds {len(sessions)} sessions. The one used is the one that " + {
            "it ran the commit": "ran the commit.", "it edited the commit's files": "edited the commit's files. None of them is on record as running the commit itself."}.get(
                why, "has a prompt from before the commit. None of them edited the commit's files, so the request shown may not be the cause of this commit."))
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
    # Two checks on what will be quoted. Is it word for word in the transcript, after the scrubbing above?
    # And does Entire, asked line by line, put the commit's lines behind the same checkpoint and request?
    motive.quote_checked = quoted_verbatim(motive.request, best_entries)
    motive.provenance = line_provenance(repo, full, motive.checkpoint, motive.request, motive.session)
    return motive

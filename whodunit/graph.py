"""Alibis from entire-graph: can this commit's changes reach the agent at all?

`entire graph commit` lists what a commit changed as entities (a function, a module body, a
document) and `entire graph impact` gives a symbol's callers. A commit that only touched the
README, or a helper script the agent never calls, has an alibi and starts with less suspicion.
It is never cleared outright: the lineup can still land on it if the replays say so.
"""

import json
import subprocess
from pathlib import Path

from .suspects import git

REACHES, UNKNOWN, DATA, UNCALLED, DOCS, ELSEWHERE = 1.0, 1.0, 0.6, 0.15, 0.05, 0.05
DOC_LANGUAGES = {"Markdown", "Git Ignore", "Text", "HTML", "CSS"}
CODE_LANGUAGES = {"Python", "TypeScript", "JavaScript", "Go", "Rust", "Java", "Ruby"}


def _graph(repo: str | Path, *args: str, timeout: float = 120.0) -> dict | None:
    """Run an entire-graph command that prints JSON. None if the plugin is missing or the call fails."""
    try:
        done = subprocess.run(["entire", "graph", *args], cwd=repo, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return None


def changes(repo: str | Path, sha: str) -> list[dict] | None:
    """What a commit changed, one entry per entity: {"path", "language", "kind", "name", "type", "dependents"}."""
    found = _graph(repo, "commit", sha, "--json")
    if found is None:
        return None
    out = []
    for file in found.get("files") or []:
        listed = file.get("changes") or [{"kind": "file", "name": file["path"], "type": file.get("status", "M")}]
        for change in listed:
            out.append({
                "path": file["path"], "language": file.get("language") or "", "kind": change.get("kind", ""),
                "name": change.get("name", ""), "type": change.get("type", ""), "dependents": change.get("dependents_count", 0),
            })
    return out


def called_from(repo: str | Path, name: str, path: str, entry: str) -> bool | None:
    """Is this symbol called, directly or through one other function, by code in the entry file? None if unknown."""
    found = _graph(repo, "impact", "--symbol", name, "--file", path, "--repo", ".", "--depth", "2", "--limit", "60", "--format", "json", "--head")
    if found is None or not found.get("focus") or found.get("disambiguation_required"):
        return None
    callers = [entry_["endpoint"].get("file_path", "") for entry_ in (found.get("callers") or {}).get("entries", [])]
    return entry in callers


def alibi(repo: str | Path, sha: str, target: str, entry: str = "agent.py") -> tuple[float, str]:
    """(prior weight, reason) for one suspect. A weight of 1 means no alibi."""
    prefix = "" if target in (".", "") else target.rstrip("/") + "/"
    entry_path = prefix + entry
    listed = changes(repo, sha)
    if listed is None:
        return UNKNOWN, "entire-graph could not read this commit"
    # Files the graph does not parse (a lockfile, say) are missing from its list. Git knows them.
    seen = {c["path"] for c in listed}
    for path in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--first-parent", sha).split("\n"):
        if path and path not in seen:
            listed.append({"path": path, "language": "Markdown" if path.endswith((".md", ".txt")) else "", "kind": "file", "name": path, "type": "M", "dependents": 0})
    inside = [c for c in listed if c["path"].startswith(prefix)]
    if not inside:
        return ELSEWHERE, "never touched the agent's folder"
    best, why = 0.0, ""
    for change in inside:
        short = change["path"][len(prefix):]
        if change["language"] in DOC_LANGUAGES:
            weight, reason = DOCS, f"only touched {short}, which the agent does not run"
        elif change["language"] not in CODE_LANGUAGES:
            weight, reason = DATA, f"changed {short}, a data or dependency file the graph cannot follow"
        elif change["path"] == entry_path:
            weight, reason = REACHES, f"changed {change['name'] if change['kind'] != 'module' else 'the body of ' + short}, in the agent's own file"
        elif change["kind"] in ("module", "file"):
            weight, reason = UNCALLED, f"changed {short}, a separate script"
        else:
            reached = called_from(repo, change["name"], change["path"], entry_path)
            if reached is None:
                weight, reason = UNKNOWN, f"changed {change['name']} in {short}, and the graph has no record of its callers"
            elif reached:
                weight, reason = REACHES, f"changed {change['name']} in {short}, which the agent calls"
            else:
                weight, reason = UNCALLED, f"changed {change['name']} in {short}, which the agent never calls"
        if weight > best:
            best, why = weight, reason
    return best, why

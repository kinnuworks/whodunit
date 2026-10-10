"""The ruling: revert the culprit, or keep what it was for and patch it?

That is the owner's call, and it is asked once per kind of change. The answer is kept as a
file under rulings/ so the next case of the same kind does not ask again.
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

REVERT, PATCH = "revert", "patch"

KINDS = {
    "prompt": "a change to the agent's instructions",
    "model-settings": "a change to the model or its settings",
    "dependency": "a dependency change",
    "tool-code": "a change to the code of a tool the agent calls",
    "agent-code": "a change to the agent's own code",
    "other": "a change outside the agent's code",
}


@dataclass
class Ruling:
    kind: str
    ruling: str  # revert or patch
    decided_on: str
    first_case: str
    culprit: str
    note: str = ""


def classify(diff: str, files: list[str]) -> str:
    """What kind of change the culprit made, from its diff. Rough on purpose: it only picks which standing ruling applies."""
    changed = [line[1:] for line in diff.splitlines() if line[:1] in "+-" and not line.startswith(("+++", "---"))]
    text = "\n".join(changed)
    names = " ".join(files).lower()
    if re.search(r"(pyproject\.toml|uv\.lock|requirements[\w.-]*\.txt|package(-lock)?\.json)", names) and not re.search(r"\.py\b", names):
        return "dependency"
    if re.search(r"\b(SYSTEM|PROMPT|INSTRUCTIONS)\b|system_prompt|\"role\": \"system\"", text) or "prompt" in names:
        return "prompt"
    # A reworded prompt often changes only the string lines inside it, and the name sits in the context.
    only_strings = bool(changed) and all(line.strip()[:1] in "\"'" or line.strip()[:2] in ('f"', "f'") for line in changed if line.strip())
    if only_strings and re.search(r"\b(SYSTEM|PROMPT|INSTRUCTIONS)\b|system_prompt", diff):
        return "prompt"
    if re.search(r"\b(MODEL|temperature|max_tokens|top_p)\b", text):
        return "model-settings"
    # A tool's own lines are often context around the change, so this one reads the whole diff.
    if re.search(r"kind=\"TOOL\"|\bTOOLS\b|def call_tool\b", diff):
        return "tool-code"
    if re.search(r"\.py\b", names):
        return "agent-code"
    return "other"


def path_for(repo: str | Path, kind: str) -> Path:
    return Path(repo) / "rulings" / f"{kind}.json"


def recall(repo: str | Path, kind: str) -> Ruling | None:
    path = path_for(repo, kind)
    return Ruling(**json.loads(path.read_text())) if path.is_file() else None


def question(kind: str, subject: str, request: str | None) -> str:
    asked = f' It was asked for with: "{request.strip().splitlines()[0][:160]}"' if request else ""
    return (
        f"The culprit is {KINDS.get(kind, kind)}: \"{subject}\".{asked}\n"
        f"Revert it, or keep what it was for and patch the bug? This answer becomes the rule for every {kind} case. [revert/patch] "
    )


def decide(repo: str | Path, kind: str, case_id: str, culprit: str, subject: str, request: str | None = None,
           answer: str | None = None, ask=input) -> tuple[Ruling, bool]:
    """Return (ruling, asked). Asks only when there is no ruling for this kind yet."""
    known = recall(repo, kind)
    if known:
        return known, False
    if answer is None:
        answer = ask(question(kind, subject, request))
    answer = answer.strip().lower()
    if answer not in (REVERT, PATCH):
        raise ValueError(f"the ruling has to be revert or patch, and was {answer!r}")
    ruling = Ruling(kind=kind, ruling=answer, decided_on=date.today().isoformat(), first_case=case_id, culprit=culprit)
    path = path_for(repo, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(ruling), indent=1) + "\n")
    return ruling, True

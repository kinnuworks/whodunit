"""Build a throwaway git repo with a bug planted at a known commit.

    python tests/planted.py <empty folder>     # the real refund agent, 20 suspects, prints the case file path

The tests use the same builders, so the history the demo bisects is the one that is tested.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VICTIM = REPO_ROOT / "victims" / "refund-agent"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Planted", "-c", "user.email=planted@example.invalid", "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{old!r} is not in {path.name}"
    path.write_text(text.replace(old, new, 1))


STUB = '''import json
BONUS = 0
print(json.dumps({"reply": "done", "refunds": [{"order_id": "1001", "refunded": 42.0 + BONUS}]}))
'''


def stub_history(repo: Path, suspects: int = 20, culprit: int = 13, broken: tuple[int, ...] = ()) -> dict:
    """A one-file agent that needs no model. Suspect numbers start at 1. `broken` commits do not compile."""
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    agent = repo / "agent" / "agent.py"
    agent.parent.mkdir()
    agent.write_text(STUB)
    shas = [commit(repo, "Start the stub agent")]
    for n in range(1, suspects + 1):
        text = agent.read_text().replace("def broken(:\n", "")
        if n == culprit:
            text = text.replace("BONUS = 0", "BONUS = 5")
            message = "Add a goodwill bonus to refunds"
        elif n in broken:
            text += "def broken(:\n"
            message = f"Half-finished refactor {n}"
        elif n % 4 == 0:
            (repo / "notes.md").write_text(f"note {n}\n")
            message = f"Update the notes ({n})"
        else:
            text += f"# tidy {n}\n"
            message = f"Tidy the agent ({n})"
        agent.write_text(text)
        shas.append(commit(repo, message))
    case = repo / "case.toml"
    case.write_text(f'''id = "stub-bonus"
symptom = "Refunds pay out more than the order amount"
good = "{shas[0]}"
bad = "{shas[-1]}"
target = "agent"
build = ["{sys.executable}", "-m", "py_compile", "agent.py"]
run = ["{sys.executable}", "agent.py", "{{input}}"]

[[inputs]]
text = "Please refund order 1001 for customer cust_9."
refunds = [{{ order_id = "1001", refunded = 42.0 }}]
''')
    return {"repo": repo, "case": case, "shas": shas, "culprit": shas[culprit] if culprit < len(shas) else None}


def refund_agent_history(repo: Path, suspects: int = 20, culprit: int = 14, broken: int = 6, fake_llm_port: int = 4199) -> dict:
    """The real refund agent with ordinary-looking commits, a planted overpayment and one commit that will not build."""
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    target = repo / "victims" / "refund-agent"
    target.mkdir(parents=True)
    for name in ("agent.py", "fake_llm.py", "pyproject.toml", "uv.lock", "README.md"):
        shutil.copy(VICTIM / name, target / name)
    (repo / ".gitignore").write_text(".venv/\n__pycache__/\n.whodunit/\nrequests.jsonl\ncase.toml\n")
    agent = target / "agent.py"
    shas = [commit(repo, "Import the refund agent")]
    for n in range(1, suspects + 1):
        if n == broken + 1:
            edit(agent, "def refund_policy(:\n", "")
        if n == culprit:
            edit(agent, 'refund = {"refunded": amount, "order_id": order_id}', 'refund = {"refunded": round(amount * 1.1, 2), "order_id": order_id}')
            message = "Add a 10% goodwill top-up to refunds"
        elif n == broken:
            edit(agent, "REFUNDS: list[dict] = []", "def refund_policy(:\nREFUNDS: list[dict] = []")
            message = "Start a refund policy helper"
        elif n == broken + 1:
            message = "Drop the unfinished refund policy helper"
        elif n % 5 == 0:
            (repo / "docs").mkdir(exist_ok=True)
            (repo / "docs" / f"note-{n}.md").write_text(f"Support note {n}.\n")
            message = f"Add support note {n}"
        elif n % 3 == 0:
            edit(agent, "\n}\nREFUNDS", f'\n    "{5000 + n}": {{"order_id": "{5000 + n}", "owner": "cust_{n}", "amount": {10 + n}.0, "status": "delivered"}},\n}}\nREFUNDS')
            message = f"Add order {5000 + n} to the test orders"
        else:
            with (target / "README.md").open("a") as f:
                f.write(f"\nNote {n}: checked the refund flow by hand.\n")
            message = f"Note a manual check in the README ({n})"
        shas.append(commit(repo, message))
    case = repo / "case.toml"
    case.write_text(f'''id = "planted-top-up"
symptom = "Refunds pay out more than the order amount"
good = "{shas[0]}"
bad = "{shas[-1]}"
target = "victims/refund-agent"
build = ["uv", "run", "-q", "python", "-m", "py_compile", "agent.py"]
run = ["uv", "run", "-q", "agent.py", "--json", "{{input}}"]

[env]
REFUND_LLM = "fake"
FAKE_LLM_URL = "http://127.0.0.1:{fake_llm_port}/v1"

[[inputs]]
text = "Please refund order 1001 for customer cust_9."
refunds = [{{ order_id = "1001", refunded = 42.0 }}]

[[inputs]]
text = "Please refund order 2002 for customer cust_9."
refunds = []
''')
    return {"repo": repo, "case": case, "shas": shas, "culprit": shas[culprit], "broken": shas[broken]}


if __name__ == "__main__":
    made = refund_agent_history(Path(sys.argv[1]))
    print(made["case"])
    print("culprit", made["culprit"])

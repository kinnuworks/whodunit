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
VICTIM_BASE = "e5542b7f40b7e37b5eea8d66ea754230cf4411c0"  # the last commit before the second session started growing the agent


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


STUB = '''import json, os, pathlib, sys, time
BONUS = 0
# STUB_OUTAGE plays a provider outage or a hang: "<commit prefix>|<which runs>|<counter file>|<what happens>".
# Which runs is "4" for the first four at that commit, or "12+6" to let twelve through and hit the next six.
# What happens is "exit <code>" with a provider error on stderr, or "sleep <seconds>".
outage = os.environ.get("STUB_OUTAGE", "")
if outage and os.environ.get("WHODUNIT_COMMIT", "").startswith(outage.split("|")[0]):
    _, which, counter, what = outage.split("|")
    skip, _, count = which.rpartition("+")
    seen = pathlib.Path(counter)
    n = int(seen.read_text()) if seen.exists() else 0
    seen.write_text(str(n + 1))
    if int(skip or 0) <= n < int(skip or 0) + int(count):
        kind, _, amount = what.partition(" ")
        if kind == "sleep":
            time.sleep(float(amount))
        else:
            print("Traceback (most recent call last):\\nprovider.ConnectionError: Connection error.", file=sys.stderr)
            sys.exit(int(amount))
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
void_exit_codes = [75]
void_stderr = ["provider.ConnectionError"]

[[inputs]]
text = "Please refund order 1001 for customer cust_9."
refunds = [{{ order_id = "1001", refunded = 42.0 }}]
''')
    return {"repo": repo, "case": case, "shas": shas, "culprit": shas[culprit] if culprit < len(shas) else None}


SHOP = '''import json, sys
STRANGERS = False
asked = " ".join(sys.argv[1:])
refunds = []
if "1001" in asked:
    refunds.append({"order_id": "1001", "refunded": 42.0})
if "2002" in asked and STRANGERS:
    refunds.append({"order_id": "2002", "refunded": 30.0})
print(json.dumps({"reply": "done", "refunds": refunds}))
'''


def shop_history(repo: Path, suspects: int = 8, culprit: int = 5) -> dict:
    """A one-file agent with two orders. The culprit starts refunding order 2002 to whoever asks.

    The case expects no refund at all, so a "fix" that stops every refund would pass it. That
    is what the do-no-harm check is for.
    """
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    agent = repo / "agent" / "agent.py"
    agent.parent.mkdir()
    agent.write_text(SHOP)
    shas = [commit(repo, "Start the shop agent")]
    for n in range(1, suspects + 1):
        if n == culprit:
            agent.write_text(agent.read_text().replace("STRANGERS = False", "STRANGERS = True"))
            shas.append(commit(repo, "Refund without checking who owns the order"))
        else:
            agent.write_text(agent.read_text() + f"# tidy {n}\n")
            shas.append(commit(repo, f"Tidy the agent ({n})"))
    case = repo / "case.toml"
    case.write_text(f'''id = "shop-strangers"
symptom = "Refunds go out on orders that belong to someone else"
good = "{shas[0]}"
bad = "{shas[-1]}"
target = "agent"
build = ["{sys.executable}", "-m", "py_compile", "agent.py"]
run = ["{sys.executable}", "agent.py", "{{input}}"]

[[inputs]]
text = "Please refund order 2002 for customer cust_9."
refunds = []
''')
    return {"repo": repo, "case": case, "shas": shas, "culprit": shas[culprit]}


TOP_UP = (
    'refund = {"refunded": amount, "order_id": order_id}',
    'refund = {"refunded": round(amount * 1.1, 2), "order_id": order_id}',
    "Add a 10% goodwill top-up to refunds",
)
# Fails about one run in three. A set of strings iterates in a different order in each Python
# process, and the raise sits inside the loop, so the lookup gives up whenever "#1001" comes first.
FLAKY_LOOKUP = (
    '''    if order_id not in ORDERS:
        raise LookupError(f"404: order {order_id} not found")
    return ORDERS[order_id]
''',
    '''    for form in {order_id, f"#{order_id}", order_id.zfill(6)}:  # every way customers write an id
        key = form.lstrip("0")
        if key in ORDERS:
            return ORDERS[key]
        raise LookupError(f"404: order {order_id} not found")
''',
    "Accept order ids written with a # or leading zeros",
)


# Needs a real model. The careful prompt names the ownership rule and this one drops it, so the
# model refunds another customer's order some of the time. On the gateway's small model that was
# 3 runs in 8 when it was first measured.
FRIENDLY_PROMPT = (
    '''SYSTEM = (
    "You are a refund agent for an online shop. Use lookup_order to find an order before refunding it. "
    "Only call issue_refund after lookup_order confirms the order exists and belongs to the customer. "
    "Never refund more than the order amount. "
''',
    '''SYSTEM = (
    "You are a friendly refund agent for an online shop. Customers who write in are often upset, so be warm, "
    "take their side and sort the refund out quickly. Use lookup_order to find the order and issue_refund to refund it. "
    "Never refund more than the order amount. "
''',
    "Make the agent's replies friendlier",
)
BUGS = {"top-up": TOP_UP, "flaky-lookup": FLAKY_LOOKUP, "friendly-prompt": FRIENDLY_PROMPT}


def refund_agent_history(repo: Path, suspects: int = 20, culprit: int = 14, broken: int = 6, fake_llm_port: int = 4199, flaky: bool = False, llm: str = "fake", bug: str | None = None) -> dict:
    """The real refund agent with ordinary-looking commits, a planted bug and one commit that will not build.

    The bug is an overpayment on every refund, or with `flaky` a lookup that fails about a third of the time.
    """
    bug = bug or ("flaky-lookup" if flaky else "top-up")
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    target = repo / "victims" / "refund-agent"
    target.mkdir(parents=True)
    for name in ("agent.py", "fake_llm.py", "pyproject.toml", "uv.lock", "README.md"):
        # The planted bugs are edits to the agent as it was before its real history grew.
        (target / name).write_text(git(REPO_ROOT, "show", f"{VICTIM_BASE}:victims/refund-agent/{name}") + "\n")
    (repo / ".gitignore").write_text(".venv/\n__pycache__/\n.whodunit/\nrequests.jsonl\ncase.toml\n")
    agent = target / "agent.py"
    shas = [commit(repo, "Import the refund agent")]
    for n in range(1, suspects + 1):
        if n == broken + 1:
            edit(agent, "def refund_policy(:\n", "")
        if n == culprit:
            old, new, message = BUGS[bug]
            edit(agent, old, new)
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
    symptom, inputs = {
        "top-up": ("Refunds pay out more than the order amount", [
            ("Please refund order 1001 for customer cust_9.", '{ order_id = "1001", refunded = 42.0 }'),
            ("Please refund order 2002 for customer cust_9.", ""),
        ]),
        "flaky-lookup": ("Some refunds are refused with an order not found error", [
            ("Please refund order 1001 for customer cust_9.", '{ order_id = "1001", refunded = 42.0 }'),
            ("Please refund order 1002 for customer cust_9.", '{ order_id = "1002", refunded = 18.5 }'),
        ]),
        "friendly-prompt": ("Some refunds go out on orders that belong to another customer", [
            ("Please refund order 2002 for customer cust_9.", ""),
            ("Please refund order 3003 for customer cust_9.", ""),
        ]),
    }[bug]
    blocks = "\n\n".join(f'[[inputs]]\ntext = "{text}"\nrefunds = [{refunds}]' for text, refunds in inputs)
    case.write_text(f'''id = "planted-{bug}"
symptom = "{symptom}"
good = "{shas[0]}"
bad = "{shas[-1]}"
target = "victims/refund-agent"
build = ["uv", "run", "-q", "python", "-m", "py_compile", "agent.py"]
run = ["uv", "run", "-q", "agent.py", "--json", "{{input}}"]

[env]
REFUND_LLM = "{llm}"
FAKE_LLM_URL = "http://127.0.0.1:{fake_llm_port}/v1"

{blocks}
''')
    return {"repo": repo, "case": case, "shas": shas, "culprit": shas[culprit], "broken": shas[broken]}


if __name__ == "__main__":
    # python tests/planted.py <folder> [top-up|flaky-lookup|friendly-prompt] [suspects] [culprit] [fake|gateway|own]
    extra = sys.argv[2:]
    bug = next((a for a in extra if a in BUGS), "flaky-lookup" if "flaky" in extra else "top-up")
    numbers = [int(a) for a in extra if a.isdigit()]
    llm = next((a for a in extra if a in ("fake", "mock", "gateway", "own")), "fake")
    made = refund_agent_history(Path(sys.argv[1]), *numbers[:2], bug=bug, llm=llm)
    print(made["case"])
    print("culprit", made["culprit"])

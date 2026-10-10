# Brief for the second session

This is for the coding session that grows the refund agent's history. It is separate from the session that builds Whodunit so that the commits and their Entire checkpoints come from real requests, and so that whoever builds the detective does not also write the crime.

## How it works

You do not edit the agent yourself. You act as the team that owns it, and every change goes through a fresh coding session, so that each commit has its own recorded request:

```bash
eval/ask.sh "In victims/refund-agent, <the request, as a person would put it>. Check agent.py still compiles, then commit."
```

`eval/ask.sh` starts a separate headless coding session, waits for it, and prints the commit it made. One call takes about a minute, so give the command a timeout of ten minutes. If it prints "no commit was made", ask again in different words. Never tell the coding session that a change is meant to break anything. It gets the request and nothing else.

To see how the agent behaves at a commit, on the real model:

```bash
uv run python eval/probe.py --ref HEAD --runs 10 "Please refund order 2002 for customer cust_9."
```

It prints what was refunded in each run. Use it before and after a change to measure a failure rate. Use `git log`, `git show` and `git diff` to read what a coding session did.

## What to do

1. Read `victims/refund-agent/agent.py` and its README first. Two commits have already been made this way (a currency field and a `placed_on` date). Continue from there.
2. Make 40 or more further commits, one request per commit, the way a small team would grow a support agent: new order fields, friendlier wording, a retry, a new tool, partial refunds, a refund window, a dependency bump, a refactor, tidier logs, README updates. Each request should read like something a person would ask for on an ordinary day. Vary the length and tone.
3. Among them, plant five or six regressions, spread across the history and at least six commits apart:
   - one that fails every time,
   - two or three that fail only some of the time (somewhere between one run in five and three in five),
   - one that comes from a request that sounds entirely reasonable, such as "make the replies friendlier",
   - one in a commit that also does something worth keeping, so that a plain revert would lose real work.
4. A regression is planted by the wording of an ordinary request, and by what the coding session then does with it. After each one, read the diff and probe the agent before and after. If the change did not break anything, that is fine: either leave it as an ordinary commit and try a different request later, or follow up with another ordinary request. Only regressions you have measured go in the answer key.
5. Each regression needs its own failing inputs, ones that the other regressions do not affect. Whodunit looks for one change point per case, so between a case's good ref and bad ref there must be exactly one commit that changes how those inputs behave.
6. Do not say in a request, a commit message or a comment that a change is a regression. The request is the motive, and it should sound innocent.
7. Work only through `eval/ask.sh` for changes to `victims/refund-agent/`. Do not touch `whodunit/`, `tests/`, or anything in `eval/` other than the answer key files below. Do not open `.env`.

## The answer key

Write `eval/answer-key.json` and do not commit it yet:

```json
{"cases": [
  {"case": "cases/<id>.toml", "culprit": "<full sha>", "rate": 0.35, "note": "what breaks and on which input"}
]}
```

For each entry, write the case file it names yourself, in this shape:

```toml
id = "short-id-that-does-not-give-the-cause-away"
symptom = "What a user or a support lead would report"
good = "<full sha, several commits before the culprit>"
bad = "<full sha, several commits after the culprit>"
target = "victims/refund-agent"
build = ["uv", "run", "-q", "python", "-m", "py_compile", "agent.py"]
run = ["uv", "run", "-q", "agent.py", "--json", "{input}"]

[env]
REFUND_LLM = "gateway"

[[inputs]]
text = "Please refund order 1001 for customer cust_9."
refunds = [{ order_id = "1001", refunded = 42.0 }]

[[inputs]]
text = "Please refund order 2002 for customer cust_9."
refunds = []
```

`refunds` is what a correct run pays out for that input, and a replay fails when the refunds differ. Every input in a case should be one that the regression can break. Leave at least five commits on each side of the culprit inside the range, more if you can, and make the ranges different sizes. Probe the good ref and the bad ref with the case inputs to confirm the good one passes and the bad one fails at the rate you expect.

Then commit the hash and only the hash:

```bash
shasum -a 256 eval/answer-key.json | cut -d' ' -f1 > eval/answer-key.sha256
git add eval/answer-key.sha256 cases/ && git commit -m "Seal the eval answer key"
```

Keep `eval/answer-key.json` out of git until Whodunit has run on every case. `eval/score.py` checks the file against the committed hash before it scores anything.

When you are done, say how many commits were made, how many cases were sealed and what was spent. Do not say which commits are the culprits. The session that builds Whodunit reads your last message.

## Traffic

This part is not for the second session. Once the history exists, the Whodunit session sends ordinary traffic through it so the traces have an onset to find:

```bash
uv run python eval/traffic.py --good <first commit of the history> --bad HEAD --runs 6 --llm gateway
```

At about 3,000 tokens a run on the small gateway model, 40 commits at 6 runs each is roughly a dollar.

## Things that will trip you up

- Keep one model for everything. A model change partway through looks like a regression.
- The session is recorded and will be public. Do not open `.env` or anything outside this repo.
- neatroots runs a local model on incoming runs at the moment, so keep to two or three agent runs at a time.

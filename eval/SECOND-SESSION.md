# Brief for the second session

This is for the coding session that grows the refund agent's history. It is separate from the session that builds Whodunit so that the commits and their Entire checkpoints come from real requests, and so that whoever builds the detective does not also write the crime.

## What to do

1. Work only inside `victims/refund-agent/`. Leave `whodunit/`, `eval/` and `tests/` alone.
2. Make 40 or more commits, one request per commit, the way a small team would grow a support agent: new order fields, friendlier wording, a retry, a new tool, a dependency bump, a refactor, tidier logs. Each request should read like something a person would ask for on an ordinary day.
3. Among them, plant regressions. Aim for five or six, spread across the history and at least six commits apart:
   - one that fails every time,
   - two or three that fail only some of the time (somewhere between one run in five and three in five),
   - one that comes from a change that sounds entirely reasonable, such as "make the replies friendlier",
   - one in a commit that also does something worth keeping, so that a plain revert would lose real work.
4. Do not say in a commit message, a comment or the session that a change is a regression. The request is the motive, and it should sound innocent.
5. Check each planted regression by running the agent a handful of times before and after, and note the failure rate you saw.

## The answer key

Write `eval/answer-key.json` and do not commit it yet:

```json
{"cases": [
  {"case": "cases/<id>.toml", "culprit": "<full sha>", "rate": 0.35, "note": "what breaks and on which input"}
]}
```

For each entry, write the case file it names: a symptom as a user would report it, two or three failing inputs with what each should have produced, the last good ref and the first bad ref. Pick the good ref well before the culprit and the bad ref well after it. `tests/planted.py` shows the format.

Then commit the hash and only the hash:

```bash
shasum -a 256 eval/answer-key.json | cut -d' ' -f1 > eval/answer-key.sha256
git add eval/answer-key.sha256 cases/ && git commit -m "Seal the eval answer key"
```

Keep `eval/answer-key.json` out of git until Whodunit has run on every case. `eval/score.py` checks the file against the committed hash before it scores anything.

## Traffic

Once the history exists, send ordinary traffic through it so the traces have an onset to find:

```bash
uv run python eval/traffic.py --good <first commit of the history> --bad HEAD --runs 6 --llm gateway
```

At about 3,000 tokens a run on the small gateway model, 40 commits at 6 runs each is roughly a dollar.

## Things that will trip you up

- Keep one model for everything. A model change partway through looks like a regression.
- The session is recorded and will be public. Do not open `.env` or anything outside this repo.
- neatroots runs a local model on incoming runs at the moment, so keep to two or three agent runs at a time.

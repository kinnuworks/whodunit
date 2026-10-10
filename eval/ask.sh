#!/bin/sh
# Send one request to a fresh headless coding session and report the commit it made.
#
#   eval/ask.sh "Add a status field to each order and commit."
#
# Each call is its own session, so Entire records the request as the motive for the commit.
# WORKER_MODEL picks the model (default sonnet). The request should end by asking for a commit.
set -u
cd "$(dirname "$0")/.." || exit 2
if [ -n "$(git status --porcelain -- victims/refund-agent)" ]; then
  echo "victims/refund-agent has uncommitted changes. Commit or discard them first."
  exit 2
fi
before=$(git rev-parse HEAD)
out=$(claude -p "$1" \
  --model "${WORKER_MODEL:-sonnet}" \
  --permission-mode acceptEdits \
  --settings '{"includeCoAuthoredBy": false, "attribution": {"commit": "", "pr": ""}}' \
  --append-system-prompt "Work only inside victims/refund-agent. Commit messages carry no co-author trailer and no generated-with line. Make exactly one commit for this request." \
  --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "Bash(git add:*)" "Bash(git commit:*)" "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(uv run:*)" "Bash(uv add:*)" "Bash(uv lock:*)" "Bash(python3 -m py_compile:*)" \
  --max-budget-usd "${WORKER_BUDGET:-1.5}" --output-format json 2>/dev/null | tail -1)
after=$(git rev-parse HEAD)
cost=$(printf '%s' "$out" | python3 -c "import json,sys
try: print(round(json.load(sys.stdin).get('total_cost_usd', 0), 2))
except Exception: print('unknown')")
if [ "$before" = "$after" ]; then
  # Nothing was committed. Put the agent's folder back so the next request starts clean.
  git checkout -q -- victims/refund-agent 2>/dev/null
  git clean -fdq -- victims/refund-agent 2>/dev/null
  echo "no commit was made (cost $cost). The folder was put back as it was."
  exit 1
fi
if git log -1 --format=%B | grep -qi "^co-authored-by"; then
  git log -1 --format=%B | grep -vi "^co-authored-by" > .git/whodunit-msg && git commit -q --amend -F .git/whodunit-msg
fi
echo "$(git rev-list --count "$before"..HEAD) commit(s), cost $cost:"
git log --format='%H %s' "$before"..HEAD
git show --stat --format= HEAD | tail -1

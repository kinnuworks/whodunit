"""Count the recorded refund-agent runs that issued a refund with no lookup before it, by where their commit sits.

This is the headline case turned into something to watch for: `issue_refund` called in a run where no
`lookup_order` came first. It reads neatroots, uses no model, and prints one JSON object.

    uv run python eval/standing_check.py
"""

import json
import subprocess
from collections import Counter

from whodunit.neat import neatroots, select_all

CULPRIT = "ced2ecd21c3ed165a1a729e17f68d2000cdc19ca"  # cases/whole-history.record.json, lineup.culprit
FIX = "7e8120e7a5bd05c5d54b542b8a2794fdbd6fc229"  # the same record, fix.commit


def holds(ancestor: str, sha: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, sha], capture_output=True).returncode == 0


def main() -> None:
    mcp = neatroots()
    runs = select_all(mcp, "select r.trace_id, s.attributes from runs r join spans s on s.trace_id = r.trace_id and s.name = 'run_info' "
                           "where r.workflow = 'refund-agent' and r.complete = 1", cap=20000)
    flagged = {row["trace_id"] for row in select_all(
        mcp, "select distinct f.trace_id from spans f where f.name = 'issue_refund' and not exists "
             "(select 1 from spans l where l.trace_id = f.trace_id and l.name = 'lookup_order' and l.start_ms < f.start_ms)", cap=20000)}
    where: dict[str, str] = {}
    seen, hits = Counter(), Counter()
    for row in runs:
        text = row["attributes"]  # the tags are in here as "commit:<sha>", whatever shape the attributes take
        at = text.find("commit:")
        sha = "".join(ch for ch in text[at + 7:at + 47] if ch in "0123456789abcdef") if at >= 0 else ""
        if len(sha) < 7:
            place = "no commit tag"
        else:
            if sha not in where:
                known = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0
                where[sha] = ("commit not in this repo" if not known else "at the kept fix" if holds(FIX, sha)
                              else "from the culprit on, unfixed" if holds(CULPRIT, sha) else "before the culprit")
            place = where[sha]
        seen[place] += 1
        hits[place] += row["trace_id"] in flagged
    print(json.dumps({"runs": sum(seen.values()), "flagged": sum(hits.values()),
                      "by_place": {place: {"runs": seen[place], "flagged": hits[place]} for place in sorted(seen)}}, indent=1))


if __name__ == "__main__":
    main()

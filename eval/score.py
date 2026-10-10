"""Score Whodunit against a sealed answer key.

    python eval/score.py eval/answer-key.json --sha256 <hash committed before the run>

The answer key is written by the session that plants the regressions, and its SHA-256 is
committed before Whodunit runs, so the answers cannot be adjusted afterwards. The key is JSON:

    {"cases": [{"case": "cases/friendlier-replies.toml", "culprit": "<full sha>"}]}

For each case this reads the record next to the case file (run `whodunit lineup` first) and
reports solved, wrong and unsolved cases, replays against a linear scan, and replay time.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def score(key: dict, root: Path) -> dict:
    rows = []
    for entry in key["cases"]:
        case = root / entry["case"]
        record_path = case.with_name(case.stem + ".record.json")
        if not record_path.is_file():
            rows.append({"case": entry["case"], "outcome": "not run"})
            continue
        record = json.loads(record_path.read_text())
        lineup = record.get("lineup") or {}
        named = (lineup.get("culprit") or {}).get("sha")
        order = [s["sha"] for s in record.get("suspects", [])]
        truth = entry["culprit"]
        top = (lineup.get("remaining") or [{}])[0].get("sha")
        rows.append({
            "case": entry["case"],
            "outcome": "solved" if named == truth else "wrong" if named else "nobody named",
            "top_suspect_right": (named or top) == truth,
            "suspects": len(order),
            "replays": lineup.get("replays", 0),
            "commits_tested": lineup.get("commits_tested", 0),
            # A linear scan replays every commit up to the culprit as often as this run replayed a commit on average.
            "linear_scan_commits": order.index(truth) + 1 if truth in order else None,
            "minutes": round(lineup.get("seconds", 0) / 60, 1),
            "replay_usd": (record.get("damages") or {}).get("replay_usd"),
        })
    done = [r for r in rows if r["outcome"] != "not run"]
    return {
        "cases": len(rows),
        "solved": sum(r["outcome"] == "solved" for r in done),
        "wrong_accusations": sum(r["outcome"] == "wrong" for r in done),
        "nobody_named": sum(r["outcome"] == "nobody named" for r in done),
        "not_run": len(rows) - len(done),
        "replays": sum(r["replays"] for r in done),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("key")
    parser.add_argument("--sha256", required=True, help="the hash that was committed before Whodunit ran")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    raw = Path(args.key).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != args.sha256:
        print(f"The answer key does not match the committed hash.\n  committed {args.sha256}\n  this file {actual}")
        return 2
    result = score(json.loads(raw), Path(args.root))
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"{result['solved']} of {result['cases']} cases solved. Wrong accusations: {result['wrong_accusations']}. Nobody named: {result['nobody_named']}. Not run: {result['not_run']}.")
    for row in result["rows"]:
        if row["outcome"] == "not run":
            print(f"  not run        {row['case']}")
        else:
            print(f"  {row['outcome']:<13}  {row['case']}  {row['replays']} replays over {row['commits_tested']} of {row['suspects']} commits, {row['minutes']} min. A linear scan stops at commit {row['linear_scan_commits']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

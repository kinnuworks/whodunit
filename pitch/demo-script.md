# Demo video script

About two and a half minutes. Screen recording with voice. The judges score the video on how clearly it explains the agent and the tool use, so every scene names the tool on screen.

Before recording: `neatroots start` is running, the terminal is in the repo root at a large font, and `cases/index.html` (the casebook, from `uv run whodunit casebook`) is open in a browser tab. Run the command in scene 2 once beforehand so the worktree environments are warm.

## Scene 1, the question (0:00 to 0:15)

Show `git log --oneline` scrolling on the refund agent's folder.

> This refund agent used to work. 57 commits later it is refunding orders that belong to other people. Not every time. About four times in five. Which commit did it, and why did anyone make it?

## Scene 2, one command (0:15 to 0:50)

Type and run:

```bash
uv run whodunit investigate cases/whole-history.toml --from-traffic refund-agent --fresh
```

`--fresh` sets the earlier record aside so the run starts from nothing. It takes about five minutes end to end and about 20 cents on the gateway, so record it once and cut.

Let the first lines print. Point at each as it appears.

> Whodunit starts with what it already has. Entire's code graph gives 22 of the 57 commits an alibi: a README edit cannot break a refund. And 18 ordinary runs in neatlogs had already asked this question. Four of them went wrong.

> Then it replays the failing request against the commits that are left, each in its own git worktree, each replay a real traced run of the agent. A bad commit does not fail every time, so it keeps a probability for every suspect.

Cut to the result line.

> Twenty replays. Five commits. 99.8 percent. This one.

## Scene 3, the motive (0:50 to 1:20)

Switch to the case file page. Scroll to Motive.

> And this is why it exists. The commit carries an Entire checkpoint, and the checkpoint holds the coding session behind it. Someone asked for this: "simple refunds feel slow, let the agent go straight to issue_refund when the customer has given the order number and the amount."

Scroll to Brief.

> A reasonable request. The brief sets it against what the commit did: it removed the only check on who owns the order. Every sentence here cites a span from a neatlogs trace, a commit or the checkpoint, and a sentence that cites nothing real is cut.

Scroll to Evidence, hover the two runs.

> Same request, one commit apart. On the left the agent looks the order up and refuses. On the right it pays.

## Scene 4, the ruling and the fix (1:20 to 1:55)

Scroll to Ruling and Fix.

> Revert it, or keep what it was for and patch it? That is the owner's call, and Whodunit asks once per kind of change. This was a prompt change and the rule was already patch, so nobody was asked.

> The patch keeps the shortcut and puts the ownership check back. Then it has to earn its place. Thirty replays, no failures. At 95% that puts the failure rate after the fix at 6.2% or less, close enough to where it was before the culprit to keep the patch.

Switch to `cases/turned-away.casefile.html`, scroll to Fix, "What it took".

> It does not always go that well. Here the first patch still failed 5 replays in 12. The second failed 4 in 18. So it reverted the commit, and the revert went 30 replays without a failure. And one case in our eval it could not fix at all, and it says so.

## Scene 5, the damage and the numbers (1:55 to 2:25)

Back to the first case file, scroll to Damages. Then show `eval/sealed/README.md`.

> The damage, read from the traces: 120 in refunds that went to the wrong people. The investigation cost 18 cents.

> We did not grade our own homework. A separate coding session grew this history through 53 ordinary requests, planted five regressions and sealed the answer key. Whodunit named all five and accused nobody wrongly.

> Plain bisect with five retries got three of them, and cheaper. On the fourth it named an innocent commit. On the fifth the broken version passed ten times in a row, so it never started.

## Scene 6, close (2:25 to 2:35)

Show the cfo.ai model, then the repo URL.

> The business plan is in cfo.ai. The code, the build log and every coding session behind it are public. Whodunit: which commit, and why.

## Shots to capture separately

- neatlogs cloud: the refund-agent traces list, and one trace open on the `issue_refund` span.
- Entire: the checkpoint page for the culprit commit, Sessions tab then Changes tab.
- cfo.ai: the plan's summary page and one scenario.

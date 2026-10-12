# Demo video script

A little under three minutes. Screen recording with voice. The judges score the video on how clearly it explains the agent and the tool use, so every scene names the tool on screen.

Before recording: `neatroots start` is running, the terminal is in the repo root at a large font, and `cases/index.html` (the casebook, from `uv run whodunit casebook`) is open in a browser tab on light paper. Run the command in scene 2 once beforehand so the worktree environments are warm. The numbers below are from the run of Monday 12 October. A new run will differ a little, so read them off the screen.

## Scene 1, the question (0:00 to 0:15)

Show `git log --oneline` scrolling on the refund agent's folder.

> This refund agent used to work. 57 commits later it is refunding orders that belong to other people. Not every time. About four times in five. Which commit did it, and why did anyone make it?

## Scene 2, one command (0:15 to 0:50)

Type and run:

```bash
uv run whodunit investigate cases/whole-history.toml --from-traffic refund-agent --fresh
```

`--fresh` sets the earlier record aside so the run starts from nothing. It took about eleven minutes end to end and about 80 cents on the gateway, so record it once and cut.

Let the first lines print. Point at each as it appears.

> Whodunit starts with what it already has. Entire's code graph gives 22 of the 57 commits an alibi: a README edit cannot break a refund. And 18 ordinary runs, traced with the neatlogs SDK, had already asked this question. Four of them went wrong. Without that head start the same case took 33 replays across 8 commits. With it, 20 across 5.

> Then it replays the failing request against the commits that are left, each in its own git worktree, each replay a real traced run of the agent. A bad commit does not fail every time, so it keeps a probability for every suspect.

Cut to the result line.

> Twenty replays. Five commits. 98.3 percent. This one.

Switch to the case file page and press "Replay the investigation" under the lineup. Let it run: the marks land, suspects are struck through, and the pencil ring is drawn last.

> Every suspect is a position in the lineup. An x is a replay that failed, an o is one that passed. Grey marks are ordinary runs it already had. Hatched ones have an alibi. Watch the odds move until one is left.

## Scene 3, the motive (0:50 to 1:20)

Scroll to Motive.

> And this is why it exists. The commit carries an Entire checkpoint, and the checkpoint holds the coding session behind it. Someone asked for this: "simple refunds feel slow, let the agent go straight to issue_refund when the customer has given the order number and the amount."

Scroll to Brief.

> A reasonable request. The brief sets it against what the commit did: it removed the only check on who owns the order. Every sentence here cites a span from a trace, a commit or the checkpoint, and a sentence that cites nothing real is cut. The numbers lead to the list in the margin.

Scroll to Evidence, Exhibit A and Exhibit B.

> Same request, one commit apart. In Exhibit A the agent looks the order up and refuses. In Exhibit B it pays. The step where they part is the ringed one.

## Scene 4, the ruling and the fix (1:20 to 1:55)

Scroll to Ruling and Fix.

> Revert it, or keep what it was for and patch it? That is the owner's call, and Whodunit asks once per kind of change. This was a prompt change and the rule was already patch, so nobody was asked.

> Then the fix has to earn its place. The first patch went thirty replays without a failure. Whodunit then replayed 13 other requests on it. One ordinary refund failed 8 times in 8, where before the patch it had failed 5 in 8. Worse, so that patch was thrown out. The second one, told what the first had broken, passed both checks: no failures in 30 replays, which at 95% means 6.2% or less, and nothing else broken.

Switch to `cases/turned-away.casefile.html`, scroll to Fix, "What it took".

> It does not always go that well. Here the first patch still failed 5 replays in 12. The second failed 4 in 18. So it reverted the commit, and the revert went 30 replays without a failure. And one case in our eval it could not fix at all, and it says so.

## Scene 5, the damage and the numbers (1:55 to 2:25)

Back to the first case file, scroll to Damages. Then show `eval/sealed/README.md`.

> The damage, read from the traces of scripted traffic: 120 in refunds that went to the wrong people. The whole investigation, both patches and their checks included, cost about 80 cents.

> We did not grade our own homework. A separate coding session grew this history through 53 ordinary requests, planted five regressions and sealed the answer key. Whodunit named all five and accused nobody wrongly.

> Plain bisect with five retries got three of them, and cheaper. On the fourth it named an innocent commit. On the fifth the broken version passed ten times in a row, so it never started.

## Scene 6, the plan and the close (2:25 to 2:50)

Show the cfo.ai workspace: the Cash and runway page with its chart, then the Simulator page. Drag the founder draw slider to $0 and let the cash line move.

> The business plan is a live model in cfo.ai: pricing, costs, revenue and runway, in four cases. What an investigation costs is taken from the six we ran. In the downside the plan lasts the year only if the founder takes no draw, and the simulator shows it.

Show the repo URL.

> The code, the build log and every coding session behind it are public. Whodunit: which commit, and why.

## Shots to capture separately

- neatlogs cloud: the refund-agent traces list, and one trace open on the `issue_refund` span.
- neatlogs cloud: the investigation's own trace, `b842b67dfae39c67c1a3aa76772f5229`, workflow `whodunit`, open on a lineup round and on the first fix attempt.
- Entire: the checkpoint page for the culprit commit, Sessions tab then Changes tab.
- cfo.ai: the Whodunit plan page, the Cash and runway page, and the simulator with the draw slider moved.

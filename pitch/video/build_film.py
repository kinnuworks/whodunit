"""Builds src/films/whodunit.json for the narrated cut. Scene lengths and event times come from
the narration clips in vo/, so the picture follows the voice. Run: python3 build_film.py"""
import json, math, subprocess
from pathlib import Path

TEMPO = 1.06   # the clips are played a little faster, to keep the film under 140 seconds
LEAD = 0.7     # beats of picture before the voice starts in a scene
VO = {
 1: "This refund agent used to work. Fifty-seven commits later, it doesn't. So which commit did it?",
 2: "It now refunds orders that belong to someone else. Not every time. About three runs in four.",
 3: "This is Whodunit. It finds the commit that broke an A.I. agent, and shows why that commit was made.",
 4: "One command opens the case. Entire's code graph gives twenty-two of the commits an alibi. And neat logs had already traced eighteen runs of this request, so the evidence starts before a single replay.",
 5: "Then, the lineup. Whodunit replays the failing request on suspect commits. A bad commit doesn't fail every time, so it keeps odds on every suspect, and names one only when it is ninety-five percent sure. Twenty replays later, it's commit thirty-seven, at ninety-eight point three percent.",
 6: "But why would anyone make that commit? Entire kept the coding session behind it. Someone asked for faster refunds. A fair request, and it removed the only check on who owns the order. Same request, one commit apart. One run looks the order up. The other just pays.",
 7: "Now the fix. The first patch passed thirty replays in a row. But Whodunit also replays other requests on a fix, and one of them got worse. So that patch was thrown out, and the second one was kept.",
 8: "Before the fix, eleven of fourteen runs went wrong. After it, none of thirty.",
 9: "The whole investigation is itself a trace in neat logs. And the damage is counted from traces too: one hundred and twenty, refunded to the wrong people.",
 10: "We sealed the answers before we tested. Five planted bugs. Five culprits named. Nobody wrongly accused. One is still not fixed, and the page says so.",
 11: "The business plan is a live model in C.F.O. dot A.I., built on what an investigation really costs. In the downside case, it survives only if the founder takes no draw.",
 12: "Neat logs, for the evidence. Entire, for the motive. C.F.O. dot A.I., for the plan.",
 13: "Whodunit. Which commit, and why.",
}
def seconds(n):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"vo/{n:02d}.mp3"], capture_output=True, text=True).stdout
    return float(out) / TEMPO
DUR = {n: seconds(n) for n in VO}
def a(n, phrase, lead=0.2):
    """The beat, from the scene's cut, at which `phrase` is spoken."""
    i = VO[n].index(phrase)
    return round(LEAD + (i / len(VO[n])) * DUR[n] * 2 - lead, 2)
def beats(n, tail=0.7):
    return math.ceil((LEAD / 2 + DUR[n] + tail / 2 + 0.2) * 2)

MARK = '<svg width="32" height="32" viewBox="0 0 28 28"><g fill="#17150F" stroke="#17150F" opacity=".38"><path d="M3.4 14h9" fill="none" stroke-width="1.5" stroke-linecap="round"/><circle cx="3.4" cy="14" r="2.2" stroke="none"/><circle cx="10.2" cy="14" r="2.2" stroke="none"/></g><circle cx="19.5" cy="14" r="3" fill="#17150F"/><path d="M20.6 11C19.4 9 16.9 7.7 14 7.8C10.1 7.9 7 10.6 7 14.1C7 17.6 10.2 20.3 14.1 20.2C18 20.1 21.1 17.3 21 13.8C20.95 12.3 20.3 10.9 19.2 9.9" fill="none" stroke="#A1411F" stroke-width="1.8" stroke-linecap="round" transform="translate(5.5 0) rotate(-12 14 14)"/></svg>'
TOP = [0.5, 0.095]
HIGH = [0.5, 0.075]
def cap(at, until, text, pos=TOP, **k): return {"at": at, "until": round(until, 2), "text": text, "pos": pos, **k}
def panel(pid, screen, w, lw, lh, x=0, y=130, **k): return {"id": pid, "screen": screen, "x": x, "y": y, "z": 0, "w": w, "h": round(w * lh / lw), "lw": lw, "lh": lh, "radius": 26, "float": 3, **k}
def card(i, x, y, z, frm=None): return {"id": f"c{i}", "screen": "WdCase", "props": {"variant": i}, "x": x, "y": y, "z": z, "w": 560, "h": 271, "lw": 620, "lh": 300, "radius": 22, **({"from": frm, "enter": "pop"} if frm else {})}

B = {n: beats(n) for n in VO}
B[13] = 14
scenes = []
# 1 the question
n = 1; q = a(n, "So which")
scenes.append({"id": "hook", "type": "Journey", "beats": B[n], "music": "sparse", "props": {
    "panels": [panel("log", "WdLog", 1320, 980, 640, y=190, radius=22)],
    "shots": [{"at": 0, "zoom": 0.96, "y": 120}, {"at": 0.1, "zoom": 1.04, "y": 140, "ms": 6000, "ease": "sine"}],
    "captions": [cap(-2.2, q - 0.4, "57 commits since it *last worked*."), cap(q, B[n] - 0.4, "Which one *did it*?")]}})
# 2 the problem
n = 2; ne = a(n, "Not every")
scenes.append({"id": "problem", "type": "Journey", "beats": B[n], "in": "blur", "music": "sparse", "events": {"ask": 0.8, "reply": a(n, "that belong"), "flag": ne}, "props": {
    "panels": [panel("chat", "WdChat", 1120, 860, 560, y=140, **{"from": -0.6})],
    "shots": [{"at": 0, "zoom": 0.98, "y": 80}, {"at": ne - 0.8, "zoom": 1.06, "y": 120, "ms": 1300}],
    "captions": [cap(0.3, ne - 0.4, "Now it refunds *strangers*."), cap(ne, B[n] - 0.4, "Not every time. About *three in four*.")]},
  "addCues": [{"at": "ask", "sfx": "pop", "gain": -8}, {"at": "reply", "sfx": "pop", "gain": -8}, {"at": "flag", "sfx": "thock", "gain": -5}]})
# 3 the title card
n = 3
scenes.append({"id": "title", "type": "Reveal", "beats": B[n], "in": "iris", "music": "build", "events": {"mark": 0.5, "name": 1.0, "tagline": a(n, "It finds")},
  "props": {"name": "Whodunit", "tagline": "Finds the commit that broke your AI agent. And why.", "markSvg": MARK}})
# 4 one command
n = 4; e = a(n, "Entire's"); nl = a(n, "And neat logs")
scenes.append({"id": "run", "type": "Journey", "beats": B[n], "in": "blur", "music": "build", "events": {"type": 0.9, "l1": 4.4, "l2": e, "l3": nl}, "props": {
    "panels": [panel("term", "WdTerminal", 1500, 1180, 520, radius=22, **{"from": -0.6})],
    "shots": [{"at": 0, "zoom": 1, "y": 40}, {"at": e - 0.8, "zoom": 1.08, "x": -30, "y": 120, "ms": 1100}],
    "captions": [cap(0.5, e - 0.4, "One command."), cap(e, nl - 0.4, "*Entire's* code graph clears 22."), cap(nl, B[n] - 0.4, "*neatlogs* had already traced 18 runs.")]},
  "addCues": [{"at": "type", "sfx": "type", "beats": 2.4, "gain": -9}, {"at": "l1", "sfx": "tick", "gain": -8}, {"at": "l2", "sfx": "tick", "gain": -8, "pitch": 2}, {"at": "l3", "sfx": "tick", "gain": -8, "pitch": 4}]})
# 5 the lineup
n = 5; w = a(n, "Whodunit replays"); bad = a(n, "A bad commit"); so = a(n, "so it keeps"); nm = a(n, "and names one"); tw = a(n, "Twenty replays"); ring = a(n, "it's commit")
scenes.append({"id": "lineup", "type": "Journey", "beats": B[n], "in": "blur", "music": "full",
  "events": {"alibi": 1.2, "traffic": 2.6, "r1": w + 1.2, "r2": bad + 0.6, "r3": so + 0.4, "r4": nm + 0.4, "ring": ring}, "props": {
    "panels": [panel("lu", "WdLineup", 1840, 1720, 540, y=110, float=2)],
    "shots": [{"at": 0, "zoom": 1.8, "x": -320, "y": 70}, {"at": 0.3, "zoom": 1.0, "x": 0, "y": 80, "ms": 1500}, {"at": bad - 1.2, "zoom": 1.5, "x": 255, "y": 90, "ms": 1300}, {"at": ring + 5, "zoom": 1.0, "x": 0, "y": 80, "ms": 1200}],
    "captions": [cap(0.5, bad - 0.4, "57 suspects, replayed in a *lineup*."),
                 cap(bad, nm - 0.4, "Bad commits don't fail *every time*.", HIGH), cap(nm, tw - 0.4, "So it names one only at *95%*.", HIGH), cap(tw, B[n] - 0.4, "20 replays. *98.3%* sure.", HIGH)]},
  "addCues": [{"at": "alibi", "sfx": "swish", "gain": -10}, {"at": "r1", "sfx": "type", "beats": 1.2, "gain": -8}, {"at": "r2", "sfx": "thock", "gain": -7}, {"at": "r3", "sfx": "thock", "gain": -7, "pitch": 2}, {"at": "r4", "sfx": "thock", "gain": -7, "pitch": 4}, {"at": "ring", "sfx": "chime", "gain": -4}]})
# 6 the motive
n = 6; en = a(n, "Entire kept"); fair = a(n, "A fair request"); same = a(n, "Same request"); one = a(n, "One run looks")
scenes.append({"id": "motive", "type": "Journey", "beats": B[n], "in": "blur", "music": "break",
  "events": {"type": en, "checked": en + 6.6, "show": same, "part": one}, "props": {
    "panels": [panel("mo", "WdMotive", 1400, 1120, 560, **{"from": -0.6, "to": same - 0.5, "exit": "fade"}),
               panel("ex", "WdExhibits", 1560, 1240, 520, y=140, chrome="none", float=2, **{"from": same - 0.3, "enter": "fade"})],
    "shots": [{"at": 0, "zoom": 1, "y": 80}, {"at": en, "zoom": 1.05, "y": 110, "ms": 4200, "ease": "sine"}, {"at": same - 0.6, "zoom": 1.0, "y": 80, "ms": 900}, {"at": one - 0.4, "zoom": 1.06, "y": 100, "ms": 1100}],
    "captions": [cap(0.3, en - 0.25, "Why would anyone *make* that commit?"), cap(en, fair - 0.4, "*Entire* kept the session behind it."),
                 cap(fair, same - 0.4, "A fair ask. It removed *the only check*."), cap(same, B[n] - 0.4, "Same request, *one commit apart*.")]},
  "addCues": [{"at": "type", "sfx": "type", "beats": 5.6, "gain": -11}, {"at": "checked", "sfx": "pop", "gain": -8}, {"at": "part", "sfx": "thock", "gain": -5}]})
# 7 the fix
n = 7; fp = a(n, "The first patch"); bw = a(n, "But Whodunit"); st = a(n, "So that patch"); sec = a(n, "and the second")
scenes.append({"id": "fix", "type": "Journey", "beats": B[n], "in": "blur", "music": "full",
  "events": {"v1": fp, "h1": bw + 1.5, "out1": st + 1.2, "v2": st + 1.8, "h2": sec + 0.6, "kept": sec + 2.2}, "props": {
    "panels": [panel("fx", "WdFix", 1500, 1160, 480, y=120, **{"from": -0.6})],
    "shots": [{"at": 0, "zoom": 1, "y": 60}, {"at": 0.1, "zoom": 1.05, "y": 70, "ms": 11000, "ease": "sine"}],
    "captions": [cap(0.3, bw - 0.4, "First patch: *0 failures in 30*."), cap(bw, st - 0.4, "But another request got *worse*."), cap(st, B[n] - 0.4, "Thrown out. The second patch is *kept*.")]},
  "addCues": [{"at": "v1", "sfx": "count", "beats": 2.6, "gain": -12}, {"at": "out1", "sfx": "thock", "gain": -5}, {"at": "kept", "sfx": "chime", "gain": -5}]})
# 8 before and after
n = 8; af = a(n, "After it")
scenes.append({"id": "proof", "type": "Journey", "beats": B[n], "in": "blur", "music": "full", "events": {"before": 0.6, "after": af}, "props": {
    "panels": [panel("ba", "WdBeforeAfter", 1520, 1400, 460, y=120, chrome="none", float=2)],
    "shots": [{"at": 0, "zoom": 0.98, "y": 60}, {"at": 0.1, "zoom": 1.04, "y": 70, "ms": 5000, "ease": "sine"}],
    "captions": [cap(0.3, B[n] - 0.4, "Before and after, on the *same request*.")]},
  "addCues": [{"at": "before", "sfx": "thock", "gain": -6}, {"at": "after", "sfx": "chime", "gain": -5}]})
# 9 the trace and the damage
n = 9; dm = a(n, "And the damage")
scenes.append({"id": "trace", "type": "Journey", "beats": B[n], "in": "blur", "music": "full", "events": {"rows": 0.6, "dmg": dm + 0.6}, "props": {
    "panels": [panel("tr", "WdTrace", 900, 900, 640, x=-410, radius=24, **{"from": -0.6}), panel("dm", "WdDamage", 640, 640, 640, x=470, radius=24, float=4, **{"from": dm - 0.2, "enter": "rise"})],
    "shots": [{"at": 0, "zoom": 1.2, "x": -400, "y": 120}, {"at": dm - 1.2, "zoom": 1.0, "x": 30, "y": 90, "ms": 1300}],
    "captions": [cap(0.3, dm - 0.4, "Every step is a *neatlogs* trace."), cap(dm, B[n] - 0.4, "The damage: *120.00* to the wrong people.")]},
  "addCues": [{"at": "rows", "sfx": "type", "beats": 1.6, "gain": -12}, {"at": "dmg", "sfx": "count", "beats": 2, "gain": -10}]})
# 10 the sealed eval
n = 10; five = a(n, "Five planted"); named = a(n, "Five culprits"); nob = a(n, "Nobody")
scenes.append({"id": "eval", "type": "Journey", "beats": B[n], "in": "blur", "music": "full", "props": {"dofK": 0.012,
    "panels": [card(0, 0, 0, 0), card(1, -700, -240, -480, 1.3), card(2, 720, -220, -400, 1.5), card(3, -760, 290, -360, 1.7), card(4, 700, 320, -520, 1.9), card(5, -120, -520, -860, 2.1)],
    "overlays": [{"id": "stats", "screen": "WdStats", "props": {"at": named + 0.2}, "x": 0, "y": 320, "w": 1300, "h": 195, "lw": 1400, "lh": 210, "from": named - 0.2, "enter": "rise", "radius": 26}],
    "shots": [{"at": 0, "zoom": 1.9, "x": 0, "y": 0, "z": 0}, {"at": 1.1, "zoom": 0.8, "x": 0, "y": 0, "z": -240, "ms": 1800}, {"at": five, "zoom": 0.86, "ry": -8, "x": 160, "z": -340, "ms": 2200, "ease": "sine"}, {"at": named - 0.4, "zoom": 0.76, "ry": 0, "x": 0, "y": -150, "z": -300, "ms": 1100}],
    "captions": [cap(0.4, five - 0.4, "We *sealed* the answers first."), cap(five, nob - 0.4, "5 planted bugs. *5 named*."), cap(nob, B[n] - 0.4, "Nobody wrongly accused. *One still open*.")]}})
# 11 the plan
n = 11; dn = a(n, "In the downside"); sv = a(n, "it survives")
scenes.append({"id": "plan", "type": "Journey", "beats": B[n], "in": "blur", "music": "build", "events": {"draw": 1, "slide": sv}, "props": {
    "panels": [panel("pl", "WdPlan", 1500, 1240, 660, y=140, **{"from": -0.6})],
    "shots": [{"at": 0, "zoom": 1, "y": 100}, {"at": dn - 0.8, "zoom": 1.06, "x": 80, "y": 120, "ms": 1100}],
    "captions": [cap(0.3, dn - 0.4, "The business plan lives in *cfo.ai*."), cap(dn, B[n] - 0.4, "The downside survives with *no founder draw*.")]},
  "addCues": [{"at": "draw", "sfx": "swish", "gain": -10}, {"at": "slide", "sfx": "swish", "gain": -7}]})
# 12 the three tools
n = 12
scenes.append({"id": "tools", "type": "Journey", "beats": B[n], "in": "blur", "music": "full", "events": {"t1": 0.6, "t2": a(n, "Entire, for"), "t3": a(n, "C.F.O.")}, "props": {
    "panels": [panel("tl", "WdTools", 1700, 1620, 520, y=130, chrome="none", float=2)],
    "shots": [{"at": 0, "zoom": 0.98, "y": 70}, {"at": 0.1, "zoom": 1.03, "y": 80, "ms": 6500, "ease": "sine"}],
    "captions": [cap(0.3, B[n] - 0.4, "Three tools, each doing *real work*.")]},
  "addCues": [{"at": "t1", "sfx": "pop", "gain": -6}, {"at": "t2", "sfx": "pop", "gain": -6, "pitch": 2}, {"at": "t3", "sfx": "pop", "gain": -6, "pitch": 4}]})
# 13 the close
scenes.append({"id": "outro", "type": "Outro", "beats": B[13], "in": "blur", "music": "out", "events": {"mark": 0, "line": 1, "roll": 2.4, "url": 5, "click": 7},
  "props": {"name": "Whodunit", "markSvg": MARK, "line": "Which commit did it, and", "roll": ["when.", "how.", "*why.*"], "url": "github.com/kinnuworks/whodunit", "cta": "", "look": "soft"}})

total = sum(B.values()) / 2 + 1
film = {
 "meta": {"title": "Whodunit, the demo", "fps": 30, "bpm": 120, "beatsPerBar": 4, "tailBeats": 2, "chords": ["Fmaj7", "Dm7", "Bbmaj7", "C"], "target": round(total)},
 "brand": {"bg": "#FAF6EF", "surface": "#FFFEFC", "ink": "#17150F", "muted": "#6D6459", "line": "#EBE3D7", "accent": "#A1411F", "accentInk": "#FFFFFF", "dark": "#14110D", "darkInk": "#F3ECE1",
           "fontDisplay": "Geist", "fontText": "Geist", "fontMono": "Geist Mono", "fontSerif": "Instrument Serif", "emphasis": "accent", "tracking": -0.04, "weight": 740,
           "look": "soft", "aurora": ["#F5D3BC", "#F2E2CE", "#FBE4D6", "#EBD8C6", "#FFFFFF"], "auroraStrength": 0.42, "panel": "#FFFEFC", "panelBorder": "rgba(23,16,14,0.06)"},
 "grain": 0.035, "scenes": scenes}
Path("src/films/whodunit.json").write_text(json.dumps(film, indent=1))
# where each narration clip starts, in seconds from the top of the film
start = 0.0; places = []
for i, s in enumerate(scenes, 1):
    places.append({"clip": f"vo/{i:02d}.mp3", "at": round(start + LEAD / 2, 3), "seconds": round(DUR[i], 2)})
    start += B[i] / 2
Path("build").mkdir(exist_ok=True)
Path("build/vo.json").write_text(json.dumps({"tempo": TEMPO, "clips": places}, indent=1))
print("beats", B, "total seconds", total)

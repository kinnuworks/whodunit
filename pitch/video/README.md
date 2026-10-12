# The demo video

`whodunit-demo.mp4` is 2 minutes 16 seconds, 1920 by 1080, with a narrator, captions and a synthesized score. It runs thirteen scenes: the question, one failing run, a title card, the command, the lineup, the motive, the fix, before and after, the trace and the damage, the sealed eval, the plan, the three tools, and the close. The file itself is not in the repo, because it is 64 MB. It is built in `video/`, which git ignores.

The narration is a synthesized voice, made with ElevenLabs from the script in `build_film.py`. Each scene is as long as its narration clip, and the events in a scene fire where the words fall.

An earlier cut, 89 seconds with captions and no voice, is kept beside it as `whodunit-v1-captions-only.mp4`.

What is here is the part of the film that is ours:

- `film.json`: the thirteen scenes, their timing in beats, the captions and the camera moves.
- `build_film.py`: the narration script, and the code that times every scene to its clip.
- `screens.tsx`: Whodunit's screens rebuilt so each row and mark can move: the git log, one failing run, the command, the lineup, the Entire checkpoint, the two exhibits, the two fix attempts, before and after, the neatlogs trace, the damages, the docket cards, the cash chart and the three tools.
- `data.json`: the 57 suspects, the ordinary runs and the four replay rounds of the headline case, copied from its record.
- `contact-sheet.png`: sixteen stills from the last third of the film.

The motion template the film runs on is not in the repo, because it is not ours to publish.

## What is real and what is drawn

Every number is from a case record, the cfo.ai model or the neatlogs dashboard. The request and the reply in the chat scene are word for word from the failing run. The lineup plays the record's own four rounds.

The screens are redrawn, so they are not screenshots. The exhibit steps are shortened. The trace shows 13 of the run's 17 steps. The cash chart is drawn from the model's monthly figures and is not cfo.ai's own chart.

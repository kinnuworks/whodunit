# The demo video

`whodunit-16x9.mp4` is 89 seconds, 1920 by 1080, with a synthesized score and no voice. The captions carry the story and name each tool where it does its work. The file itself is not in the repo, because it is 44 MB. It is built in `video/`, which git ignores.

What is here is the part of the film that is ours:

- `film.json`: the ten scenes, their timing in beats, the captions and the camera moves.
- `screens.tsx`: Whodunit's screens rebuilt so each row and mark can move: the git log, one failing run, the command, the lineup, the Entire checkpoint, the two exhibits, the two fix attempts, the neatlogs trace, the damages, the docket cards and the cash chart.
- `data.json`: the 57 suspects, the ordinary runs and the four replay rounds of the headline case, copied from its record.
- `contact-sheet.png`: sixteen stills from the middle of the film.

The motion template the film runs on is not in the repo, because it is not ours to publish.

## What is real and what is drawn

Every number is from a case record, the cfo.ai model or the neatlogs dashboard. The request and the reply in the chat scene are word for word from the failing run. The lineup plays the record's own four rounds.

The screens are redrawn, so they are not screenshots. The exhibit steps are shortened. The trace shows 13 of the run's 17 steps. The cash chart is drawn from the model's monthly figures and is not cfo.ai's own chart.

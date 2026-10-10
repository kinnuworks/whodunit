# Build log

Whodunit, built for neatHack between 10 and 12 October 2026. Times are IST. Newest entry last.

## Saturday 10 October

### 7:05 PM, repo created

The project is Whodunit: given an AI agent that used to work and now fails, find the commit that broke it, show what that commit was asked to do, fix it, and count the damage.

Checked before writing any code:

- neatroots 0.2.6 is running on port 4100 with 0 runs so far. Its local model is not installed, so checks will be rule checks for now.
- The hackathon model gateway lists a small Haiku model. Three parallel calls came back in about 1.4 seconds each, so replays can run a few at a time.
- In a throwaway repo, `entire enable` kept the redaction settings that were already in `.entire/settings.json` and installed 9 agent hooks plus 5 git hooks. Email and phone redaction is on here from the first commit because the session transcripts in this repo are public.

Next: turn Entire on, get the refund agent running with traces going to neatlogs and neatroots, and verify the first checkpoint.

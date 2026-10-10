"""Read keys from the repo's .env file inside the process that needs them."""

import os
from pathlib import Path


def load_env(start: str | Path = ".") -> None:
    """Put .env values into os.environ. Values already set win. Never prints anything."""
    explicit = os.environ.get("WHODUNIT_ENV")
    here = Path(start).resolve()
    candidates = [Path(explicit)] if explicit else [p / ".env" for p in (here, *here.parents)]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))

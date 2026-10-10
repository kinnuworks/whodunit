"""One way to ask a model for text, used by the brief and the patch.

WHODUNIT_LLM picks where the question goes:

    gateway  the hackathon gateway, with LITELLM_BASE_URL and LITELLM_API_KEY from .env (default)
    own      your own key, ANTHROPIC_API_KEY from .env
    agent    a coding agent in headless mode: the command in WHODUNIT_AGENT_CMD gets the prompt
             on stdin and prints its answer
    none     no model at all; callers fall back to a template

WHODUNIT_MODEL overrides the model id for gateway and own.
"""

import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request

from .env import load_env

DEFAULT_MODELS = {"gateway": "claude-sonnet-4.6", "own": "claude-sonnet-5-5"}


class LlmError(RuntimeError):
    pass


def choice() -> str:
    return os.environ.get("WHODUNIT_LLM", "gateway")


def model_name() -> str:
    which = choice()
    if which == "agent":
        return "coding agent, headless"
    return os.environ.get("WHODUNIT_MODEL", DEFAULT_MODELS.get(which, "none"))


def ask(system: str, prompt: str, max_tokens: int = 1500, timeout: float = 180.0) -> str:
    which = choice()
    if which == "none":
        raise LlmError("WHODUNIT_LLM is none")
    if which == "agent":
        command = os.environ.get("WHODUNIT_AGENT_CMD")
        if not command:
            raise LlmError("WHODUNIT_AGENT_CMD is not set")
        done = subprocess.run(shlex.split(command), input=f"{system}\n\n{prompt}", capture_output=True, text=True, timeout=timeout)
        if done.returncode != 0:
            raise LlmError(f"the coding agent exited with {done.returncode}")
        return done.stdout
    load_env()
    if which == "gateway":
        base, key = os.environ.get("LITELLM_BASE_URL", ""), os.environ.get("LITELLM_API_KEY", "")
    elif which == "own":
        base, key = "https://api.anthropic.com/v1", os.environ.get("ANTHROPIC_API_KEY", "")
    else:
        raise LlmError(f"WHODUNIT_LLM={which} is not one of gateway, own, agent, none")
    if not base or not key:
        raise LlmError(f"the keys for WHODUNIT_LLM={which} are not in .env")
    body = {
        "model": model_name(), "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", json.dumps(body).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise LlmError(f"the model endpoint answered {exc.code}") from None
    except OSError as exc:
        raise LlmError(f"the model endpoint is not reachable: {exc}") from None
    return reply["choices"][0]["message"]["content"] or ""

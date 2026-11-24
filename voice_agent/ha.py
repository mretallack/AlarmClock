"""Home Assistant Conversation API client — the "middle" of the voice agent.

This is the same call JarvisHA makes: POST /api/conversation/process with a
long-lived access token. HA's intent/LLM agent decides the reply, we just read
back the spoken text.

Credentials come from voice_agent/.env:
    HA=<long-lived access token>
    HA_URL=https://home.retallack.org.uk   # optional, this is the default
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"
DEFAULT_URL = "https://home.retallack.org.uk"


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _credentials() -> tuple[str, str]:
    env = _load_env()
    token = env.get("HA") or env.get("HA_TOKEN")
    url = env.get("HA_URL") or DEFAULT_URL
    if not token:
        raise RuntimeError(f"no HA token in {ENV_PATH}")
    return url.rstrip("/"), token


def ask(
    text: str,
    *,
    language: str = "en",
    agent_id: str | None = None,
    conversation_id: str | None = None,
    timeout: float = 20.0,
) -> dict:
    """Send *text* to HA Assist and return the parsed response.

    Keys of interest: speech (str), response_type, conversation_id,
    continue_conversation.
    """
    url, token = _credentials()
    payload: dict[str, object] = {"text": text, "language": language}
    if agent_id:
        payload["agent_id"] = agent_id
    if conversation_id:
        payload["conversation_id"] = conversation_id

    request = urllib.request.Request(
        f"{url}/api/conversation/process",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HA {exc.code}: {detail}") from exc

    result = body.get("response", {})
    speech = ((result.get("speech") or {}).get("plain") or {}).get("speech") or ""
    return {
        "speech": speech,
        "response_type": result.get("response_type"),
        "conversation_id": body.get("conversation_id"),
        "continue_conversation": body.get("continue_conversation", False),
        "raw": body,
    }

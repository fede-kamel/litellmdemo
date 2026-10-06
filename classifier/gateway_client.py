"""A small async client for the gateway that keeps the route it took.

Every call returns the text and the x-litellm-* routing headers, so the
labelling and evaluation scripts record which deployment answered and what
it cost.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx

GATEWAY = os.environ.get("LITELLM_GATEWAY", "http://127.0.0.1:4000")
KEYFILE = Path(os.environ.get("LITELLMDEMO_CONFIG", Path.home() / ".config/litellmdemo/config.json")).parent / "master_key"
CONCURRENCY = int(os.environ.get("LITELLMDEMO_CONCURRENCY", "8"))

_client: httpx.AsyncClient | None = None
_gate = asyncio.Semaphore(CONCURRENCY)


def key() -> str:
    return os.environ.get("LITELLM_API_KEY") or KEYFILE.read_text().strip()


async def chat(model: str, prompt: str | list, *, max_tokens: int = 1500, json_mode: bool = False,
               tags: list[str] | None = None, retries: int = 2) -> dict:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=300)
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tags:
        body["tags"] = tags
    async with _gate:
        for attempt in range(retries + 1):
            r = await _client.post(f"{GATEWAY}/v1/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {key()}"})
            if r.status_code == 200 or attempt == retries:
                break
            await asyncio.sleep(2 + 3 * attempt)
    headers = {k.lower(): v for k, v in r.headers.items() if k.lower().startswith("x-litellm")}
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "text": r.text[:500], "headers": headers}
    data = r.json()
    return {"ok": True, "text": (data["choices"][0]["message"].get("content") or "").strip(),
            "headers": headers, "usage": data.get("usage", {})}

"""A small async client for the gateway that keeps the route it took.

Every call returns the text and the x-litellm-* routing headers, so the
labelling and evaluation scripts record which deployment answered and what
it cost.

Failover: LITELLM_GATEWAY_FALLBACK names more gateways (comma-separated).
A gateway that is unreachable, or whose OCI signing fails (a 401 from OCI
passes every health check), is skipped for 30 seconds and the call goes to
the next. Each result says which gateway answered.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

GATEWAY = os.environ.get("LITELLM_GATEWAY", "http://127.0.0.1:4000")
KEYFILE = Path(os.environ.get("LITELLMDEMO_CONFIG", Path.home() / ".config/litellmdemo/config.json")).parent / "master_key"
GATEWAYS = [GATEWAY] + [u.strip() for u in os.environ.get("LITELLM_GATEWAY_FALLBACK", "").split(",") if u.strip()]
SKIP_SECONDS = 30
CONCURRENCY = int(os.environ.get("LITELLMDEMO_CONCURRENCY", "8"))

_client: httpx.AsyncClient | None = None
_gate = asyncio.Semaphore(CONCURRENCY)


def key() -> str:
    return os.environ.get("LITELLM_API_KEY") or KEYFILE.read_text().strip()


_down: dict[str, float] = {}   # gateway -> when it last failed


def _client_() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # Idle connections are dropped after 2 s, before the gateway's server closes them (uvicorn: 5 s);
        # otherwise a request can go out on a connection the server has just closed.
        _client = httpx.AsyncClient(timeout=300, limits=httpx.Limits(keepalive_expiry=2))
    return _client


# A kept-alive connection the server closed: the request never reached it, so it is safe to send again.
STALE = (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)


async def _send(method: str, url: str, **kw) -> httpx.Response:
    """One request, sent once more on a fresh connection if the pooled one turned out to be closed."""
    try:
        return await _client_().request(method, url, **kw)
    except STALE:
        return await _client_().request(method, url, **kw)


def mark_down(url: str, why: str = "") -> None:
    _down[url] = time.monotonic()
    print(f"GATEWAY-DOWN {url} skipped for {SKIP_SECONDS}s: {why or 'request failed'}", file=sys.stderr, flush=True)


async def active_gateway() -> str:
    """The first gateway that is not marked down and answers its liveness check."""
    for url in GATEWAYS:
        if time.monotonic() - _down.get(url, -SKIP_SECONDS) < SKIP_SECONDS:
            continue
        if len(GATEWAYS) == 1:
            return url
        started = time.monotonic()
        try:
            # 5 s: a gateway busy with a long reasoning call answers its liveness check late, not never
            r = await _send("GET", f"{url}/health/liveliness", timeout=5)
            if r.status_code == 200:
                return url
            why = f"liveness {r.status_code}"
        except httpx.HTTPError as exc:
            why = f"liveness {type(exc).__name__} after {time.monotonic() - started:.1f}s"
        mark_down(url, why)
    return GATEWAYS[-1]


def _gateway_fault(r: httpx.Response) -> bool:
    """A failure of the gateway or its OCI signing, not of the request: worth trying another gateway."""
    return r.status_code in (502, 503, 504) or (r.status_code == 401 and "OciException" in r.text)


async def chat(model: str, prompt: str | list, *, max_tokens: int = 1500, json_mode: bool = False,
               tags: list[str] | None = None, retries: int = 2, metadata: dict | None = None) -> dict:
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tags:
        body["tags"] = tags
    if metadata:
        body["metadata"] = metadata
    r, url, error = None, GATEWAY, ""
    async with _gate:
        for attempt in range(retries + len(GATEWAYS)):
            url = await active_gateway()
            try:
                r = await _send("POST", f"{url}/v1/chat/completions", json=body,
                                headers={"Authorization": f"Bearer {key()}"})
            except httpx.TransportError as exc:
                r, error = None, f"{type(exc).__name__} from {url}"
                mark_down(url, error)
                continue
            if r.status_code == 200:
                break
            if _gateway_fault(r):
                mark_down(url, f"{r.status_code} from {url}")
                continue
            if attempt >= retries:
                break
            await asyncio.sleep(2 + 3 * attempt)
    if r is None:
        return {"ok": False, "status": 0, "text": error or "no gateway reachable", "headers": {}, "gateway": url}
    headers = {k.lower(): v for k, v in r.headers.items() if k.lower().startswith("x-litellm")}
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "text": r.text[:500], "headers": headers, "gateway": url}
    data = r.json()
    return {"ok": True, "text": (data["choices"][0]["message"].get("content") or "").strip(),
            "headers": headers, "usage": data.get("usage", {}), "gateway": url}

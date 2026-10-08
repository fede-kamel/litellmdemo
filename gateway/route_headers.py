"""Return the classifier's decision to the caller, in the gateway's own response.

The complexity router keeps only the route name (x-litellm-complexity-router-tier).
trained_classifier.py leaves its full decision on the request's metadata
(requester_metadata: LiteLLM 1.104 copies the rest before this hook runs); this
callback returns it as one header, so an application, or the control room, can
explain a route from what the gateway decided rather than by asking a second
copy of the classifier:

    x-litellm-route-decision: {"route": "MEDIUM", "criterion": "ladder", "bar": 0.7,
                               "p": {"SIMPLE": 0.47, "MEDIUM": 0.96, ...}, ...}

    litellm_settings:
      callbacks: [oci_session_signer.handler, route_headers.handler]
"""

from __future__ import annotations

import json

from litellm.integrations.custom_logger import CustomLogger

HEADER = "x-litellm-route-decision"


class RouteHeaders(CustomLogger):
    async def async_post_call_response_headers_hook(self, data, user_api_key_dict, response,
                                                    request_headers=None, litellm_call_info=None):
        for key in ("metadata", "litellm_metadata"):
            metadata = data.get(key)
            carrier = metadata.get("requester_metadata") if isinstance(metadata, dict) else None
            if isinstance(carrier, dict) and carrier.get("_route_decision"):
                return {HEADER: json.dumps(carrier["_route_decision"], separators=(",", ":"), ensure_ascii=True)}
        return None


NAMES = {"SIMPLE": "fast", "MEDIUM": "balanced", "COMPLEX": "strong", "REASONING": "reasoning"}


def _why(d: dict | None) -> str:
    if not d:
        return "-"
    if d.get("criterion") == "ladder":
        r = d.get("route")
        pr, bar = d.get("p", {}).get(r, 0), d.get("bar", 0)
        if pr >= bar:
            return f"ladder: {NAMES.get(r, r)} {pr:.0%} >= bar {bar:.0%}"
        return f"ladder: none clears bar {bar:.0%}; {NAMES.get(r, r)} most likely at {pr:.0%}"
    return str(d.get("criterion"))


class ConsoleLog(CustomLogger):
    """One line per request on stdout, for the control room's console:

    ROUTE key=openshell-agent asked=oci-auto-trained route=MEDIUM why="ladder: balanced 96% >= bar 70%"
          model=oci/openai.gpt-5-mini 1.24s $0.002430 tokens=31/240 fallbacks=0
    """

    @staticmethod
    def _line(kwargs, start_time, end_time, ok: bool, error: str = "") -> str:
        slo = kwargs.get("standard_logging_object") or {}
        md = (kwargs.get("litellm_params") or {}).get("metadata") or {}
        decision = (md.get("requester_metadata") or {}).get("_route_decision") if isinstance(md, dict) else None
        key = (slo.get("metadata") or {}).get("user_api_key_alias") or md.get("user_api_key_alias") or "master"
        asked = md.get("original_model_group") or md.get("model_group") or slo.get("model_group") or "-"
        seconds = (end_time - start_time).total_seconds() if start_time and end_time else 0.0
        parts = [f"key={key}", f"asked={asked}"]
        if decision:
            parts += [f"route={decision.get('route')}", f'why="{_why(decision)}"']
        parts += [f"model={kwargs.get('model') or slo.get('model')}", f"{seconds:.2f}s"]
        if ok:
            parts += [f"${float(slo.get('response_cost') or 0):.6f}",
                      f"tokens={slo.get('prompt_tokens', 0)}/{slo.get('completion_tokens', 0)}"]
        fb = md.get("attempted_fallbacks") or 0
        parts.append(f"fallbacks={fb}")
        if error:
            parts.append(f'error="{error[:160]}"')
        return ("ROUTE " if ok else "ROUTE-FAIL ") + " ".join(parts)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        print(self._line(kwargs, start_time, end_time, True), flush=True)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        err = kwargs.get("exception") or (kwargs.get("standard_logging_object") or {}).get("error_str") or ""
        print(self._line(kwargs, start_time, end_time, False, str(err).replace("\n", " ")), flush=True)


handler = RouteHeaders()
console = ConsoleLog()

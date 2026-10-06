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
                return {HEADER: json.dumps(carrier.pop("_route_decision"), separators=(",", ":"), ensure_ascii=True)}
        return None


handler = RouteHeaders()

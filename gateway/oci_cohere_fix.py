"""Let OCI's Cohere models answer after a tool call.

LiteLLM's OCI provider (1.104.0, and main at the time of writing) gets two
things wrong on the call that follows a tool call, when the conversation ends
with a tool result:

1. The request. It appends the tool result to `chatHistory` and still sets
   `message` to the last user message. OCI's Cohere API refuses that: 400
   "cannot specify message if the last entry in chat history contains tool
   results". Cohere's contract for that turn is a top-level `toolResults` and
   an empty `message` ("message must be at least 1 token long or tool results
   must be specified").
2. The response. With tool results the model cites them, and OCI writes the
   citation field as `documentIds`; LiteLLM's `CohereCitation` type requires
   `document_ids`, so a good answer failed validation ("Response cannot be
   casted to CohereChatResult").

In this demo every such call failed and fell back (the MULTILINGUAL route,
Command A, on the second call of the Japanese request). This module wraps
LiteLLM's request and response transformations for that one case; nothing
else changes. Imported by oci_session_signer.py, so it applies wherever the
gateway's OCI fixes do. Proposed upstream to BerriAI/litellm.
"""

from __future__ import annotations

import json

import httpx
from litellm.llms.oci.chat.transformation import OCIChatConfig

_transform_request = OCIChatConfig.transform_request
_transform_response = OCIChatConfig.transform_response


def transform_request(self, model, messages, optional_params, litellm_params, headers):
    body = _transform_request(self, model, messages, optional_params, litellm_params, headers)
    chat = body.get("chatRequest") if isinstance(body, dict) else None
    if isinstance(chat, dict) and chat.get("apiFormat") == "COHERE" and messages and messages[-1].get("role") == "tool":
        history = list(chat.get("chatHistory") or [])
        results: list = []
        while history and isinstance(history[-1], dict) and history[-1].get("role") == "TOOL":
            results = list(history.pop().get("toolResults") or []) + results
        if results:
            chat["chatHistory"] = history
            chat["toolResults"] = results
            chat["message"] = ""
    return body


def transform_response(self, model, raw_response, model_response, *args, **kwargs):
    try:
        data = raw_response.json()
    except ValueError:
        data = None
    chat = data.get("chatResponse") if isinstance(data, dict) else None
    citations = chat.get("citations") if isinstance(chat, dict) else None
    if citations and any(isinstance(c, dict) and "documentIds" in c and "document_ids" not in c for c in citations):
        for c in citations:
            if isinstance(c, dict) and "documentIds" in c:
                c.setdefault("document_ids", c["documentIds"])
        # the body is re-serialised uncompressed: the original's encoding and length headers no longer describe it
        headers = {k: v for k, v in raw_response.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
        raw_response = httpx.Response(raw_response.status_code, headers=headers, content=json.dumps(data).encode(),
                                      request=getattr(raw_response, "_request", None))
    return _transform_response(self, model, raw_response, model_response, *args, **kwargs)


OCIChatConfig.transform_request = transform_request
OCIChatConfig.transform_response = transform_response


# Streaming. OCI compresses its event stream (zstd), and httpx decoding it chunk by chunk fails
# with "cannot use a decompressobj multiple times" (LiteLLM 1.104): every streamed OCI chat call
# broke, which is how Codex and most OpenAI clients call. Ask for an uncompressed stream; the
# header is not part of OCI's request signature.
_validate_environment = OCIChatConfig.validate_environment


def validate_environment(self, headers, *args, **kwargs):
    out = _validate_environment(self, headers, *args, **kwargs)
    out["Accept-Encoding"] = "identity"
    return out


OCIChatConfig.validate_environment = validate_environment

"""A LiteLLM provider for OCI Generative AI's Responses API, so the CODE route can use Codex.

OCI serves OpenAI's Codex models (openai.gpt-5.3-codex) only on its
OpenAI-compatible Responses endpoint, /openai/v1/responses: the chat API
answers "This model is not supported in the v1/chat/completions endpoint. Use
the v1/responses endpoint instead." LiteLLM's OCI provider speaks only the chat
API, so this custom provider (LiteLLM's CustomLLM) does the translation:

    chat request  -> Responses input: system text becomes `instructions`; user text
                     and images, assistant turns, tool calls and tool results become
                     input items; chat tools become Responses function tools
    Responses     -> chat response: output text, function calls as tool_calls, usage

Requests are signed like every other OCI call (oci_session_signer.py: the
operator's session, or the node's instance principal on OKE). An HTTP error
is raised as such, so LiteLLM's fallbacks and retries apply.

    litellm_settings:
      custom_provider_map: [{provider: oci-responses, custom_handler: oci_responses.handler}]
    model_list:
      - model_name: oci-code
        litellm_params: {model: oci-responses/openai.gpt-5.3-codex}
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

import requests
from litellm import CustomLLM
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ChatCompletionMessageToolCall, Function, ModelResponse, Usage

# LiteLLM loads this module by path; its sibling may not be importable from the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oci_session_signer import handler as signing  # noqa: E402


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in (content or []) if isinstance(p, dict))


def to_responses(messages: list[dict], optional_params: dict) -> dict:
    instructions, items = [], []
    for m in messages:
        role, content = m.get("role"), m.get("content")
        if role in ("system", "developer"):
            instructions.append(_text(content))
        elif role == "user":
            parts = [{"type": "input_text", "text": content}] if isinstance(content, str) else [
                {"type": "input_text", "text": p.get("text", "")} if p.get("type") == "text" else
                {"type": "input_image", "image_url": (p.get("image_url") or {}).get("url") if isinstance(p.get("image_url"), dict) else p.get("image_url")}
                for p in (content or []) if isinstance(p, dict)]
            items.append({"role": "user", "content": parts})
        elif role == "assistant":
            if _text(content):
                items.append({"role": "assistant", "content": [{"type": "output_text", "text": _text(content)}]})
            for c in m.get("tool_calls") or []:
                f = c.get("function") or {}
                items.append({"type": "function_call", "call_id": c.get("id"), "name": f.get("name"),
                              "arguments": f.get("arguments") or "{}"})
        elif role == "tool":
            items.append({"type": "function_call_output", "call_id": m.get("tool_call_id"), "output": _text(content)})
    body: dict = {"input": items}
    if instructions:
        body["instructions"] = "\n\n".join(instructions)
    tools = optional_params.get("tools") or []
    if tools:
        body["tools"] = [{"type": "function", "name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "parameters": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                         for t in tools if t.get("type") == "function"]
        if isinstance(optional_params.get("tool_choice"), str):
            body["tool_choice"] = optional_params["tool_choice"]
    limit = optional_params.get("max_completion_tokens") or optional_params.get("max_tokens")
    if limit:
        body["max_output_tokens"] = int(limit)
    return body


class OCIResponses(CustomLLM):
    async def acompletion(self, model, messages, api_base, custom_prompt_dict, model_response: ModelResponse, print_verbose,
                          encoding, api_key, logging_obj, optional_params, acompletion=None, litellm_params=None,
                          logger_fn=None, headers=None, timeout=None, client=None):
        params = {**(litellm_params or {}), **(optional_params or {})}
        region = params.get("oci_region") or os.environ.get("OCI_REGION", "us-chicago-1")
        compartment = params.get("oci_compartment_id") or os.environ["OCI_COMPARTMENT_ID"]
        body = {"model": model.split("/", 1)[-1], **to_responses(messages, optional_params or {})}
        url = api_base or f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1/responses"
        started = time.time()
        r = await asyncio.to_thread(requests.post, url, json=body, auth=signing.signer(), timeout=float(timeout or 300),
                                    headers={"opc-compartment-id": compartment, "content-type": "application/json"})
        if r.status_code != 200:
            raise CustomLLMError(status_code=r.status_code, message=r.text[:800])
        data = r.json()
        text, calls = [], []
        for item in data.get("output", []):
            if item.get("type") == "message":
                text += [c.get("text", "") for c in item.get("content", []) if c.get("type") in ("output_text", "text")]
            elif item.get("type") == "function_call":
                calls.append(ChatCompletionMessageToolCall(id=item.get("call_id") or f"call_{uuid.uuid4().hex[:12]}", type="function",
                                                           function=Function(name=item.get("name"), arguments=item.get("arguments") or "{}")))
        choice = model_response.choices[0]
        choice.message.content = "".join(text) or None
        if calls:
            choice.message.tool_calls = calls
        choice.finish_reason = "tool_calls" if calls else "stop"
        u = data.get("usage") or {}
        model_response.usage = Usage(prompt_tokens=u.get("input_tokens", 0), completion_tokens=u.get("output_tokens", 0),
                                     total_tokens=u.get("total_tokens", u.get("input_tokens", 0) + u.get("output_tokens", 0)))
        model_response.model = model
        model_response.created = int(started)
        return model_response

    def completion(self, *args, **kwargs):
        return asyncio.run(self.acompletion(*args, **kwargs))

    async def astreaming(self, model, messages, api_base, custom_prompt_dict, model_response: ModelResponse, print_verbose,
                         encoding, api_key, logging_obj, optional_params, acompletion=None, litellm_params=None,
                         logger_fn=None, headers=None, timeout=None, client=None):
        """A streamed request (Codex and most OpenAI clients stream): one buffered OCI call, replayed as chunks.

        Without this LiteLLM failed every streamed call ("'coroutine' object is not an iterator") and the
        CODE route fell back to its backup, quietly."""
        r = await self.acompletion(model, messages, api_base, custom_prompt_dict, ModelResponse(), print_verbose, encoding,
                                   api_key, logging_obj, optional_params, acompletion, litellm_params, logger_fn, headers,
                                   timeout, client)
        msg, u = r.choices[0].message, r.usage
        usage = {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens, "total_tokens": u.total_tokens}
        calls = msg.tool_calls or []
        yield {"text": msg.content or "", "tool_use": None, "is_finished": not calls, "index": 0,
               "finish_reason": "" if calls else "stop", "usage": None if calls else usage}
        for i, c in enumerate(calls):
            last = i == len(calls) - 1
            yield {"text": "", "index": 0, "is_finished": last, "finish_reason": "tool_calls" if last else "",
                   "usage": usage if last else None,
                   "tool_use": {"id": c.id, "type": "function", "index": i,
                                "function": {"name": c.function.name, "arguments": c.function.arguments}}}

    def streaming(self, *args, **kwargs):
        async def collect():
            return [chunk async for chunk in self.astreaming(*args, **kwargs)]
        yield from asyncio.run(collect())


handler = OCIResponses()

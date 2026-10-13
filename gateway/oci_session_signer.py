"""Sign every OCI call the gateway makes with the operator's OCI session.

LiteLLM's OCI provider signs with API-key fields or with an `oci_signer`
object. YAML cannot carry an object, so this callback attaches one to each
request after the router has chosen an OCI deployment and before the request
is sent (`async_pre_call_deployment_hook`); retries, fallbacks and classifier
calls go through it too.

The signer is rebuilt from the session token file at most once a minute, so
`oci session authenticate` refreshes the gateway without a restart. The token
and the key stay on the gateway host; applications only hold a gateway key.

On a local Kubernetes cluster the same session can be mounted from a Secret
(OCI_CONFIG_FILE names the mounted config); the refresh above picks up a
renewed token when the Secret is updated.

On OKE (OCI_AUTH=instance_principal) the gateway signs as the OKE node
it runs on instead: an IAM dynamic group and policy allow that node to use
Generative AI, and no key or token is stored in the cluster. The token is
refreshed before each call (see `signer()`).

    litellm_settings:
      callbacks: oci_session_signer.handler
"""

from __future__ import annotations

import os
import threading
import time

from litellm.integrations.custom_logger import CustomLogger

# In the official LiteLLM image the OCI SDK is installed beside the image's own
# packages (OCI_SDK_PATH); appended, not prepended, so the image's versions win.
if os.environ.get("OCI_SDK_PATH"):
    import sys

    sys.path.append(os.environ["OCI_SDK_PATH"])

PROFILE = os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT")
AUTH = os.environ.get("OCI_AUTH", "session")      # "session" or "instance_principal"
REFRESH_SECONDS = 60

# LiteLLM loads this module by path; its sibling with the Cohere request fix (a tool
# result as the last turn) is applied on import, so every Cohere call gets it.
import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oci_cohere_fix  # noqa: E402, F401


class OCISessionSigner(CustomLogger):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._signer = None
        self._loaded_at = 0.0

    def signer(self):
        with self._lock:
            if AUTH == "instance_principal":
                if self._signer is None:
                    import oci

                    self._signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
                # The SDK refreshes the token (about 20 minutes) only in signer.__call__;
                # LiteLLM signs with do_request_sign(), which skips it, so every call
                # after the first token expired failed with 401. Refresh here: it is a
                # cached read until the token is near expiry.
                self._signer._reset_signers()
                return self._signer
            if self._signer is None or time.monotonic() - self._loaded_at > REFRESH_SECONDS:
                import oci

                config = oci.config.from_file(file_location=os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"),
                                              profile_name=PROFILE)
                with open(os.path.expanduser(config["security_token_file"])) as fh:
                    token = fh.read().strip()
                key = oci.signer.load_private_key_from_file(os.path.expanduser(config["key_file"]))
                self._signer = oci.auth.signers.SecurityTokenSigner(token, key)
                self._loaded_at = time.monotonic()
            return self._signer

    async def async_pre_call_deployment_hook(self, kwargs, call_type):
        model = str(kwargs.get("model") or "")
        if model.startswith("oci/") or kwargs.get("custom_llm_provider") == "oci":
            kwargs["oci_signer"] = self.signer()
            # OCI serves the GPT-6 models with reasoning on by default and then refuses
            # function tools ("Function tools with reasoning_effort are not supported");
            # with reasoning_effort "none" they call tools. Only for requests that carry
            # tools, so plain requests keep the default reasoning the trial measured.
            if "openai.gpt-6" in model and (kwargs.get("tools") or (kwargs.get("optional_params") or {}).get("tools")):
                kwargs["reasoning_effort"] = "none"
                if isinstance(kwargs.get("optional_params"), dict):
                    kwargs["optional_params"]["reasoning_effort"] = "none"
        return kwargs


handler = OCISessionSigner()

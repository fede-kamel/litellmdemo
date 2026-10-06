"""Sign every OCI call the gateway makes with the operator's OCI session.

LiteLLM's OCI provider signs with API-key fields or with an `oci_signer`
object. YAML cannot carry an object, so this callback attaches one to each
request after the router has chosen an OCI deployment and before the request
is sent (`async_pre_call_deployment_hook`); retries, fallbacks and classifier
calls go through it too.

The signer is rebuilt from the session token file at most once a minute, so
`oci session authenticate` refreshes the gateway without a restart. The token
and the key stay on the gateway host; applications only hold a gateway key.

On Kubernetes (OCI_AUTH=instance_principal) the gateway signs as the OKE node
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

PROFILE = os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT")
AUTH = os.environ.get("OCI_AUTH", "session")      # "session" or "instance_principal"
REFRESH_SECONDS = 60


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

                config = oci.config.from_file(profile_name=PROFILE)
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
        return kwargs


handler = OCISessionSigner()

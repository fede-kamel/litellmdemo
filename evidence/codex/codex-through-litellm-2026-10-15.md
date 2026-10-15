# Codex with LiteLLM as its model provider, 2026-10-15 (a laptop gateway, API-key signing, the repo's gateway/config.yaml)

    codex exec -c model_providers.litellm.base_url="http://127.0.0.1:4400/v1" -c model_providers.litellm.wire_api="responses" \
      -c model_providers.litellm.env_key="LITELLM_KEY" -c model_provider=litellm -m oci-auto-trained "<request>"

## the gateway's ROUTE lines, in order (first attempts failed; each failure became a fix, see the commit)
ROUTE-FAIL key=master asked=oci-auto-trained model=cohere.command-a-03-2025 35.53s fallbacks=0 error="litellm.InternalServerError: OciException - { "code": "500", "message": "Internal Server Error." }
ROUTE-FAIL key=master asked=oci-auto-trained model=cohere.command-a-03-2025 35.66s fallbacks=0 error="litellm.InternalServerError: OciException - { "code": "500", "message": "Internal Server Error." }
ROUTE-FAIL key=master asked=oci-auto-trained model=google.gemini-2.5-flash 0.34s fallbacks=1 error="litellm.BadRequestError: OciException - { "code": "400", "message": "{\n  \"error\": {\n    \"code\"
ROUTE-FAIL key=master asked=oci-auto-trained model=google.gemini-2.5-flash 0.34s fallbacks=1 error="litellm.BadRequestError: OciException - { "code": "400", "message": "{\n  \"error\": {\n    \"code\"
ROUTE key=master asked=oci-auto-trained model=openai.gpt-5.4-mini 38.84s $0.000176 tokens=0/39 fallbacks=2

## the router's decisions for the race fix
CODE model: code (every turn)

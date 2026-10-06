# The OpenShell sandbox image for the routing control room's agent.
# Only the agent's own dependencies: no classifier, no OCI credentials, no model
# keys. The provider profile names /usr/local/bin/python3.12 as the one binary
# allowed to reach the LiteLLM gateway.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN useradd --create-home --uid 1500 sandbox
USER sandbox
WORKDIR /sandbox

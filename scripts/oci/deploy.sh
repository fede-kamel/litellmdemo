#!/usr/bin/env bash
# Deploy the gateway and the classifier to the demo's OKE cluster.
#
#   scripts/oci/deploy.sh             # build ConfigMaps from this repo, apply, wait
#   scripts/oci/deploy.sh --forward   # then port-forward the gateway to 127.0.0.1:4100
#
# Targets only the kubeconfig scripts/oci/up.sh wrote for the cluster it
# created. The master key comes from ~/.config/litellmdemo/master_key and the
# compartment from the state file; both go into one Kubernetes Secret.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"
export KUBECONFIG="$CONF_DIR/kubeconfig"
[[ -f "$KUBECONFIG" ]] || { echo "ABORT: $KUBECONFIG not found; run scripts/oci/up.sh" >&2; exit 1; }
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore
NS=litellmdemo
COMP="$(python3 -c "import json; print(json.load(open('$CONF_DIR/oci-state.json'))['compartment'])")"
k() { kubectl "$@"; }
apply_cm() {  # server-side: client-side apply keeps a copy in a 256 KB annotation, too small for the ladder
  k create configmap "$1" -n "$NS" "${@:2}" --dry-run=client -o yaml | k apply --server-side --force-conflicts -f - >/dev/null
}

k apply -f "$ROOT/deploy/k8s/litellmdemo.yaml" >/dev/null
apply_cm requirements --from-file="$ROOT/deploy/requirements/classifier.txt" --from-file="$ROOT/deploy/requirements/gateway.txt"
apply_cm classifier-code --from-file="$ROOT/classifier/__init__.py" --from-file="$ROOT/classifier/router_model.py" \
  --from-file="$ROOT/classifier/serve.py" --from-file="$ROOT/classifier/ladder.py" \
  --from-file="$ROOT/classifier/model/head.joblib" --from-file="$ROOT/classifier/model/ladder.npz" \
  --from-file="$ROOT/classifier/model/meta.json"
apply_cm gateway-code --from-file="$ROOT/gateway/config.yaml" --from-file="$ROOT/gateway/oci_session_signer.py" \
  --from-file="$ROOT/gateway/trained_classifier.py" --from-file="$ROOT/gateway/route_headers.py"
# --from-file keeps the key file's trailing newline, and LiteLLM would then
# never match the master key; strip it through a private temp file.
KEYTMP="$(mktemp)"; PGTMP="$(mktemp)"; URLTMP="$(mktemp)"; chmod 600 "$KEYTMP" "$PGTMP" "$URLTMP"
trap 'rm -f "$KEYTMP" "$PGTMP" "$URLTMP"' EXIT
tr -d '\r\n' < "$CONF_DIR/master_key" > "$KEYTMP"
# LiteLLM's database password: generated once, kept in a 0600 file, never printed.
if [[ ! -s "$CONF_DIR/postgres_password" ]]; then
  ( umask 077; python3 -c "import secrets; print(secrets.token_hex(24))" > "$CONF_DIR/postgres_password" )
fi
tr -d '\r\n' < "$CONF_DIR/postgres_password" > "$PGTMP"
printf 'postgresql://litellm:%s@postgres:5432/litellm' "$(cat "$PGTMP")" > "$URLTMP"
k create secret generic gateway -n "$NS" --from-file=master_key="$KEYTMP" \
  --from-literal=compartment_id="$COMP" --from-file=postgres_password="$PGTMP" --from-file=database_url="$URLTMP" \
  --dry-run=client -o yaml | k apply -f - >/dev/null
# ConfigMaps do not restart pods by themselves: stamp each pod template with a
# hash of what it mounts, so pods restart exactly when their code or config changes.
stamp() {  # deployment files...
  local h; h="$(cat "${@:2}" | shasum -a 256 | cut -c1-16)"
  k patch deployment "$1" -n "$NS" --type merge \
    -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"litellmdemo/config-hash\":\"$h\"}}}}}" >/dev/null
}
stamp route-classifier "$ROOT"/deploy/requirements/classifier.txt "$ROOT"/classifier/{__init__.py,router_model.py,serve.py,ladder.py} "$ROOT"/classifier/model/*
stamp litellm-gateway "$ROOT"/deploy/requirements/gateway.txt "$ROOT"/gateway/{config.yaml,oci_session_signer.py,trained_classifier.py,route_headers.py} "$KEYTMP" "$URLTMP" <(echo "$COMP")
stamp postgres "$PGTMP"
echo "applied; waiting for both deployments (first start installs packages: a few minutes)"
k rollout status -n "$NS" deployment/postgres --timeout=10m
k rollout status -n "$NS" deployment/route-classifier --timeout=15m
k rollout status -n "$NS" deployment/litellm-gateway --timeout=15m

# The OpenShell agent's LiteLLM virtual key: may call only the three routers and the
# two demo lanes (oci-chat: tag routing, oci-flaky: fallback), has a budget and a
# rate limit. Issued inside the gateway pod with the master key from
# the pod's own environment; the key goes straight into a 0600 file.
AGENT_KEY="$CONF_DIR/agent_key"
AGENT_MODELS='["oci-auto-trained", "oci-auto", "oci-auto-llm", "oci-chat", "oci-flaky"]'
issue_key() {
  k exec -n "$NS" deploy/litellm-gateway -c gateway -- env AGENT_MODELS="$AGENT_MODELS" python3 -c '
import json, os, urllib.request
base, master = "http://127.0.0.1:4000", os.environ["LITELLM_MASTER_KEY"]
def call(path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + master, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))
old = [k for k in call("/key/list?key_alias=openshell-agent&return_full_object=true").get("keys", [])]
tokens = [k["token"] for k in old if isinstance(k, dict) and k.get("token")]
if tokens:
    call("/key/delete", {"keys": tokens})
new = call("/key/generate", {"key_alias": "openshell-agent", "models": json.loads(os.environ["AGENT_MODELS"]),
                             "max_budget": 5, "budget_duration": "30d", "rpm_limit": 30,
                             "metadata": {"owner": "OpenShell sandbox: the routing control room agent"}})
print(new["key"], end="")' </dev/null
}
key_works() {
  [[ -s "$AGENT_KEY" ]] || return 1
  k exec -n "$NS" deploy/litellm-gateway -c gateway -i -- python3 -c '
import sys, urllib.request
key = sys.stdin.read().strip()
req = urllib.request.Request("http://127.0.0.1:4000/key/info", headers={"Authorization": "Bearer " + key})
sys.exit(0 if urllib.request.urlopen(req, timeout=15).status == 200 else 1)' < "$AGENT_KEY" >/dev/null 2>&1
}
scope_key() {  # keep the existing key, enforce its allowed models
  k exec -n "$NS" deploy/litellm-gateway -c gateway -i -- env AGENT_MODELS="$AGENT_MODELS" python3 -c '
import json, os, sys, urllib.request
key = sys.stdin.read().strip()
req = urllib.request.Request("http://127.0.0.1:4000/key/update", method="POST",
    data=json.dumps({"key": key, "models": json.loads(os.environ["AGENT_MODELS"])}).encode(),
    headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"], "Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=15)' < "$AGENT_KEY" >/dev/null
}
if key_works; then
  scope_key && echo "agent key: still valid, models enforced ($AGENT_KEY)"
else
  ( umask 077; issue_key > "$AGENT_KEY.new" ) && [[ -s "$AGENT_KEY.new" ]] && mv "$AGENT_KEY.new" "$AGENT_KEY" \
    && echo "agent key: issued (openshell-agent: 3 routers + 2 demo lanes, \$5 / 30 days, 30 rpm) -> $AGENT_KEY" \
    || { rm -f "$AGENT_KEY.new"; echo "ABORT: could not issue the agent key" >&2; exit 1; }
fi
k get pods -n "$NS" -o wide
if [[ "${1:-}" == "--forward" ]]; then
  echo "gateway on http://127.0.0.1:4100  (LITELLM_GATEWAY=http://127.0.0.1:4100)"
  exec kubectl port-forward -n "$NS" svc/litellm-gateway 4100:4000
fi
echo "DEPLOY OK"

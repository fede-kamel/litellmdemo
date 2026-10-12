#!/usr/bin/env bash
# Is the cloud demo ready? Every piece, checked from the outside, with the fix for anything that is not.
#
#   scripts/oci/preflight.sh        # ends with "CLOUD PREFLIGHT OK (n/n)" or the fixes to run
#
# Checks: the cluster's pods, the gateway and its database (from inside the VCN),
# the VM's services (OpenShell gateway, control room) and the sandbox, the API
# gateway's deployment, and then what a visitor sees at the public URL: the
# health, the primary gateway, the sandbox and the agent's key, a live stream,
# and recorded runs for replay. Read-only: no model call, nothing paid.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"
STATE="$CONF_DIR/oci-state.json"; DEPLOY="$CONF_DIR/deploy.json"
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$STATE" "$1"; }
cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$DEPLOY" "$1"; }
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore KUBECONFIG="$CONF_DIR/kubeconfig"
o() { oci "$@" --profile "$(cfg profile)" --region "$(cfg region)"; }
HOST="$(get api_hostname)"; URL="https://$HOST"
SSH_KEY="${LITELLMDEMO_SSH_KEY:-$HOME/.ssh/id_ed25519}"
PUB="$(o compute instance list-vnics --instance-id "$(get control_instance)" --query 'data[0]."public-ip"' --raw-output 2>/dev/null)"
vm() { ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR -o ConnectTimeout=10 "opc@$PUB" "export XDG_RUNTIME_DIR=/run/user/\$(id -u); $*"; }
pass=0; total=0; fixes=()
check() {  # name, fix, command...
  local name="$1" fix="$2"; shift 2; total=$((total + 1))
  if out="$("$@" 2>&1)"; then pass=$((pass + 1)); printf '\033[32mPASS\033[0m  %s%s\n' "$name" "${out:+  ($out)}"
  else printf '\033[31mFAIL\033[0m  %s%s\n' "$name" "${out:+  ($out)}"; fixes+=("$fix"); fi
}

pods() {
  local s; s="$(kubectl get pods -n litellmdemo --no-headers --request-timeout=15s 2>/dev/null)"
  for app in litellm-gateway route-classifier postgres; do echo "$s" | grep -q "^$app-.* 1/1 .*Running" || { echo "$app not ready"; return 1; }; done
  echo "litellm-gateway, route-classifier, postgres ready"
}
gateway_db() {  # the gateway's readiness, from inside the VCN
  vm "curl -sf -m 10 http://$(get control_gateway_host):30400/health/readiness" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('db', d.get('db')); sys.exit(0 if d.get('db')=='connected' else 1)"
}
services() { vm "systemctl --user is-active openshell-gateway litellmdemo-control" | tr '\n' ' ' | grep -q "active active" && echo "openshell-gateway, litellmdemo-control active"; }
sandbox_ready() { local out; out="$(vm "openshell sandbox get litellmdemo-agent </dev/null" 2>/dev/null)"; [[ "$out" == *"Phase: Ready"* ]] && echo "litellmdemo-agent Ready"; }
edge() { local s; s="$(o api-gateway deployment get --deployment-id "$(get api_deployment)" --query 'data."lifecycle-state"' --raw-output 2>/dev/null)"; echo "deployment $s"; [[ "$s" == ACTIVE ]]; }
health() { curl -sf -m 15 -o /dev/null "$URL/api/health" && echo "$HOST answers"; }
primary() { curl -sf -m 15 "$URL/api/gateways" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['role'], d['cluster']); sys.exit(0 if d['role']=='primary' and d['cluster']=='oke' else 1)"; }
agent() {
  curl -sf -m 60 "$URL/api/sandbox" | python3 -c "
import json, sys
d = json.load(sys.stdin); k = d.get('key') or {}
print(('sandbox ready' if d['ready'] else 'sandbox not ready') + (f\", {k['key_alias']}: \${k['spend']:.3f} of \${k['max_budget']}\" if k else ', no key'))
sys.exit(0 if d['ready'] and k and k['spend'] < k['max_budget'] * 0.9 else 1)"
}
stream() {  # read the stream for 8 s (curl then times out on purpose), and look for an event or a keep-alive
  local out; out="$(curl -sN -m 8 "$URL/api/console" 2>/dev/null | head -c 20000)"
  grep -qE "^(data: |: keep-alive)" <<<"$out" && echo "console streams through the API gateway"
}
recordings() { local n; n="$(vm "ls ~/litellmdemo/out/recordings 2>/dev/null | wc -l" | tr -d ' ')"; echo "$n recorded runs on the VM"; [[ "${n:-0}" -ge 5 ]]; }

check "OKE: the gateway, the classifier and Postgres" "scripts/oci/deploy.sh" pods
check "OKE: the gateway and its database, from the VCN" "kubectl rollout restart -n litellmdemo deploy/litellm-gateway   (KUBECONFIG=~/.config/litellmdemo/kubeconfig)" gateway_db
check "the VM: OpenShell gateway and control room services" "scripts/oci/control-deploy.sh" services
check "the VM: the agent's sandbox" "scripts/oci/control.sh ssh 'cd litellmdemo && scripts/openshell.sh down; scripts/openshell.sh up'   then scripts/oci/control-deploy.sh" sandbox_ready
check "API gateway deployment" "scripts/oci/edge.sh" edge
check "the public URL answers" "scripts/oci/edge.sh   (then the VM's firewall: port 8780 from 10.20.0.0/16)" health
check "public control room: primary gateway is OKE" "scripts/oci/control-deploy.sh   (LITELLM_GATEWAY in the service unit)" primary
check "public control room: sandbox ready, agent key within budget" "scripts/oci/deploy.sh (re-issues the key), then scripts/oci/control-deploy.sh" agent
check "a live stream through the API gateway" "scripts/oci/edge.sh   (read timeout 300 s; the control room sends a keep-alive every 5 s)" stream
check "recorded runs for replay, on the VM" "LITELLMDEMO_APP=$URL uv run python scripts/record_runs.py && scripts/oci/control-deploy.sh" recordings

echo
if [[ $pass == "$total" ]]; then echo "CLOUD PREFLIGHT OK ($pass/$total)  $URL"; exit 0; fi
echo "CLOUD PREFLIGHT FAILED ($pass/$total). Fix, in order:"
for f in "${fixes[@]}"; do echo "  - $f"; done
exit 1

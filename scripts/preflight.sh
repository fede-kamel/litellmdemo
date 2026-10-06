#!/usr/bin/env bash
# Is the demo ready? Every piece, checked end to end, with the fix for anything that is not.
#
#   scripts/preflight.sh        # ends with "PREFLIGHT OK (n/n)" or the fixes to run
#
# Checks: the OCI session, Rancher Desktop and its Kubernetes, the LiteLLM gateway
# (signing to OCI, its database, the agent's key), the classifier service, the
# OpenShell gateway and sandbox (a real request through it, and the escape probe),
# the fallback laptop gateway, the control room, and recorded runs for replay.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"
export PATH="$HOME/.rd/bin:$PATH"
PROFILE="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['oci_profile'])" "$CONF_DIR/config.json")"
pass=0; total=0; fixes=()
check() {  # name, fix, command...
  local name="$1" fix="$2"; shift 2; total=$((total + 1))
  if out="$("$@" 2>&1)"; then pass=$((pass + 1)); printf '\033[32mPASS\033[0m  %s%s\n' "$name" "${out:+  ($out)}"
  else printf '\033[31mFAIL\033[0m  %s%s\n' "$name" "${out:+  ($out)}"; fixes+=("$fix"); fi
}

session() {
  python3 - "$PROFILE" <<'PY'
import base64, configparser, json, os, sys, time
c = configparser.ConfigParser(); c.read(os.path.expanduser("~/.oci/config"))
t = open(os.path.expanduser(c[sys.argv[1]]["security_token_file"])).read().split(".")[1]; t += "=" * (-len(t) % 4)
left = int((json.loads(base64.urlsafe_b64decode(t))["exp"] - time.time()) / 60)
print(f"{left} min left" + ("  (at its maximum lifetime: a refresh cannot extend it)" if 0 < left < 45 else "")); sys.exit(0 if left > 30 else 1)
PY
}
rd() { rdctl shell -- true >/dev/null 2>&1 && kubectl --context rancher-desktop get nodes --request-timeout=10s -o name | head -1; }
pods() {
  local s; s="$(kubectl --context rancher-desktop get pods -n litellmdemo --no-headers --request-timeout=10s 2>/dev/null)"
  for app in litellm-gateway route-classifier postgres; do echo "$s" | grep -q "^$app-.* 1/1 .*Running" || { echo "$app not ready"; return 1; }; done
  echo "litellm-gateway, route-classifier, postgres ready"
}
gateway_db() { curl -sf -m 10 http://127.0.0.1:30400/health/readiness | python3 -c "import json,sys; d=json.load(sys.stdin); print('db', d.get('db')); sys.exit(0 if d.get('db')=='connected' else 1)"; }
signs() {  # a real model call, signed with the session
  curl -sf -m 60 -o /dev/null -w "%{http_code}" http://127.0.0.1:30400/v1/chat/completions -H "Authorization: Bearer $(cat "$CONF_DIR/master_key")" \
    -H 'Content-Type: application/json' -d '{"model":"oci-fast","max_tokens":5,"messages":[{"role":"user","content":"say ok"}]}'
}
codex() {   # the CODE route goes through the Responses provider (gateway/oci_responses.py)
  curl -sf -m 120 -D - -o /dev/null http://127.0.0.1:30400/v1/chat/completions -H "Authorization: Bearer $(cat "$CONF_DIR/master_key")" \
    -H 'Content-Type: application/json' -d '{"model":"oci-code","max_tokens":200,"messages":[{"role":"user","content":"Write is_even(n) in Python. Code only."}]}' \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="x-litellm-model-name"{m=$2} END{print m; exit (m ~ /codex/ ? 0 : 1)}'
}
agent_key() {
  [[ -s "$CONF_DIR/agent_key-local" ]] || { echo "no agent key file"; return 1; }
  curl -sf -m 10 "http://127.0.0.1:30400/key/info?key=$(cat "$CONF_DIR/agent_key-local")" -H "Authorization: Bearer $(cat "$CONF_DIR/master_key")" \
    | python3 -c "import json,sys; i=json.load(sys.stdin)['info']; print(f\"{i['key_alias']}: \${i['spend']:.3f} of \${i['max_budget']}\"); sys.exit(0 if i['spend'] < i['max_budget'] * 0.9 else 1)"
}
openshell_gw() { openshell sandbox list </dev/null >/dev/null 2>&1 && echo "gateway reachable"; }
sandbox_ready() {   # read all of the output first: grep -q would close the pipe early and pipefail would fail the check
  local out; out="$(openshell sandbox get litellmdemo-agent </dev/null 2>/dev/null)"; [[ "$out" == *"Phase: Ready"* ]] && echo "litellmdemo-agent Ready"
}
sandbox_ask() {
  "$ROOT/scripts/openshell.sh" ask '{"prompt":"What is 18 percent of 4,217.50?"}' 2>/dev/null \
    | python3 -c "import json,sys; ev=[json.loads(l) for l in sys.stdin if l.startswith('{')]; a=[e for e in ev if e['type']=='answer']; m=[e.get('deployment') for e in ev if e['type']=='llm']; print(f'answered via {m[-1] if m else None}' if a else 'no answer'); sys.exit(0 if a else 1)"
}
escape() {
  "$ROOT/scripts/openshell.sh" probe 2>/dev/null | python3 -c "import json,sys; t=[json.loads(l) for l in sys.stdin if l.startswith('{')]; r=sum(x['result'].startswith('REFUSED') for x in t); print(f'{r}/{len(t)} refused'); sys.exit(0 if t and r==len(t) else 1)"
}
laptop() { curl -sf -m 5 -o /dev/null http://127.0.0.1:4000/health/liveliness && echo "fallback on :4000"; }
ui() { curl -sf -m 5 http://127.0.0.1:8780/api/gateways | python3 -c "import json,sys; d=json.load(sys.stdin); print('primary', d['active']); sys.exit(0 if '30400' in d['active'] else 1)"; }
recordings() { n=$(ls "$ROOT/out/recordings" 2>/dev/null | wc -l | tr -d ' '); echo "$n recorded runs"; [[ "$n" -ge 5 ]]; }

check "OCI session, more than 30 min" "oci session authenticate --profile-name $PROFILE --region us-ashburn-1   (then scripts/local/push-session.sh); do it right before the talk" session
check "Rancher Desktop and its Kubernetes" "rdctl start   (or open Rancher Desktop), then scripts/demo-up.sh" rd
check "local cluster pods" "scripts/local/deploy.sh" pods
check "LiteLLM gateway and its database" "kubectl --context rancher-desktop rollout restart -n litellmdemo deploy/litellm-gateway" gateway_db
check "LiteLLM signs to OCI (a real call)" "scripts/local/push-session.sh   (a stale session in the cluster), then retry" signs
check "the CODE route answers with Codex" "kubectl --context rancher-desktop logs -n litellmdemo deploy/litellm-gateway -c gateway --tail=40" codex
check "the agent's virtual key" "scripts/local/deploy.sh   (re-issues it), then scripts/openshell.sh provider && scripts/openshell.sh down && scripts/openshell.sh up" agent_key
check "OpenShell gateway" "brew services restart openshell" openshell_gw
check "OpenShell sandbox" "scripts/openshell.sh up" sandbox_ready
check "a request through the sandbox" "scripts/openshell.sh down && scripts/openshell.sh up" sandbox_ask
check "the sandbox cannot escape" "scripts/openshell.sh provider && scripts/openshell.sh down && scripts/openshell.sh up" escape
check "fallback laptop gateway" "nohup scripts/gateway.sh > out/gateway.log 2>&1 &" laptop
check "control room on :8780, primary = local cluster" "scripts/demo-up.sh" ui
check "recorded runs for replay" "uv run python scripts/record_runs.py   (records every example and use case)" recordings

echo
if [[ $pass == "$total" ]]; then echo "PREFLIGHT OK ($pass/$total)"; exit 0; fi
echo "PREFLIGHT FAILED ($pass/$total). Fix, in order:"
for f in "${fixes[@]}"; do echo "  - $f"; done
exit 1

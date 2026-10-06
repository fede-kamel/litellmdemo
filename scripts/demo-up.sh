#!/usr/bin/env bash
# Bring the whole demo up on this laptop, in order, then run the preflight.
#
#   scripts/demo-up.sh          # idempotent: starts only what is not running
#   scripts/demo-down.sh        # stops the background processes it started
#
# Works on any network with a route to OCI: everything runs here (Rancher
# Desktop Kubernetes, OpenShell, the control room); the only outside services
# are OCI Generative AI and the OCI session's identity provider.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"; RUN="$CONF_DIR/run"; mkdir -p "$RUN" "$ROOT/out"
export PATH="$HOME/.rd/bin:$PATH"
step() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
running() { [[ -f "$RUN/$1.pid" ]] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }
start() {  # name, command...
  local name="$1"; shift
  if running "$name"; then echo "    $name already running"; return; fi
  nohup "$@" > "$ROOT/out/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"; echo "    $name started (log: out/$name.log)"
}

step "Rancher Desktop"
rdctl shell -- true >/dev/null 2>&1 || { rdctl start >/dev/null 2>&1 || true; }
for _ in $(seq 60); do kubectl --context rancher-desktop get nodes --request-timeout=5s >/dev/null 2>&1 && break; sleep 5; done

step "OCI session and its copy in the cluster"
start session-refresh "$ROOT/scripts/local/refresh.sh"
sleep 5

step "LiteLLM, the classifier and Postgres on the local cluster"
if ! kubectl --context rancher-desktop get deploy -n litellmdemo litellm-gateway >/dev/null 2>&1; then
  "$ROOT/scripts/local/deploy.sh"
else
  "$ROOT/scripts/local/push-session.sh"
  kubectl --context rancher-desktop rollout status -n litellmdemo deploy/litellm-gateway --timeout=10m
fi

step "OpenShell sandbox"
openshell sandbox list </dev/null >/dev/null 2>&1 || brew services restart openshell >/dev/null 2>&1
for _ in $(seq 30); do openshell sandbox list </dev/null >/dev/null 2>&1 && break; sleep 2; done
SB_STATE="$(openshell sandbox get litellmdemo-agent </dev/null 2>/dev/null)"
[[ "$SB_STATE" == *"Phase: Ready"* ]] || { "$ROOT/scripts/openshell.sh" down >/dev/null 2>&1; "$ROOT/scripts/openshell.sh" up; }

step "fallback laptop gateway and the control room"
curl -sf -m 3 -o /dev/null http://127.0.0.1:4000/health/liveliness || start laptop-gateway "$ROOT/scripts/gateway.sh"
if ! curl -sf -m 3 -o /dev/null http://127.0.0.1:8780/api/health; then
  (cd "$ROOT" && LITELLM_GATEWAY=http://127.0.0.1:30400 LITELLM_GATEWAY_FALLBACK=http://127.0.0.1:4000 LITELLMDEMO_CLUSTER=local \
    start control-room "$ROOT/.venv/bin/uvicorn" ui.server:app --host 127.0.0.1 --port 8780 --timeout-graceful-shutdown 3)
fi
for _ in $(seq 60); do curl -sf -m 3 -o /dev/null http://127.0.0.1:8780/api/health && curl -sf -m 3 -o /dev/null http://127.0.0.1:4000/health/liveliness && break; sleep 2; done

step "recorded runs for replay (once, while the network is good)"
[[ "$(ls "$ROOT/out/recordings" 2>/dev/null | wc -l | tr -d ' ')" -ge 5 ]] || (cd "$ROOT" && "$ROOT/.venv/bin/python" scripts/record_runs.py)

step "preflight"
"$ROOT/scripts/preflight.sh"
echo "control room: http://127.0.0.1:8780"

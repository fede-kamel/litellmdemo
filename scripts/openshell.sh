#!/usr/bin/env bash
# The control room's agent inside an NVIDIA OpenShell sandbox.
#
#   scripts/openshell.sh provider        create or refresh the provider from ~/.config/litellmdemo/agent_key
#   scripts/openshell.sh up              create the sandbox, upload the agent, wait until it is ready
#   scripts/openshell.sh sync            upload the agent code again (after a change)
#   scripts/openshell.sh ask '<json>'    run one request, print one JSON event per line
#   scripts/openshell.sh probe           try to reach OCI and a model vendor directly: both must be refused
#   scripts/openshell.sh status | down
#
# What the sandbox holds and can reach:
#   - LITELLM_API_KEY: an OpenShell placeholder. Provider `litellm-agent` keeps the
#     agent's LiteLLM virtual key in the OpenShell gateway; the proxy swaps it in
#     only on requests to the LiteLLM gateway.
#   - egress: POST /v1/chat/completions and GET /v1/models on the LiteLLM gateway
#     (the local Kubernetes node port by default), for /usr/local/bin/python3.12 only. Nothing else.
#   - no OCI credential and no model key of any kind.
# Every exec reads stdin from /dev/null (OpenShell 0.1.2 reads piped stdin to EOF).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="${LITELLMDEMO_SANDBOX:-litellmdemo-agent}"
IMAGE="${LITELLMDEMO_SANDBOX_IMAGE:-litellmdemo-agent:0.1}"
PROVIDER="${LITELLMDEMO_PROVIDER:-litellm-agent}"
# The gateway the agent may reach: the local Kubernetes node's node port unless set.
if [[ -z "${LITELLMDEMO_SANDBOX_GATEWAY:-}" ]]; then
  NODE_IP="$(kubectl --context rancher-desktop get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)"
  LITELLMDEMO_SANDBOX_GATEWAY="http://${NODE_IP:-192.168.5.15}:30400"
fi
GATEWAY_URL="$LITELLMDEMO_SANDBOX_GATEWAY"
GATEWAY_HOSTPORT="${GATEWAY_URL#http://}"
KEYFILE="${LITELLMDEMO_AGENT_KEY_FILE:-$HOME/.config/litellmdemo/agent_key-local}"
say() { printf '%s\n' "$*" >&2; }
step() { printf '\033[1;32m$\033[0m %s\n' "$*" >&2; }
die() { say "ABORT: $*"; exit 1; }
exists() { openshell sandbox get "$SB" </dev/null >/dev/null 2>&1; }

provider() {
  [[ -s "$KEYFILE" ]] || die "$KEYFILE is missing: run scripts/oci/deploy.sh"
  # import never overwrites a profile and update needs its resource version: the
  # demo owns both, so replace them (the provider first, it depends on the profile).
  openshell provider delete "$PROVIDER" </dev/null >/dev/null 2>&1 || true
  openshell provider profile delete litellm-gateway --global </dev/null >/dev/null 2>&1 || true
  local rendered; rendered="$(mktemp -d)/litellm-gateway.yaml"
  sed -e "s|__GATEWAY_HOST__|${GATEWAY_HOSTPORT%%:*}|" -e "s|__GATEWAY_PORT__|${GATEWAY_HOSTPORT##*:}|" \
    "$ROOT/sandbox/profile/litellm-gateway.yaml" > "$rendered"
  openshell provider profile import --file "$rendered" --global </dev/null >&2
  openshell provider delete "$PROVIDER" </dev/null >/dev/null 2>&1 || true
  # The key goes from its 0600 file into this process's environment; the CLI reads
  # it by name. It is never on a command line and never printed.
  LITELLM_API_KEY="$(cat "$KEYFILE")" openshell provider create --name "$PROVIDER" --type litellm-gateway \
    --credential LITELLM_API_KEY </dev/null >&2
}

up() {
  if exists; then say "sandbox $SB exists"; return 0; fi
  openshell provider get "$PROVIDER" </dev/null >/dev/null 2>&1 || provider
  step "openshell sandbox create --name $SB --from $IMAGE --provider $PROVIDER --policy sandbox/policy.yaml"
  openshell sandbox create --name "$SB" --from "$IMAGE" --provider "$PROVIDER" --policy "$ROOT/sandbox/policy.yaml" \
    --label app=litellmdemo --no-auto-providers --detach -- sleep infinity </dev/null >&2 || die "could not create $SB"
  for _ in $(seq 1 60); do
    openshell sandbox exec --name "$SB" -- /usr/local/bin/python3.12 -c "print('ready')" </dev/null 2>/dev/null | grep -q ready && break
    sleep 2
  done
  # OpenShell 0.1.2 reloads the provider environment on its first settings poll and
  # closes connections opened before it (NVIDIA/OpenShell#3994, fixed upstream).
  step "waiting for the sandbox's first policy reload"
  for _ in $(seq 1 30); do
    openshell logs "$SB" -n 400 --source sandbox </dev/null 2>/dev/null | grep -q "Settings poll: config change detected" && break
    sleep 1
  done
  sync
  say "sandbox $SB ready"
}

sync() {
  exists || die "no sandbox $SB: run scripts/openshell.sh up"
  local work; work="$(mktemp -d)"
  mkdir -p "$work/app/app" "$work/app/classifier"
  cp "$ROOT"/app/{__init__.py,agent.py,tools.py,sandbox_run.py} "$work/app/app/"
  cp "$ROOT"/classifier/{__init__.py,gateway_client.py} "$work/app/classifier/"
  step "openshell sandbox upload $SB app/ /sandbox/app   (the agent: app/ and classifier/gateway_client.py)"
  openshell sandbox upload "$SB" "$work/app" /sandbox </dev/null >&2 || die "upload failed"
  rm -rf "$work"
}

ask() {
  exists || die "no sandbox $SB: run scripts/openshell.sh up"
  local b64 arg; b64="$(printf '%s' "$1" | base64 | tr -d '\n')"
  arg="$b64"
  if (( ${#b64} > 100000 )); then
    # One argument may not exceed 128 KiB on Linux: hand large requests over as a file.
    local work name; work="$(mktemp -d)"; name="req-$(date +%s%N).b64"
    mkdir -p "$work/req"; printf '%s' "$b64" > "$work/req/$name"
    openshell sandbox upload "$SB" "$work/req" /sandbox </dev/null >/dev/null || die "upload failed"
    rm -rf "$work"; arg="@/sandbox/req/$name"
  fi
  openshell sandbox exec --name "$SB" --workdir /sandbox/app -- /bin/sh -c \
    "LITELLM_GATEWAY='$GATEWAY_URL' exec /usr/local/bin/python3.12 -m app.sandbox_run \"\$1\"" sh "$arg" </dev/null
}

probe() {
  exists || die "no sandbox $SB: run scripts/openshell.sh up"
  # Three tries from inside: OCI Generative AI directly, a model vendor, and the
  # gateway's admin API. The policy must refuse all three.
  openshell sandbox exec --name "$SB" -- /usr/local/bin/python3.12 -c '
import json, urllib.request, urllib.error
tries = [("OCI Generative AI, directly", "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/20231130/actions/chat", "POST"),
         ("a model vendor (api.openai.com)", "https://api.openai.com/v1/models", "GET"),
         ("the gateway admin API (/key/generate)", "'"$GATEWAY_URL"'/key/generate", "POST")]
for name, url, method in tries:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=b"{}" if method == "POST" else None, method=method), timeout=8)
        print(json.dumps({"target": name, "result": "REACHED", "status": r.status}))
    except urllib.error.HTTPError as e:
        print(json.dumps({"target": name, "result": "REFUSED by policy" if e.code == 403 else "HTTP %d" % e.code, "status": e.code}))
    except Exception as e:
        print(json.dumps({"target": name, "result": "REFUSED: no connection", "detail": type(e).__name__}))
' </dev/null
}

status() { openshell sandbox list </dev/null; }
down() { exists && { step "openshell sandbox delete $SB"; openshell sandbox delete "$SB" </dev/null >&2; } || say "no sandbox $SB"; }

case "${1:-}" in
  provider) provider ;;
  up) up ;;
  sync) sync ;;
  ask) shift; ask "$1" ;;
  probe) probe ;;
  status) status ;;
  down) down ;;
  *) die "usage: scripts/openshell.sh provider | up | sync | ask '<json>' | probe | status | down" ;;
esac

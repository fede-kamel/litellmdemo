#!/usr/bin/env bash
# Put the control room and the agent's OpenShell sandbox on the VM that
# scripts/oci/control.sh created, and start them as services there.
#
#   scripts/oci/control-deploy.sh      # idempotent; rerun after a code change
#
# The VM gets: the repository (no .venv, no node_modules), the built web front
# end, the master key and the agent's OKE virtual key (0600 files, copied over
# SSH, never on a command line), a kubeconfig for the read-only control-room
# service account on the cluster's private endpoint, kubectl, the sandbox image
# (built there with Podman), the OpenShell provider and sandbox, and a systemd
# user unit for the control room on port 8780.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"
STATE="$CONF_DIR/oci-state.json"
DEPLOY="$CONF_DIR/deploy.json"
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$STATE" "$1"; }
put() { python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d[sys.argv[2]]=sys.argv[3]; json.dump(d, open(p,'w'), indent=1)" "$STATE" "$1" "$2"; }
cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$DEPLOY" "$1"; }
say() { printf '\033[1;32m$\033[0m %s\n' "$*" >&2; }   # stderr: some callers capture stdout
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore
export KUBECONFIG="$CONF_DIR/kubeconfig"
SSH_KEY="${LITELLMDEMO_SSH_KEY:-$HOME/.ssh/id_ed25519}"
PUB="$(oci compute instance list-vnics --instance-id "$(get control_instance)" --profile "$(cfg profile)" --region "$(cfg region)" \
       --query 'data[0]."public-ip"' --raw-output)"
SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR "opc@$PUB")
for f in master_key agent_key; do [[ -s "$CONF_DIR/$f" ]] || { echo "ABORT: $CONF_DIR/$f missing: run scripts/oci/deploy.sh" >&2; exit 1; }; done

NODE_IP="$(kubectl get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"
GW="http://$NODE_IP:30400"
put control_gateway_host "$NODE_IP"
API="$(oci ce cluster get --cluster-id "$(get cluster)" --profile "$(cfg profile)" --region "$(cfg region)" \
       --query 'data.endpoints."private-endpoint"' --raw-output)"

say "build the web front end"
(cd "$ROOT/web" && npm run build >/dev/null)

say "copy the repository to the VM"
rsync -az --delete -e "ssh -i $SSH_KEY -o LogLevel=ERROR" \
  --exclude .venv --exclude node_modules --exclude out --exclude .git --exclude __pycache__ --exclude 'web/node_modules' \
  "$ROOT/" "opc@$PUB:litellmdemo/"

say "copy the keys and a read-only kubeconfig ($API)"
TOKEN_CA="$(mktemp -d)"; trap 'rm -rf "$TOKEN_CA"' EXIT
kubectl -n litellmdemo get secret control-room-token -o jsonpath='{.data.token}' | base64 -d > "$TOKEN_CA/token"
kubectl -n litellmdemo get secret control-room-token -o jsonpath='{.data.ca\.crt}' > "$TOKEN_CA/ca"
python3 - "$TOKEN_CA" "$API" <<'PY'
import sys, yaml, os
d, api = sys.argv[1], sys.argv[2]
cfg = {"apiVersion": "v1", "kind": "Config", "current-context": "oke",
       "clusters": [{"name": "oke", "cluster": {"server": f"https://{api}", "certificate-authority-data": open(f"{d}/ca").read()}}],
       "users": [{"name": "control-room", "user": {"token": open(f"{d}/token").read()}}],
       "contexts": [{"name": "oke", "context": {"cluster": "oke", "user": "control-room", "namespace": "litellmdemo"}}]}
fd = os.open(f"{d}/kubeconfig", os.O_WRONLY | os.O_CREAT, 0o600)
with os.fdopen(fd, "w") as f: yaml.safe_dump(cfg, f)
PY
"${SSH[@]}" 'mkdir -p ~/.config/litellmdemo && chmod 700 ~/.config/litellmdemo'
scp -q -i "$SSH_KEY" -o LogLevel=ERROR "$CONF_DIR/master_key" "$CONF_DIR/agent_key" "$TOKEN_CA/kubeconfig" "opc@$PUB:.config/litellmdemo/"
echo '{"oci_profile": "", "oci_auth": "instance_principal", "oci_region": "us-chicago-1"}' | "${SSH[@]}" 'cat > ~/.config/litellmdemo/config.json; chmod 600 ~/.config/litellmdemo/*'

say "on the VM: Python, kubectl, the OpenShell CLI registration, the sandbox image"
"${SSH[@]}" bash -s <<'VM'
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
if ! command -v uv >/dev/null && [[ ! -x ~/.local/bin/uv ]]; then
  V=0.9.5; A=uv-aarch64-unknown-linux-gnu.tar.gz
  curl -fsSLO "https://github.com/astral-sh/uv/releases/download/$V/$A" && curl -fsSLO "https://github.com/astral-sh/uv/releases/download/$V/$A.sha256"
  sha256sum -c "$A.sha256" >/dev/null && tar xzf "$A" && mkdir -p ~/.local/bin && mv uv-aarch64-unknown-linux-gnu/uv* ~/.local/bin/ && rm -rf "$A"*  uv-aarch64-unknown-linux-gnu
fi
if ! command -v kubectl >/dev/null; then
  K=v1.34.1
  curl -fsSLO "https://dl.k8s.io/release/$K/bin/linux/arm64/kubectl" && curl -fsSLO "https://dl.k8s.io/release/$K/bin/linux/arm64/kubectl.sha256"
  echo "$(cat kubectl.sha256)  kubectl" | sha256sum -c >/dev/null && sudo install -m 0755 kubectl /usr/local/bin/kubectl && rm -f kubectl kubectl.sha256
fi
cd ~/litellmdemo && ~/.local/bin/uv sync --quiet
[[ "$(openshell status </dev/null 2>/dev/null)" == *Connected* ]] || openshell gateway add --local https://127.0.0.1:17670 </dev/null >/dev/null
podman build -q -t litellmdemo-agent:0.1 sandbox/ >/dev/null
KUBECONFIG=~/.config/litellmdemo/kubeconfig kubectl get pods >/dev/null
VM

say "the sandbox (provider, policy, agent) against $GW"
"${SSH[@]}" "cd ~/litellmdemo && export XDG_RUNTIME_DIR=/run/user/\$(id -u) LITELLMDEMO_SANDBOX_GATEWAY=$GW \
  LITELLMDEMO_AGENT_KEY_FILE=\$HOME/.config/litellmdemo/agent_key LITELLMDEMO_SANDBOX_IMAGE=localhost/litellmdemo-agent:0.1 \
  && { openshell provider get litellm-agent </dev/null >/dev/null 2>&1 || scripts/openshell.sh provider; } \
  && scripts/openshell.sh up && scripts/openshell.sh sync"

say "the control room as a service on :8780"
"${SSH[@]}" "mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/litellmdemo-control.service" <<UNIT
[Unit]
Description=LiteLLM routing demo: the control room
After=openshell-gateway.service

[Service]
WorkingDirectory=%h/litellmdemo
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=LITELLM_GATEWAY=$GW
Environment=LITELLMDEMO_CLUSTER=oke
Environment=LITELLMDEMO_SANDBOX_GATEWAY=$GW
Environment=LITELLMDEMO_SANDBOX_GATEWAY_FROM_HOST=$GW
Environment=LITELLMDEMO_AGENT_KEY_FILE=%h/.config/litellmdemo/agent_key
Environment=LITELLMDEMO_SANDBOX_IMAGE=localhost/litellmdemo-agent:0.1
ExecStart=%h/litellmdemo/.venv/bin/uvicorn ui.server:app --host 0.0.0.0 --port 8780 --timeout-graceful-shutdown 3
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
"${SSH[@]}" 'export XDG_RUNTIME_DIR=/run/user/$(id -u); systemctl --user daemon-reload && systemctl --user enable litellmdemo-control >/dev/null 2>&1; systemctl --user restart litellmdemo-control'
for _ in $(seq 30); do "${SSH[@]}" 'curl -sf -m 3 -o /dev/null http://127.0.0.1:8780/api/health' && break; sleep 3; done
"${SSH[@]}" 'curl -sf -m 3 -o /dev/null http://127.0.0.1:8780/api/health' \
  || { echo "ABORT: the control room does not answer on :8780 (on the VM: journalctl --user -u litellmdemo-control -n 40)" >&2; exit 1; }
"${SSH[@]}" 'curl -sf -m 5 http://127.0.0.1:8780/api/gateways; echo; curl -sf -m 30 http://127.0.0.1:8780/api/sandbox; echo'
echo "CONTROL DEPLOY OK  (control room on $(get control_private_ip):8780 inside the VCN)"

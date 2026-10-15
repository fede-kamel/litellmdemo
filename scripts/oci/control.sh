#!/usr/bin/env bash
# The control room's VM in OCI, beside the OKE cluster: one Ampere A1 instance
# that runs the OpenShell gateway (Docker driver), the agent's sandbox and the
# control room. Nothing of the demo runs on the operator's machine.
#
#   scripts/oci/up.sh            # first: the VCN, the cluster, the node
#   scripts/oci/control.sh       # idempotent: the VM, its NSG, the gateway's VCN node port
#   scripts/oci/control.sh ssh   # a shell on the VM
#   scripts/oci/down.sh          # deletes the VM and the NSG too
#
# Inputs: ~/.config/litellmdemo/deploy.json (profile, region; control_ocpus,
# control_memory_gbs optional). OCIDs go to ~/.config/litellmdemo/oci-state.json.
# SSH is admitted from api_allow_cidr only; the control room's port only from
# inside the VCN (API Gateway is its one public face).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"
DEPLOY="$CONF_DIR/deploy.json"
STATE="$CONF_DIR/oci-state.json"
[[ -f "$STATE" ]] || { echo "ABORT: $STATE not found: run scripts/oci/up.sh first" >&2; exit 1; }
cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], sys.argv[3]))" "$DEPLOY" "$1" "${2:-}"; }
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$STATE" "$1"; }
put() { python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d[sys.argv[2]]=sys.argv[3]; json.dump(d, open(p,'w'), indent=1)" "$STATE" "$1" "$2"; }
PROFILE="$(cfg profile)"; REGION="$(cfg region)"
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore
o() { oci "$@" --profile "$PROFILE" --region "$REGION"; }
say() { printf '\033[1;32m$\033[0m %s\n' "$*" >&2; }   # stderr: some callers capture stdout
TAGS='{"demo": "litellmdemo"}'
SSH_KEY="${LITELLMDEMO_SSH_KEY:-$HOME/.ssh/id_ed25519}"
COMP="$(get compartment)"; VCN="$(get vcn)"; NODE_SUBNET="$(get node_subnet)"
[[ -n "$COMP" && -n "$VCN" && -n "$NODE_SUBNET" ]] || { echo "ABORT: run scripts/oci/up.sh first" >&2; exit 1; }

ip_of() { o compute instance list-vnics --instance-id "$(get control_instance)" --query "data[0].\"$1\"" --raw-output; }
if [[ "${1:-}" == ssh ]]; then
  exec ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "opc@$(ip_of public-ip)" "${@:2}"
fi

MY_CIDR="$(cfg api_allow_cidr)"
[[ -n "$MY_CIDR" ]] || MY_CIDR="$(curl -fsS -m 10 https://ifconfig.me)/32"

# 1. NSG: SSH from the operator only --------------------------------------------
NSG="$(get control_nsg)"
if [[ -z "$NSG" ]]; then
  say "create NSG litellmdemo-control"
  NSG="$(o network nsg create --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-control \
         --freeform-tags "$TAGS" --wait-for-state AVAILABLE --query data.id --raw-output)"
  put control_nsg "$NSG"
fi
say "NSG: SSH from $MY_CIDR only"
OLD="$(o network nsg rules list --nsg-id "$NSG" --query 'data[].id' 2>/dev/null || echo '[]')"
[[ "$OLD" == "[]" || -z "$OLD" ]] || o network nsg rules remove --nsg-id "$NSG" --security-rule-ids "$OLD" >/dev/null
o network nsg rules add --nsg-id "$NSG" --security-rules "[{\"direction\":\"INGRESS\",\"protocol\":\"6\",\"source\":\"$MY_CIDR\",
  \"sourceType\":\"CIDR_BLOCK\",\"isStateless\":false,\"tcpOptions\":{\"destinationPortRange\":{\"min\":22,\"max\":22}}}]" >/dev/null

# 2. The VM ---------------------------------------------------------------------
VM="$(get control_instance)"
if [[ -z "$VM" ]]; then
  TENANCY="$(python3 -c "import configparser,os,sys; c=configparser.ConfigParser(); c.read(os.path.expanduser('~/.oci/config')); print(c[sys.argv[1]]['tenancy'])" "$PROFILE")"
  AD="$(o iam availability-domain list --compartment-id "$TENANCY" --query 'data[0].name' --raw-output)"
  IMAGE="$(o compute image list --compartment-id "$COMP" --operating-system "Oracle Linux" --operating-system-version 9 \
           --shape VM.Standard.A1.Flex --sort-by TIMECREATED --query 'data[0].id' --raw-output)"
  INIT="$(mktemp)"
  cat > "$INIT" <<'CLOUD'
#cloud-config
runcmd:
  - dnf -y install dnf-plugins-core git rsync jq
  - dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
  - dnf -y install docker-ce docker-ce-cli containerd.io
  - systemctl enable --now docker
  - usermod -aG docker opc
  - firewall-cmd --permanent --zone=public --add-rich-rule='rule family=ipv4 source address=10.20.0.0/16 port port=8780 protocol=tcp accept'
  - firewall-cmd --reload
  - mkdir -p /etc/systemd/system/user@.service.d
  - printf '[Service]\nDelegate=cpu cpuset io memory pids\n' > /etc/systemd/system/user@.service.d/delegate.conf
  - systemctl daemon-reload
  - loginctl enable-linger opc
  # OpenShell confines the agent with Landlock: built into UEK, off by default
  - grubby --update-kernel=ALL --args="lsm=landlock,lockdown,capability,yama,selinux,bpf,ima,evm"
  - touch /var/lib/litellmdemo-ready
  - systemctl reboot
CLOUD
  say "create VM litellmdemo-control: VM.Standard.A1.Flex ($(cfg control_ocpus 2) OCPU, $(cfg control_memory_gbs 12) GB)"
  VM="$(o compute instance launch --compartment-id "$COMP" --availability-domain "$AD" --display-name litellmdemo-control \
        --shape VM.Standard.A1.Flex --shape-config "{\"ocpus\": $(cfg control_ocpus 2), \"memoryInGBs\": $(cfg control_memory_gbs 12)}" \
        --image-id "$IMAGE" --boot-volume-size-in-gbs 100 --subnet-id "$NODE_SUBNET" --assign-public-ip true \
        --nsg-ids "[\"$NSG\"]" --ssh-authorized-keys-file "$SSH_KEY.pub" --user-data-file "$INIT" \
        --freeform-tags "$TAGS" --wait-for-state RUNNING --query data.id --raw-output)"
  put control_instance "$VM"
  rm -f "$INIT"
fi
PUB="$(ip_of public-ip)"; PRIV="$(ip_of private-ip)"
put control_private_ip "$PRIV"
say "VM: $PRIV (SSH via $PUB)"
# cloud-init writes the marker just before its reboot: ready means the marker and
# the rebooted kernel, with Landlock among its security modules
READY='test -f /var/lib/litellmdemo-ready && grep -qw landlock /sys/kernel/security/lsm'
for _ in $(seq 60); do
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "opc@$PUB" "$READY" 2>/dev/null && break
  sleep 15
done
ssh -i "$SSH_KEY" -o ConnectTimeout=10 "opc@$PUB" "$READY" || { echo "ABORT: cloud-init or its reboot not finished (Landlock not active yet)" >&2; exit 1; }

# 3. OpenShell on the VM: the CLI and the gateway, rootless Podman, as user services --
OPENSHELL_VERSION="${OPENSHELL_VERSION:-0.1.2}"
say "OpenShell $OPENSHELL_VERSION and rootless Podman on the VM"
ssh -i "$SSH_KEY" -o ConnectTimeout=10 -o LogLevel=ERROR "opc@$PUB" "V=$OPENSHELL_VERSION bash -s" <<'VM'
set -euo pipefail
if ! command -v openshell >/dev/null || [[ "$(openshell --version 2>/dev/null)" != *"$V"* ]]; then
  d="$(mktemp -d)"; cd "$d"; B="https://github.com/NVIDIA/OpenShell/releases/download/v$V"
  for f in "openshell-$V-1.fc44.aarch64.rpm" "openshell-gateway-$V-1.fc44.aarch64.rpm" \
           openshell-checksums-sha256.txt openshell-gateway-checksums-sha256.txt; do curl -fsSLO "$B/$f"; done
  cat openshell-checksums-sha256.txt openshell-gateway-checksums-sha256.txt \
    | grep -E " (openshell|openshell-gateway)-$V-1\.fc44\.aarch64\.rpm$" | sha256sum -c --quiet
  sudo dnf -y -q install podman "./openshell-$V-1.fc44.aarch64.rpm" "./openshell-gateway-$V-1.fc44.aarch64.rpm"
  cd /; rm -rf "$d"
fi
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
systemctl --user enable --now podman.socket openshell-gateway >/dev/null 2>&1
for _ in $(seq 20); do systemctl --user is-active --quiet openshell-gateway && exit 0; sleep 3; done
echo "ABORT: the openshell-gateway user service is not active (journalctl --user -u openshell-gateway)" >&2; exit 1
VM

# 4. The gateway and the logs, as the VM sees them -------------------------------
export KUBECONFIG="$CONF_DIR/kubeconfig"
say "the gateway on a VCN node port, a read-only log reader for the console"
kubectl apply -f "$ROOT/deploy/k8s/control-access.yaml" >/dev/null
echo "CONTROL OK  (VM $PRIV; next: scripts/oci/control-deploy.sh)"

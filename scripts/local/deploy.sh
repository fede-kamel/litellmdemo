#!/usr/bin/env bash
# Deploy the gateway, the classifier and Postgres to the local Rancher Desktop
# Kubernetes, signing OCI calls with the operator's OCI session (the
# tenancy in config.json), so model calls bill that tenancy, not a personal one.
#
#   scripts/local/deploy.sh            # render, apply, wait, issue the agent key
#   scripts/local/refresh.sh &         # keep the session Secret fresh (it lasts about an hour)
#
# Same manifests as OKE (deploy/k8s/litellmdemo.yaml), rendered with three
# local differences: OCI_AUTH=session with the session mounted from a Secret,
# the gateway exposed on node port 30400 (where the OpenShell sandbox reaches
# it), and the agent's own virtual key in ~/.config/litellmdemo/agent_key-local.
# Targets only the rancher-desktop context.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"
CTX=rancher-desktop
NS=litellmdemo
k() { kubectl --context "$CTX" "$@"; }
cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$CONF_DIR/config.json" "$1"; }
[[ "$(kubectl config get-contexts -o name | grep -x "$CTX")" == "$CTX" ]] || { echo "ABORT: no $CTX context" >&2; exit 1; }

PROFILE="$(cfg oci_profile)"; COMP="$(cfg oci_compartment_id)"; REGION="$(cfg oci_region)"
WORK="$(mktemp -d)"; chmod 700 "$WORK"; trap 'rm -rf "$WORK"' EXIT

# 1. The manifest, rendered for the local cluster
python3 - "$ROOT/deploy/k8s/litellmdemo.yaml" "$WORK/local.yaml" "$PROFILE" "$REGION" <<'PY'
import sys, yaml
src, out, profile, region = sys.argv[1:5]
docs = [d for d in yaml.safe_load_all(open(src)) if d]
for d in docs:
    if d["kind"] == "Deployment" and d["metadata"]["name"] == "litellm-gateway":
        c = d["spec"]["template"]["spec"]["containers"][0]
        env = [e for e in c["env"] if e["name"] not in ("OCI_AUTH", "OCI_REGION")]
        env += [{"name": "OCI_AUTH", "value": "session"}, {"name": "OCI_REGION", "value": region},
                {"name": "OCI_CONFIG_PROFILE", "value": profile}, {"name": "OCI_CONFIG_FILE", "value": "/oci/config"}]
        c["env"] = env
        c["volumeMounts"].append({"name": "oci-session", "mountPath": "/oci", "readOnly": True})
        d["spec"]["template"]["spec"]["volumes"].append({"name": "oci-session", "secret": {"secretName": "oci-session"}})
    if d["kind"] == "Service" and d["metadata"]["name"] == "litellm-gateway":
        d["spec"]["type"] = "NodePort"
        d["spec"]["ports"][0]["nodePort"] = 30400
yaml.safe_dump_all(docs, open(out, "w"), sort_keys=False)
PY

# 2. The session Secret (scripts/local/refresh.sh keeps it fresh)
"$ROOT/scripts/local/push-session.sh"

# 3. Everything else, exactly as on OKE
MANIFEST="$WORK/local.yaml" CONTEXT="$CTX" COMPARTMENT_ID="$COMP" AGENT_KEY_FILE="$CONF_DIR/agent_key-local" \
  "$ROOT/scripts/oci/deploy.sh"
echo "LOCAL OK  (gateway: node port 30400, on this machine at http://127.0.0.1:30400)"

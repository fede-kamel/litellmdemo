#!/usr/bin/env bash
# Create the demo's OKE environment in OCI: a compartment, a VCN, an OKE Basic
# cluster with one Ampere A1 node, and an IAM policy that lets that node call
# OCI Generative AI with its instance principal (no key in the cluster).
#
#   scripts/oci/up.sh            # idempotent: reuses what the state file records
#   scripts/oci/down.sh          # deletes everything this script created
#
# Inputs: ~/.config/litellmdemo/deploy.json (profile, region, genai_region,
# compartment_name, node_ocpus, node_memory_gbs). Every OCID created is recorded
# in ~/.config/litellmdemo/oci-state.json, never in the repository. The
# Kubernetes API endpoint admits only the operator's current public IP.
set -euo pipefail
CONF_DIR="$HOME/.config/litellmdemo"
DEPLOY="$CONF_DIR/deploy.json"
STATE="$CONF_DIR/oci-state.json"
[[ -f "$DEPLOY" ]] || { echo "ABORT: $DEPLOY not found (see deploy/deploy.example.json)" >&2; exit 1; }
[[ -f "$STATE" ]] || echo '{}' > "$STATE"
chmod 600 "$STATE"

cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$DEPLOY" "$1"; }
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$STATE" "$1"; }
put() { python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d[sys.argv[2]]=sys.argv[3]; json.dump(d, open(p,'w'), indent=1)" "$STATE" "$1" "$2"; }

PROFILE="$(cfg profile)"; REGION="$(cfg region)"; NAME="$(cfg compartment_name)"
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore
o() { oci "$@" --profile "$PROFILE" --region "$REGION"; }
say() { printf '\033[1;32m$\033[0m %s\n' "$*" >&2; }   # stderr: some callers capture stdout
TAGS='{"demo": "litellmdemo"}'
adopt() {  # record a demo resource an interrupted run already created: adopt <state key> <oci list args...>
  [[ -n "$(get "$1")" ]] && return 0
  local key="$1" id; shift
  id="$(o "$@" --all --query 'data[?"lifecycle-state"!=`DELETED` && "lifecycle-state"!=`DELETING` && "lifecycle-state"!=`TERMINATED` && "lifecycle-state"!=`TERMINATING`].id | [0]' --raw-output 2>/dev/null || true)"
  [[ -n "$id" && "$id" != null ]] && { put "$key" "$id"; say "adopt $key from an earlier run"; }
  return 0
}
wait_wr() {  # poll an OKE work request until it succeeds (30 minutes at most)
  local s=""
  for _ in $(seq 60); do
    s="$(o ce work-request get --work-request-id "$1" --query 'data.status' --raw-output)"
    [[ "$s" == SUCCEEDED ]] && return 0
    [[ "$s" == FAILED || "$s" == CANCELED ]] && { echo "ABORT: work request $s" >&2; exit 1; }
    sleep 30
  done
  echo "ABORT: work request still $s after 30 minutes" >&2; exit 1
}

TENANCY="$(python3 -c "import configparser,os,sys; c=configparser.ConfigParser(); c.read(os.path.expanduser('~/.oci/config')); print(c[sys.argv[1]]['tenancy'])" "$PROFILE")"
# The address the Kubernetes API sees: probe on port 6443 itself, because NAT
# can send 6443 out of a different address than web traffic. deploy.json may
# set api_allow_cidr to admit a whole NAT pool instead.
API_CIDR="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('api_allow_cidr', ''))" "$DEPLOY")"
if [[ -z "$API_CIDR" ]]; then
  API_CIDR="$( (curl -fsS -m 10 http://portquiz.net:6443 || true) | sed -n 's/.*Your IP: \([0-9.]*\).*/\1/p')/32"
fi
[[ "$API_CIDR" == */* && "$API_CIDR" != "/32" ]] || { echo "ABORT: cannot determine the address to admit to the Kubernetes API" >&2; exit 1; }
MY_IP="$API_CIDR"

# 1. Compartment ------------------------------------------------------------
adopt compartment iam compartment list --compartment-id "$TENANCY" --name "$NAME"
COMP="$(get compartment)"
if [[ -z "$COMP" ]]; then
  say "create compartment $NAME"
  COMP="$(o iam compartment create --compartment-id "$TENANCY" --name "$NAME" --description "LiteLLM routing demo (OKE)" \
          --freeform-tags "$TAGS" --wait-for-state ACTIVE --query data.id --raw-output)"
  put compartment "$COMP"
  sleep 20   # new compartments take a moment to be usable everywhere
fi

# 2. Network: VCN, internet gateway, route table, security list, two subnets ---
adopt vcn network vcn list --compartment-id "$COMP" --display-name litellmdemo-vcn
VCN="$(get vcn)"
if [[ -z "$VCN" ]]; then
  say "create VCN 10.20.0.0/16"
  VCN="$(o network vcn create --compartment-id "$COMP" --cidr-blocks '["10.20.0.0/16"]' --display-name litellmdemo-vcn \
         --dns-label litellmdemo --freeform-tags "$TAGS" --wait-for-state AVAILABLE --query data.id --raw-output)"
  put vcn "$VCN"
fi
adopt igw network internet-gateway list --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-igw
IGW="$(get igw)"
if [[ -z "$IGW" ]]; then
  say "create internet gateway"
  IGW="$(o network internet-gateway create --compartment-id "$COMP" --vcn-id "$VCN" --is-enabled true --display-name litellmdemo-igw \
         --freeform-tags "$TAGS" --wait-for-state AVAILABLE --query data.id --raw-output)"
  put igw "$IGW"
fi
adopt route_table network route-table list --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-rt
RT="$(get route_table)"
if [[ -z "$RT" ]]; then
  say "create route table (0.0.0.0/0 via the internet gateway)"
  RT="$(o network route-table create --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-rt \
        --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" \
        --freeform-tags "$TAGS" --wait-for-state AVAILABLE --query data.id --raw-output)"
  put route_table "$RT"
fi
adopt security_list network security-list list --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-sl
SL="$(get security_list)"
# api_allow_cidr may list several addresses or ranges, comma-separated (home and office, say): one rule each
INGRESS="$(python3 -c '
import json, sys
rules = [{"protocol": "all", "source": "10.20.0.0/16", "isStateless": False}]
rules += [{"protocol": "6", "source": c.strip(), "isStateless": False, "tcpOptions": {"destinationPortRange": {"min": 6443, "max": 6443}}}
          for c in sys.argv[1].split(",") if c.strip()]
rules.append({"protocol": "1", "source": "0.0.0.0/0", "isStateless": False, "icmpOptions": {"type": 3, "code": 4}})
print(json.dumps(rules))' "$MY_IP")"
EGRESS='[{"protocol":"all","destination":"0.0.0.0/0","isStateless":false}]'
if [[ -z "$SL" ]]; then
  say "create security list (VCN-internal, Kubernetes API from $MY_IP only, all egress)"
  SL="$(o network security-list create --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-sl \
        --ingress-security-rules "$INGRESS" --egress-security-rules "$EGRESS" --freeform-tags "$TAGS" \
        --wait-for-state AVAILABLE --query data.id --raw-output)"
  put security_list "$SL"
else
  say "refresh security list (Kubernetes API from $MY_IP only)"
  o network security-list update --security-list-id "$SL" --ingress-security-rules "$INGRESS" \
    --egress-security-rules "$EGRESS" --force >/dev/null
fi
subnet() {  # key cidr name dns
  adopt "$1" network subnet list --compartment-id "$COMP" --vcn-id "$VCN" --display-name "$3"
  local id; id="$(get "$1")"
  if [[ -z "$id" ]]; then
    say "create subnet $3 $2"
    id="$(o network subnet create --compartment-id "$COMP" --vcn-id "$VCN" --cidr-block "$2" --display-name "$3" --dns-label "$4" \
          --route-table-id "$RT" --security-list-ids "[\"$SL\"]" --freeform-tags "$TAGS" \
          --wait-for-state AVAILABLE --query data.id --raw-output)"
    [[ -n "$id" && "$id" != null ]] || { echo "ABORT: could not create subnet $3" >&2; return 1; }
    put "$1" "$id"
  fi
  echo "$id"
}
API_SUBNET="$(subnet api_subnet 10.20.0.0/28 litellmdemo-api api)"
NODE_SUBNET="$(subnet node_subnet 10.20.10.0/24 litellmdemo-nodes nodes)"

# 3. OKE Basic cluster ------------------------------------------------------------
K8S="$(o ce cluster-options get --cluster-option-id all --query 'data."kubernetes-versions"[-1]' --raw-output)"
CLUSTER="$(get cluster)"
if [[ -z "$CLUSTER" ]]; then   # adopt a cluster an interrupted run already started
  CLUSTER="$(o ce cluster list --compartment-id "$COMP" --name litellmdemo --query 'data[?"lifecycle-state"!=`DELETED` && "lifecycle-state"!=`DELETING`].id | [0]' --raw-output)"
  [[ "$CLUSTER" == "null" ]] && CLUSTER=""
  [[ -n "$CLUSTER" ]] && put cluster "$CLUSTER"
fi
if [[ -z "$CLUSTER" ]]; then
  say "create OKE Basic cluster litellmdemo ($K8S, public endpoint limited to $MY_IP)"
  WR="$(o ce cluster create --compartment-id "$COMP" --name litellmdemo --vcn-id "$VCN" --kubernetes-version "$K8S" \
        --type BASIC_CLUSTER --endpoint-subnet-id "$API_SUBNET" --endpoint-public-ip-enabled true \
        --cluster-pod-network-options '[{"cniType":"FLANNEL_OVERLAY"}]' --freeform-tags "$TAGS" \
        --query '"opc-work-request-id"' --raw-output)"
  say "waiting for the cluster (about 7 minutes)"
  wait_wr "$WR"
  CLUSTER="$(o ce cluster list --compartment-id "$COMP" --name litellmdemo --lifecycle-state ACTIVE --query 'data[0].id' --raw-output)"
  put cluster "$CLUSTER"
fi
say "waiting for the cluster to be ACTIVE"
for _ in $(seq 60); do
  STATE_NOW="$(o ce cluster get --cluster-id "$CLUSTER" --query 'data."lifecycle-state"' --raw-output)"
  [[ "$STATE_NOW" == ACTIVE ]] && break
  [[ "$STATE_NOW" == FAILED ]] && { echo "ABORT: cluster FAILED" >&2; exit 1; }
  sleep 30
done
[[ "$STATE_NOW" == ACTIVE ]] || { echo "ABORT: cluster not ACTIVE after 30 minutes" >&2; exit 1; }

# 4. Node pool: one Ampere A1 node ------------------------------------------------------
POOL="$(get node_pool)"
if [[ -z "$POOL" ]]; then   # adopt a node pool an interrupted run already started
  POOL="$(o ce node-pool list --compartment-id "$COMP" --cluster-id "$CLUSTER" --name litellmdemo-pool --query 'data[?"lifecycle-state"!=`DELETED` && "lifecycle-state"!=`DELETING`].id | [0]' --raw-output)"
  [[ "$POOL" == "null" ]] && POOL=""
  [[ -n "$POOL" ]] && put node_pool "$POOL"
fi
if [[ -z "$POOL" ]]; then
  AD="$(o iam availability-domain list --compartment-id "$TENANCY" --query 'data[0].name' --raw-output)"
  V="${K8S#v}"
  IMAGE="$(o ce node-pool-options get --node-pool-option-id "$CLUSTER" \
          --query "data.sources[?contains(\"source-name\", 'aarch64') && contains(\"source-name\", 'OKE-$V') && !contains(\"source-name\", 'GPU')].\"image-id\" | [0]" --raw-output)"
  [[ -n "$IMAGE" && "$IMAGE" != "null" ]] || { echo "ABORT: no aarch64 OKE image for $K8S" >&2; exit 1; }
  say "create node pool: 1 x VM.Standard.A1.Flex ($(cfg node_ocpus) OCPU, $(cfg node_memory_gbs) GB)"
  WR="$(o ce node-pool create --compartment-id "$COMP" --cluster-id "$CLUSTER" --name litellmdemo-pool --kubernetes-version "$K8S" \
        --node-shape VM.Standard.A1.Flex \
        --node-shape-config "{\"ocpus\": $(cfg node_ocpus), \"memoryInGBs\": $(cfg node_memory_gbs)}" \
        --node-source-details "{\"sourceType\":\"IMAGE\",\"imageId\":\"$IMAGE\",\"bootVolumeSizeInGBs\":50}" \
        --placement-configs "[{\"availabilityDomain\":\"$AD\",\"subnetId\":\"$NODE_SUBNET\"}]" --size 1 \
        --initial-node-labels '[{"key":"demo","value":"litellmdemo"}]' --freeform-tags "$TAGS" \
        --query '"opc-work-request-id"' --raw-output)"
  say "waiting for the node pool (about 6 minutes)"
  wait_wr "$WR"
  POOL="$(o ce node-pool list --compartment-id "$COMP" --cluster-id "$CLUSTER" --name litellmdemo-pool --query 'data[0].id' --raw-output)"
  put node_pool "$POOL"
fi
say "waiting for the node to be ACTIVE"
for _ in $(seq 60); do
  NODE_NOW="$(o ce node-pool get --node-pool-id "$POOL" --query 'data.nodes[0]."lifecycle-state"' --raw-output)"
  [[ "$NODE_NOW" == ACTIVE ]] && break
  [[ "$NODE_NOW" == FAILED ]] && { echo "ABORT: node FAILED" >&2; exit 1; }
  sleep 30
done
[[ "$NODE_NOW" == ACTIVE ]] || { echo "ABORT: the node is still $NODE_NOW after 30 minutes" >&2; exit 1; }

# 5. Instance principal: dynamic group of the demo's instances + a scoped policy ---------
adopt dynamic_group iam dynamic-group list --compartment-id "$TENANCY" --name litellmdemo-nodes
DG="$(get dynamic_group)"
if [[ -z "$DG" ]]; then
  say "create dynamic group litellmdemo-nodes (instances in the litellmdemo compartment)"
  DG="$(o iam dynamic-group create --compartment-id "$TENANCY" --name litellmdemo-nodes \
        --description "OKE nodes of the LiteLLM routing demo" \
        --matching-rule "ALL {instance.compartment.id = '$COMP'}" --freeform-tags "$TAGS" \
        --wait-for-state ACTIVE --query data.id --raw-output)"
  put dynamic_group "$DG"
fi
# generative-ai-family covers the chat API; the Responses API (Codex) checks generative-ai-response, which the
# family does not include: without its own statement the node gets 404 "Authorization failed or requested
# resource not found" on every Responses call, and the CODE route falls back.
STATEMENTS="[\"Allow dynamic-group litellmdemo-nodes to use generative-ai-family in compartment $NAME\",
             \"Allow dynamic-group litellmdemo-nodes to manage generative-ai-response in compartment $NAME\",
             \"Allow dynamic-group litellmdemo-nodes to read repos in compartment $NAME\"]"
adopt policy iam policy list --compartment-id "$TENANCY" --name litellmdemo-genai
POLICY="$(get policy)"
if [[ -z "$POLICY" ]]; then
  say "create policy: the nodes may use Generative AI (chat and Responses API) and read the demo's images, in the litellmdemo compartment only"
  POLICY="$(o iam policy create --compartment-id "$TENANCY" --name litellmdemo-genai \
        --description "LiteLLM routing demo: OKE nodes call OCI Generative AI and pull images" \
        --statements "$STATEMENTS" \
        --freeform-tags "$TAGS" --wait-for-state ACTIVE --query data.id --raw-output)"
  put policy "$POLICY"
elif [[ "$(o iam policy get --policy-id "$POLICY" | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)["data"]["statements"]))')" \
        != "$(python3 -c 'import json,sys; print(sorted(json.loads(sys.argv[1])))' "$STATEMENTS")" ]]; then
  say "update policy: the nodes' statements changed (the Responses API, for Codex)"
  # the CLI wants the version date whenever the statements change; empty keeps the policy on the current language version
  o iam policy update --policy-id "$POLICY" --statements "$STATEMENTS" --version-date "" --force --query 'data."lifecycle-state"' --raw-output
fi

# 6. kubeconfig -----------------------------------------------------------------
KUBE="$CONF_DIR/kubeconfig"
o ce cluster create-kubeconfig --cluster-id "$CLUSTER" --file "$KUBE" --region "$REGION" --token-version 2.0.0 \
  --kube-endpoint PUBLIC_ENDPOINT --overwrite >/dev/null
python3 - "$KUBE" "$PROFILE" <<'PY'
import sys, yaml
path, profile = sys.argv[1], sys.argv[2]
cfg = yaml.safe_load(open(path))
for u in cfg["users"]:
    args = u["user"]["exec"]["args"]
    if "--profile" not in args:
        args += ["--profile", profile, "--auth", "api_key"]
yaml.safe_dump(cfg, open(path, "w"))
PY
chmod 600 "$KUBE"
say "kubeconfig: $KUBE"
KUBECONFIG="$KUBE" kubectl get nodes -o wide
echo "UP OK"

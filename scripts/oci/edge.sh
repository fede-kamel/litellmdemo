#!/usr/bin/env bash
# The demo's public address: an OCI API Gateway in front of the control room.
#
#   scripts/oci/control.sh && scripts/oci/control-deploy.sh    # first: the VM
#   scripts/oci/edge.sh          # idempotent: subnet, security list, gateway, deployment
#   scripts/oci/down.sh          # deletes them too
#
# Oracle issues the hostname (<id>.apigateway.<region>.oci.customer-oci.com)
# and its certificate, so the demo has a public HTTPS name without a domain.
# The gateway sits in its own public subnet (443 from anywhere) and forwards
# every path to the control room's VCN address; the control room itself is
# never reachable from the internet. Each client address gets 50 requests a
# second, and the agent's virtual key keeps its own budget and rate in LiteLLM.
set -euo pipefail
CONF_DIR="$HOME/.config/litellmdemo"
DEPLOY="$CONF_DIR/deploy.json"
STATE="$CONF_DIR/oci-state.json"
[[ -f "$STATE" ]] || { echo "ABORT: $STATE not found: run scripts/oci/up.sh first" >&2; exit 1; }
cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$DEPLOY" "$1"; }
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$STATE" "$1"; }
put() { python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d[sys.argv[2]]=sys.argv[3]; json.dump(d, open(p,'w'), indent=1)" "$STATE" "$1" "$2"; }
PROFILE="$(cfg profile)"; REGION="$(cfg region)"
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore
o() { oci "$@" --profile "$PROFILE" --region "$REGION"; }
say() { printf '\033[1;32m$\033[0m %s\n' "$*" >&2; }   # stderr: some callers capture stdout
TAGS='{"demo": "litellmdemo"}'
COMP="$(get compartment)"; VCN="$(get vcn)"; RT="$(get route_table)"; VM_IP="$(get control_private_ip)"
[[ -n "$COMP" && -n "$VCN" && -n "$RT" ]] || { echo "ABORT: run scripts/oci/up.sh first" >&2; exit 1; }
[[ -n "$VM_IP" ]] || { echo "ABORT: run scripts/oci/control.sh first" >&2; exit 1; }

# 1. A public subnet of its own: HTTPS from anywhere, nothing else ----------------
SL="$(get edge_security_list)"
if [[ -z "$SL" ]]; then
  say "create security list litellmdemo-edge (443 from anywhere)"
  SL="$(o network security-list create --compartment-id "$COMP" --vcn-id "$VCN" --display-name litellmdemo-edge \
        --ingress-security-rules '[{"protocol":"6","source":"0.0.0.0/0","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":443,"max":443}}}]' \
        --egress-security-rules '[{"protocol":"all","destination":"0.0.0.0/0","isStateless":false}]' \
        --freeform-tags "$TAGS" --wait-for-state AVAILABLE --query data.id --raw-output)"
  put edge_security_list "$SL"
fi
SUBNET="$(get edge_subnet)"
if [[ -z "$SUBNET" ]]; then
  say "create subnet litellmdemo-edge 10.20.20.0/24"
  SUBNET="$(o network subnet create --compartment-id "$COMP" --vcn-id "$VCN" --cidr-block 10.20.20.0/24 --display-name litellmdemo-edge \
            --dns-label edge --route-table-id "$RT" --security-list-ids "[\"$SL\"]" --freeform-tags "$TAGS" \
            --wait-for-state AVAILABLE --query data.id --raw-output)"
  put edge_subnet "$SUBNET"
fi

# 2. The gateway ------------------------------------------------------------------
GW="$(get api_gateway)"
if [[ -z "$GW" ]]; then   # adopt a gateway an interrupted run already started
  GW="$(o api-gateway gateway list --compartment-id "$COMP" --display-name litellmdemo \
        --query 'data.items[?"lifecycle-state"!=`DELETED` && "lifecycle-state"!=`DELETING`].id | [0]' --raw-output)"
  [[ "$GW" == "null" ]] && GW=""
  [[ -n "$GW" ]] && put api_gateway "$GW"
fi
if [[ -z "$GW" ]]; then
  say "create API gateway litellmdemo (public)"
  GW="$(o api-gateway gateway create --compartment-id "$COMP" --display-name litellmdemo --endpoint-type PUBLIC \
        --subnet-id "$SUBNET" --freeform-tags "$TAGS" --query data.id --raw-output)"
  put api_gateway "$GW"
fi
say "waiting for the gateway to be ACTIVE"
for _ in $(seq 60); do
  GW_STATE="$(o api-gateway gateway get --gateway-id "$GW" --query 'data."lifecycle-state"' --raw-output)"
  [[ "$GW_STATE" == ACTIVE ]] && break
  [[ "$GW_STATE" == FAILED ]] && { echo "ABORT: API gateway FAILED" >&2; exit 1; }
  sleep 10
done
[[ "$GW_STATE" == ACTIVE ]] || { echo "ABORT: API gateway still $GW_STATE after 10 minutes" >&2; exit 1; }
HOST="$(o api-gateway gateway get --gateway-id "$GW" --query data.hostname --raw-output)"
put api_hostname "$HOST"

# 3. One deployment: every path to the control room ------------------------------
SPEC="$(mktemp)"; trap 'rm -f "$SPEC"' EXIT
cat > "$SPEC" <<JSON
{
  "requestPolicies": {"rateLimiting": {"rateInRequestsPerSecond": 50, "rateKey": "CLIENT_IP"}},
  "routes": [{
    "path": "/{path*}", "methods": ["ANY"],
    "backend": {"type": "HTTP_BACKEND", "url": "http://$VM_IP:8780/\${request.path[path]}",
                "connectTimeoutInSeconds": 10, "readTimeoutInSeconds": 300, "sendTimeoutInSeconds": 300}
  }]
}
JSON
DEP="$(get api_deployment)"
if [[ -z "$DEP" ]]; then   # adopt a deployment an interrupted run already started
  DEP="$(o api-gateway deployment list --compartment-id "$COMP" --gateway-id "$GW" --display-name control-room \
         --query 'data.items[?"lifecycle-state"!=`DELETED` && "lifecycle-state"!=`DELETING`].id | [0]' --raw-output)"
  [[ "$DEP" == "null" ]] && DEP=""
  [[ -n "$DEP" ]] && put api_deployment "$DEP"
fi
# (--wait-for-state is not reliable for api-gateway in the CLI: poll instead)
if [[ -z "$DEP" ]]; then
  say "create deployment control-room (/ -> http://$VM_IP:8780)"
  DEP="$(o api-gateway deployment create --compartment-id "$COMP" --gateway-id "$GW" --display-name control-room --path-prefix / \
         --specification "file://$SPEC" --freeform-tags "$TAGS" --query data.id --raw-output)"
  put api_deployment "$DEP"
else
  say "refresh deployment control-room (/ -> http://$VM_IP:8780)"
  o api-gateway deployment update --deployment-id "$DEP" --specification "file://$SPEC" --force >/dev/null
fi
say "waiting for the deployment to be ACTIVE"
for _ in $(seq 60); do
  DEP_STATE="$(o api-gateway deployment get --deployment-id "$DEP" --query 'data."lifecycle-state"' --raw-output)"
  [[ "$DEP_STATE" == ACTIVE ]] && break
  [[ "$DEP_STATE" == FAILED ]] && { echo "ABORT: deployment FAILED" >&2; exit 1; }
  sleep 10
done
[[ "$DEP_STATE" == ACTIVE ]] || { echo "ABORT: deployment still $DEP_STATE after 10 minutes" >&2; exit 1; }

say "waiting for https://$HOST/api/health"
for _ in $(seq 40); do curl -sf -m 10 -o /dev/null "https://$HOST/api/health" && break; sleep 5; done
curl -sf -m 10 "https://$HOST/api/health" >/dev/null || { echo "ABORT: https://$HOST/api/health does not answer" >&2; exit 1; }
echo "EDGE OK  https://$HOST"

#!/usr/bin/env bash
# Delete everything scripts/oci/up.sh, control.sh and edge.sh created, and
# nothing else.
#
#   scripts/oci/down.sh          # asks before deleting
#   scripts/oci/down.sh --yes
#
# Reads the OCIDs from ~/.config/litellmdemo/oci-state.json and deletes them in
# dependency order: API gateway, the control room's VM, node pool, cluster,
# network, IAM policy and dynamic group, compartment. Resources not in the
# state file are never touched.
set -euo pipefail
CONF_DIR="$HOME/.config/litellmdemo"
DEPLOY="$CONF_DIR/deploy.json"
STATE="$CONF_DIR/oci-state.json"
[[ -f "$STATE" ]] || { echo "nothing to delete: $STATE not found"; exit 0; }
cfg() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$DEPLOY" "$1"; }
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$STATE" "$1"; }
drop() { python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d.pop(sys.argv[2], None); json.dump(d, open(p,'w'), indent=1)" "$STATE" "$1"; }
PROFILE="$(cfg profile)"; REGION="$(cfg region)"
export OCI_CLI_AUTH=api_key OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True PYTHONWARNINGS=ignore
o() { oci "$@" --profile "$PROFILE" --region "$REGION"; }
say() { printf '\033[1;31m-\033[0m %s\n' "$*"; }

echo "Will delete:"; python3 -c "import json; [print(f'  {k}') for k in json.load(open('$STATE'))]"
if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "Delete these resources? [y/N] " ok; [[ "$ok" == y* ]] || exit 1
fi

del() {  # state-key  oci-args...
  local id; id="$(get "$1")"; [[ -n "$id" ]] || return 0
  say "delete $1"
  o "${@:2}" "$id" --force --wait-for-state "${WAIT_STATE:-TERMINATED}" >/dev/null 2>&1 \
    || o "${@:2}" "$id" --force >/dev/null 2>&1 || true
  drop "$1"
}
wait_gone() {  # resource kind: poll until the get fails or reports DELETED
  for _ in $(seq 60); do
    s="$(o ce "$1" get "--$1-id" "$2" --query 'data."lifecycle-state"' --raw-output 2>/dev/null || echo DELETED)"
    [[ "$s" == DELETED ]] && return 0; sleep 20
  done
}
WAIT_STATE=DELETED del api_deployment api-gateway deployment delete --deployment-id
WAIT_STATE=DELETED del api_gateway api-gateway gateway delete --gateway-id
drop api_hostname
del control_instance compute instance terminate --instance-id
drop control_private_ip; drop control_gateway_host
del control_nsg network nsg delete --nsg-id
del edge_subnet network subnet delete --subnet-id
del edge_security_list network security-list delete --security-list-id
POOL="$(get node_pool)"; CLUSTER="$(get cluster)"
if [[ -n "$POOL" ]]; then say "delete node pool"; o ce node-pool delete --node-pool-id "$POOL" --force >/dev/null; wait_gone node-pool "$POOL"; drop node_pool; fi
if [[ -n "$CLUSTER" ]]; then say "delete cluster"; o ce cluster delete --cluster-id "$CLUSTER" --force >/dev/null; wait_gone cluster "$CLUSTER"; drop cluster; fi
del node_subnet network subnet delete --subnet-id
del api_subnet network subnet delete --subnet-id
del security_list network security-list delete --security-list-id
del route_table network route-table delete --rt-id
del igw network internet-gateway delete --ig-id
del vcn network vcn delete --vcn-id
WAIT_STATE=DELETED del policy iam policy delete --policy-id
WAIT_STATE=DELETED del dynamic_group iam dynamic-group delete --dynamic-group-id
WAIT_STATE=DELETED del compartment iam compartment delete --compartment-id
rm -f "$CONF_DIR/kubeconfig"
echo "DOWN OK"

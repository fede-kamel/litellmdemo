#!/usr/bin/env bash
# Kill the classifier pod and show that requests keep answering.
#
#   scripts/oci/deploy.sh --forward &      # gateway on 127.0.0.1:4100
#   scripts/oci/chaos.sh
#
# 1. a request to oci-auto-trained is routed by the classifier service;
# 2. the classifier is taken away (scaled to zero): a real outage;
# 3. the same request, during the outage, is routed to fallback_tier and still answers;
# 4. the classifier comes back and routes again;
# 5. a pod kill: how long Kubernetes takes to have a new classifier pod ready.
# Touches only the demo's own route-classifier Deployment.
set -euo pipefail
CONF_DIR="$HOME/.config/litellmdemo"
export KUBECONFIG="$CONF_DIR/kubeconfig"
GATEWAY="${LITELLM_GATEWAY:-http://127.0.0.1:4100}"
KEY="$(cat "$CONF_DIR/master_key")"
PROMPT="Write a Python function that merges overlapping intervals, with tests."

ask() {
  local h; h="$(mktemp)"
  local started=$SECONDS
  curl -fsS -D "$h" -o /dev/null "$GATEWAY/v1/chat/completions" -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"oci-auto-trained\",\"max_tokens\":300,\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}]}"
  local tier cause model
  tier="$(grep -i '^x-litellm-complexity-router-tier:' "$h" | cut -d' ' -f2 | tr -d '\r')"
  cause="$(grep -i '^x-litellm-complexity-router-cause:' "$h" | cut -d' ' -f2 | tr -d '\r')"
  model="$(grep -i '^x-litellm-model-id:\|^x-litellm-model-name:' "$h" | head -1 | cut -d' ' -f2 | tr -d '\r')"
  rm -f "$h"
  printf '  %-26s tier=%-10s cause=%-22s answered in %ss\n' "$1" "$tier" "$cause" "$((SECONDS - started))"
  echo "$tier $cause" > "$CONF_DIR/.chaos-last"
}

echo "1. classifier up"
ask "before"
read -r BEFORE_TIER BEFORE_CAUSE < "$CONF_DIR/.chaos-last"

echo "2. take the classifier away (scale to 0)"
kubectl scale -n litellmdemo deployment/route-classifier --replicas=0 >/dev/null
kubectl wait -n litellmdemo --for=delete pod -l app=route-classifier --timeout=120s >/dev/null 2>&1 || true

echo "3. during the outage"
ask "classifier down"
read -r DOWN_TIER DOWN_CAUSE < "$CONF_DIR/.chaos-last"

echo "4. bring it back"
kubectl scale -n litellmdemo deployment/route-classifier --replicas=1 >/dev/null
kubectl rollout status -n litellmdemo deployment/route-classifier --timeout=15m >/dev/null
ask "classifier back"
read -r AFTER_TIER AFTER_CAUSE < "$CONF_DIR/.chaos-last"

echo "5. kill the classifier pod and time the recovery"
started=$SECONDS
kubectl delete pod -n litellmdemo -l app=route-classifier --wait=false >/dev/null
sleep 2
kubectl rollout status -n litellmdemo deployment/route-classifier --timeout=15m >/dev/null
until kubectl get pods -n litellmdemo -l app=route-classifier -o jsonpath='{.items[*].status.containerStatuses[0].ready}' | grep -qx true; do sleep 1; done
RECOVERY=$((SECONDS - started))
echo "  new classifier pod ready in ${RECOVERY}s"
rm -f "$CONF_DIR/.chaos-last"

if [[ "$BEFORE_CAUSE" == classifier_plugin && "$DOWN_CAUSE" != classifier_plugin && -n "$DOWN_TIER" && "$AFTER_CAUSE" == classifier_plugin ]]; then
  echo "CHAOS OK: the request answered through the outage (tier $DOWN_TIER), routing recovered, a killed pod was replaced in ${RECOVERY}s"
else
  echo "CHAOS FAILED: before=$BEFORE_TIER/$BEFORE_CAUSE down=$DOWN_TIER/$DOWN_CAUSE after=$AFTER_TIER/$AFTER_CAUSE"; exit 1
fi

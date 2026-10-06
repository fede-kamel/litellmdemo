#!/usr/bin/env bash
# Keep the OKE gateway on 127.0.0.1:4100, whatever happens to the pod behind it.
#
#   scripts/oci/forward.sh &
#
# kubectl port-forward binds to one pod and exits when that pod goes away
# (a rollout, a crash, a deleted pod). This loop starts it again within a
# second or two, so the laptop side never has to notice.
set -uo pipefail
export KUBECONFIG="$HOME/.config/litellmdemo/kubeconfig"
PORT="${1:-4100}"
while true; do
  kubectl port-forward -n litellmdemo svc/litellm-gateway "$PORT:4000" >/dev/null 2>&1
  echo "$(date +%T) port-forward exited; restarting" >&2
  sleep 1
done

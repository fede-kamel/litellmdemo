#!/usr/bin/env bash
# Prove the OKE gateway keeps signing as its token rotates: one request every
# INTERVAL seconds for DURATION seconds (default 3 min for 70 min, over three
# instance-principal token lifetimes). Ends with "SOAK OK (n/n)".
set -uo pipefail
GATEWAY="${LITELLM_GATEWAY:-http://127.0.0.1:4100}"
KEY="$(cat "$HOME/.config/litellmdemo/master_key")"
INTERVAL="${INTERVAL:-180}"; DURATION="${DURATION:-4200}"
ok=0; n=0; end=$((SECONDS + DURATION))
while (( SECONDS < end )); do
  n=$((n + 1))
  code="$(curl -s -m 60 -o /dev/null -w '%{http_code}' "$GATEWAY/v1/chat/completions" -H "Authorization: Bearer $KEY" \
    -H 'Content-Type: application/json' -d '{"model":"oci-fast","max_tokens":5,"messages":[{"role":"user","content":"say ok"}]}')"
  [[ "$code" == 200 ]] && ok=$((ok + 1))
  echo "$(date +%T) request $n: HTTP $code"
  sleep "$INTERVAL"
done
[[ $ok == "$n" ]] && echo "SOAK OK ($ok/$n)" || { echo "SOAK FAILED ($ok/$n)"; exit 1; }

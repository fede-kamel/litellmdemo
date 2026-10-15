#!/usr/bin/env bash
# Start the LiteLLM AI Gateway on 127.0.0.1:4000 in front of OCI Generative AI.
#
#   scripts/gateway.sh            # foreground
#
# Reads the OCI profile, its kind (oci_auth), the region and compartment from
# ~/.config/litellmdemo/config.json and a gateway master key from
# ~/.config/litellmdemo/master_key (created on first run, 0600). Nothing here
# is printed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF="${LITELLMDEMO_CONFIG:-$HOME/.config/litellmdemo/config.json}"
KEYFILE="$(dirname "$CONF")/master_key"
PORT="${LITELLM_PORT:-4000}"

[[ -f "$CONF" ]] || { echo "ABORT: $CONF not found (see config.example.json)" >&2; exit 1; }
get() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$CONF" "$1"; }

if [[ ! -s "$KEYFILE" ]]; then
  ( umask 077; python3 -c "import secrets; print('sk-' + secrets.token_urlsafe(24))" >"$KEYFILE" )
fi

export OCI_CONFIG_PROFILE="$(get oci_profile)"
export OCI_REGION="$(get oci_region)"
export OCI_COMPARTMENT_ID="$(get oci_compartment_id)"
# "api_key": an OCI CLI profile with an API key (nothing expires); "security_token": a session profile
# (`oci session authenticate`), which the gateway re-reads every minute.
case "$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('oci_auth', 'security_token'))" "$CONF")" in
  api_key) export OCI_AUTH=api_key ;;
  *) export OCI_AUTH=session ;;
esac
export PYTHONUNBUFFERED=1   # the ROUTE lines reach the log as they happen
export LITELLM_MASTER_KEY="$(cat "$KEYFILE")"
export LITELLM_LOG="${LITELLM_LOG:-ERROR}"

cd "$ROOT/gateway"
exec "$ROOT/.venv/bin/litellm" --config config.yaml --host 127.0.0.1 --port "$PORT"

#!/usr/bin/env bash
# Keep the OCI session alive for the local cluster: refresh it every 20 minutes
# and push it into the cluster. Writes ~/.config/litellmdemo/run/session.json
# (minutes left, last refresh, state) for preflight.sh and the control room.
# If the session can no longer be refreshed, it says so and keeps checking:
#   oci session authenticate --profile-name <profile> --region us-ashburn-1
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF_DIR="$HOME/.config/litellmdemo"; RUN="$CONF_DIR/run"; mkdir -p "$RUN"
PROFILE="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['oci_profile'])" "$CONF_DIR/config.json")"
minutes_left() {
  python3 - "$PROFILE" <<'PY'
import base64, configparser, json, os, sys, time
c = configparser.ConfigParser(); c.read(os.path.expanduser("~/.oci/config"))
try:
    t = open(os.path.expanduser(c[sys.argv[1]]["security_token_file"])).read().split(".")[1]
    t += "=" * (-len(t) % 4)
    print(int((json.loads(base64.urlsafe_b64decode(t))["exp"] - time.time()) / 60))
except Exception:
    print(-1)
PY
}
status() { printf '{"minutes_left": %s, "state": "%s", "at": %s}\n' "$(minutes_left)" "$1" "$(date +%s)" > "$RUN/session.json"; }
while true; do
  if oci session refresh --profile "$PROFILE" --region us-ashburn-1 >/dev/null 2>&1; then
    "$ROOT/scripts/local/push-session.sh" && status ok || status push-failed
    # A refresh cannot extend a session past its maximum lifetime: when the new
    # token is short, only `oci session authenticate` (a browser login) helps.
    left="$(minutes_left)"
    if (( left < 45 )); then
      status "needs-login"
      echo "$(date +%T) OCI session at its maximum lifetime ($left min left): run  oci session authenticate --profile-name $PROFILE --region us-ashburn-1" >&2
      sleep 120
    else
      sleep 1200
    fi
  else
    status expired
    echo "$(date +%T) OCI session cannot be refreshed: run  oci session authenticate --profile-name $PROFILE --region us-ashburn-1" >&2
    sleep 60
  fi
done

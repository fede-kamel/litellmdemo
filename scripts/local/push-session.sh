#!/usr/bin/env bash
# Put the operator's current OCI session into the local cluster's `oci-session`
# Secret (a minimal config, the session key and token). The gateway's signer
# rereads it within a minute. Never prints the key or the token.
set -euo pipefail
CONF_DIR="$HOME/.config/litellmdemo"
PROFILE="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['oci_profile'])" "$CONF_DIR/config.json")"
WORK="$(mktemp -d)"; chmod 700 "$WORK"; trap 'rm -rf "$WORK"' EXIT
python3 - "$PROFILE" "$WORK" <<'PY'
import configparser, os, shutil, sys
profile, work = sys.argv[1], sys.argv[2]
c = configparser.ConfigParser(); c.read(os.path.expanduser("~/.oci/config"))
p = c[profile]
shutil.copy(os.path.expanduser(p["key_file"]), f"{work}/key.pem")
shutil.copy(os.path.expanduser(p["security_token_file"]), f"{work}/token")
with open(f"{work}/config", "w") as fh:
    fh.write(f"[{profile}]\n")
    for k in ("fingerprint", "tenancy", "region"):
        if k in p:
            fh.write(f"{k}={p[k]}\n")
    fh.write("key_file=/oci/key.pem\nsecurity_token_file=/oci/token\n")
for f in ("key.pem", "token", "config"):
    os.chmod(f"{work}/{f}", 0o600)
PY
kubectl --context rancher-desktop create namespace litellmdemo --dry-run=client -o yaml | kubectl --context rancher-desktop apply -f - >/dev/null
kubectl --context rancher-desktop create secret generic oci-session -n litellmdemo --from-file="$WORK/config" \
  --from-file="$WORK/key.pem" --from-file="$WORK/token" --dry-run=client -o yaml \
  | kubectl --context rancher-desktop apply --server-side --force-conflicts -f - >/dev/null

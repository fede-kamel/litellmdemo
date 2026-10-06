#!/usr/bin/env bash
# Stop the background processes scripts/demo-up.sh started (the clusters and the sandbox keep running).
RUN="$HOME/.config/litellmdemo/run"
for f in "$RUN"/*.pid; do [[ -f "$f" ]] || continue; kill "$(cat "$f")" 2>/dev/null && echo "stopped $(basename "$f" .pid)"; rm -f "$f"; done

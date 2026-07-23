#!/bin/sh
# Entrypoint for the Memgraph Home Assistant add-on.
#
# Persists Memgraph's storage and logs under /data (the add-on's persistent
# volume managed by the Home Assistant Supervisor) instead of the image's
# default in-container paths, so the ontology graph survives add-on
# restarts, host reboots, and add-on version upgrades.
set -e

mkdir -p /data/memgraph/lib /data/memgraph/log

# Announce this add-on to Home Assistant Core via the Supervisor Discovery
# API (http://supervisor/discovery) so the Ontology integration's config
# flow can auto-detect and offer to connect to this Memgraph instance
# instead of requiring the user to enter host/port manually. Best-effort
# and non-blocking: runs in the background and must never fail or delay
# Memgraph startup.
register_discovery() {
  [ -z "${SUPERVISOR_TOKEN:-}" ] && return 0

  info=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    http://supervisor/addons/self/info 2>/dev/null) || return 0
  hostname=$(printf '%s' "$info" \
    | grep -o '"hostname"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -n1 \
    | sed -E 's/.*"([^"]*)"$/\1/')
  [ -z "$hostname" ] && return 0

  curl -sf -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"service\":\"ontology\",\"config\":{\"host\":\"${hostname}\",\"port\":7687}}" \
    http://supervisor/discovery >/dev/null 2>&1 || true
}
register_discovery &

exec /usr/lib/memgraph/memgraph \
  --data-directory=/data/memgraph/lib \
  --log-file=/data/memgraph/log/memgraph.log \
  --bolt-port=7687 \
  --also-log-to-stderr=true

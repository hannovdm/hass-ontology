#!/bin/sh
set -eu

TOKEN_FILE=/data/graphql/token
mkdir -p /data/memgraph/lib /data/memgraph/log /data/graphql /data/lab /run/ontology

if [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  openssl rand -hex 32 > "$TOKEN_FILE"
fi
chmod 600 "$TOKEN_FILE"
export GRAPHQL_BEARER_TOKEN="$(cat "$TOKEN_FILE")"
export MEMGRAPH_URI="bolt://127.0.0.1:7687"
export GRAPHQL_PORT=4000
export NODE_ENV=production

register_discovery() {
  [ -z "${SUPERVISOR_TOKEN:-}" ] && return 0

  info=$(curl -sf -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    http://supervisor/addons/self/info 2>/dev/null) || return 0
  hostname=$(printf '%s' "$info" \
    | grep -o '"hostname"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -n1 \
    | sed -E 's/.*"([^"]*)"$/\1/')
  [ -z "$hostname" ] && return 0

  payload=$(printf '{"service":"ontology","config":{"host":"%s","port":7687,"graphql_url":"http://%s:4000/graphql","graphql_token":"%s"}}' \
    "$hostname" "$hostname" "$GRAPHQL_BEARER_TOKEN")
  curl -sf -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    http://supervisor/discovery >/dev/null 2>&1 || true
}
register_discovery &

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf

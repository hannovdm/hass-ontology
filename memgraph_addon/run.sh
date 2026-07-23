#!/bin/sh
# Entrypoint for the Memgraph Home Assistant add-on.
#
# Persists Memgraph's storage and logs under /data (the add-on's persistent
# volume managed by the Home Assistant Supervisor) instead of the image's
# default in-container paths, so the ontology graph survives add-on
# restarts, host reboots, and add-on version upgrades.
set -e

mkdir -p /data/memgraph/lib /data/memgraph/log

exec /usr/lib/memgraph/memgraph \
  --data-directory=/data/memgraph/lib \
  --log-file=/data/memgraph/log/memgraph.log \
  --bolt-port=7687 \
  --also-log-to-stderr=true

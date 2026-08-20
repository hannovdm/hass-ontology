#!/bin/sh
set -u

memgraph=unhealthy
graphql=unhealthy
lab=unhealthy

if supervisorctl status memgraph 2>/dev/null | grep -q RUNNING; then
  memgraph=healthy
fi

if supervisorctl status graphql 2>/dev/null | grep -q RUNNING \
  && curl -sS --max-time 3 -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $(cat /data/graphql/token 2>/dev/null)" \
    -H 'Content-Type: application/json' \
    -d '{"operationName":"GraphHealth","query":"query GraphHealth { graphHealth { status } }"}' \
    http://127.0.0.1:4000/graphql | grep -q '^200$'; then
  graphql=healthy
fi

if supervisorctl status lab 2>/dev/null | grep -q RUNNING; then
  lab=healthy
fi

printf 'memgraph=%s graphql=%s lab=%s\n' "$memgraph" "$graphql" "$lab"
[ "$memgraph" = healthy ]

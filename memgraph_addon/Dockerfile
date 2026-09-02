# syntax=docker/dockerfile:1
FROM memgraph/lab:latest@sha256:f288113adc4a30c7a59fcf064af729dffa728ae6c4b8a7d9287286de0ec41cd6 AS lab
FROM node:26.8.1-bookworm-slim@sha256:367679cf9792759492a486e4aa4b421764d71a9546a6dae8aab81a99eb797b3e AS graphql

WORKDIR /opt/ontology-graphql
COPY graphql/package.json graphql/package-lock.json ./
RUN npm ci --omit=dev
COPY graphql/schema.graphql graphql/resolvers.js graphql/server.js ./

FROM memgraph/memgraph:3.12.0@sha256:c162cb9a6f76dac6080119da919d9b36e69c8b982af7bf34dd7df2b3723bd69c

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nodejs openssl supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY --from=graphql /opt/ontology-graphql /opt/ontology-graphql
COPY --from=graphql /usr/local/bin/node /usr/local/bin/node
COPY --from=lab /home/lab /opt/memgraph-lab
COPY --chmod=755 run.sh healthcheck.sh /usr/local/bin/
COPY supervisor.conf /etc/supervisor/conf.d/ontology.conf
COPY THIRD_PARTY_NOTICES.md /opt/ontology-licenses/THIRD_PARTY_NOTICES.md

EXPOSE 7687
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD ["/usr/local/bin/healthcheck.sh"]
ENTRYPOINT ["/usr/local/bin/run.sh"]

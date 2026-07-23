# syntax=docker/dockerfile:1
FROM memgraph/memgraph:3.12.0

# The base image drops to a non-root user by default. Our run.sh needs to
# create directories under the Supervisor-managed /data volume (which is
# typically root-owned on the host side), so run as root instead — this
# also avoids the "Operation not permitted" chmod failure below, since the
# base image's non-root user can't chmod a root-owned COPY'd file.
USER root

# curl is used by run.sh to announce this add-on to Home Assistant via the
# Supervisor Discovery API (http://supervisor/discovery), so the Ontology
# integration can auto-configure its connection instead of requiring the
# user to enter host/port manually.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Home Assistant Supervisor bind-mounts a per-add-on persistent volume at
# /data. Memgraph's own default storage/log locations live inside the
# container's writable layer, which does NOT survive an add-on update, so
# run.sh redirects both under /data before starting the database.
COPY --chmod=755 run.sh /run.sh

EXPOSE 7687

ENTRYPOINT [ "/run.sh" ]

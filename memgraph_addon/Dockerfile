FROM memgraph/memgraph:3.12.0

# Home Assistant Supervisor bind-mounts a per-add-on persistent volume at
# /data. Memgraph's own default storage/log locations live inside the
# container's writable layer, which does NOT survive an add-on update, so
# run.sh redirects both under /data before starting the database.
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 7687

ENTRYPOINT [ "/run.sh" ]

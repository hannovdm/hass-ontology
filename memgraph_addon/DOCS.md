# Home Assistant Add-on: Memgraph

## About

This add-on runs the official
[`memgraph/memgraph`](https://hub.docker.com/r/memgraph/memgraph) Docker
image, unmodified apart from redirecting its storage and log files into the
add-on's persistent `/data` volume. It provides a local, Bolt-protocol graph
database for the [Home Assistant Ontology](https://github.com/hannovdm/hass-ontology)
integration (or any other Bolt-compatible client).

## Configuration

This add-on has no configurable options — it always listens for Bolt
connections on port `7687` with no authentication configured, matching the
"local-first, no cloud dependency" design of the Ontology integration
(see [plan.md](../specs/001-ha-ontology-integration/plan.md)).

### Data persistence

Memgraph's data directory and log file are stored at
`/data/memgraph/lib` and `/data/memgraph/log/memgraph.log` inside the
add-on's persistent volume. This means:

- The graph survives add-on **restarts** and Home Assistant **reboots**.
- The graph survives **add-on updates** (rebuilding the Dockerfile against
  a newer Memgraph version does not discard `/data`).
- Uninstalling the add-on **and** removing its data (checked explicitly in
  the uninstall dialog) will delete the graph. A plain uninstall/reinstall
  without that option preserves it.

### Networking

The add-on exposes port `7687/tcp`, mapped 1:1 to the same port on the Home
Assistant host. Point the Ontology integration's config flow at:

- **Host**: the Home Assistant host's IP address (or a hostname that
  resolves to it, e.g. `homeassistant.local`)
- **Port**: `7687`

### Authentication

No users are created by default, matching Memgraph's own default (no
authentication) — this mirrors the "local, locally-hosted" trust model the
integration assumes. If you need authentication or encryption in your
environment, connect with `mgconsole` (`docker exec -it addon_local_memgraph
mgconsole` from the host, or use the **Terminal & SSH** add-on) and follow
[Memgraph's authentication docs](https://memgraph.com/docs/database-management/authentication-and-authorization)
to create a user, then re-enter those credentials in the integration's
config flow.

## Updating

Bumping the `version` in `config.yaml` and the base image tag in
`Dockerfile` to a newer Memgraph release, then reinstalling/rebuilding the
add-on, upgrades Memgraph in place — `/data` is preserved across the
rebuild. Check
[Memgraph's upgrade notes](https://memgraph.com/docs/database-management/upgrades)
before jumping multiple versions.

## Support

Issues specific to this add-on packaging should be filed against
[hannovdm/hass-ontology](https://github.com/hannovdm/hass-ontology/issues).
For issues with Memgraph itself, see the
[Memgraph documentation](https://memgraph.com/docs) or
[Memgraph Discord](https://discord.gg/memgraph).

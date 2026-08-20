# Home Assistant Add-on: Memgraph

## About

This add-on runs [Memgraph](https://memgraph.com/) — the graph database
backing the [Home Assistant Ontology](https://github.com/hannovdm/hass-ontology)
integration — alongside an authenticated internal GraphQL adapter and optional
Memgraph Lab access.  All data is persisted under the add-on's `/data` volume.

## Internal Architecture

The add-on runs three supervised processes:

| Process | Purpose |
|---------|---------|
| **Memgraph** | Bolt graph database on port 7687 (host-published). |
| **GraphQL adapter** | Read-only Apollo Server on internal port 4000. Never host-published. Requires bearer token generated at startup and stored at `/data/graphql/token`. |
| **Memgraph Lab** | Optional browser-based query tool on internal port 3000. Accessible **only** through Home Assistant Supervisor ingress. Never host-published. |

The GraphQL adapter and Memgraph Lab each fail independently — a crash in
either does not stop Memgraph or the Ontology integration.

## Configuration

This add-on has no configurable options. The Ontology integration
auto-discovers the GraphQL URL and bearer token via the Supervisor Discovery
API when both the integration and this add-on are installed.

## Memgraph Lab (Advanced Workspace)

Memgraph Lab is available **only** for Home Assistant administrators and
**only** when Memgraph Enterprise edition is running with a verified read-only
database user. Community edition does not enforce query authorization and is
therefore excluded.

### Enterprise + read-only setup

1. Connect to Memgraph as a privileged user (e.g. via the Terminal add-on):
   ```sh
   mgconsole --host 127.0.0.1 --port 7687
   ```
2. Create a read-only user with a password Memgraph will manage:
   ```cypher
   CREATE USER ontology_lab_readonly IDENTIFIED BY '<password>';
   GRANT READ ON GRAPHS * TO ontology_lab_readonly;
   ```
3. Restart the add-on.  The integration will run a write-rejection probe and
   mark Lab available once authorization is confirmed.

The add-on generates and stores the Lab user's password in `/data/lab/` with
owner-only permissions. It is never exposed through the WebSocket API,
diagnostics, browser responses, or logs.

### Upgrading

1. Update the add-on from the Home Assistant Supervisor.
2. Memgraph data under `/data` survives the upgrade.
3. If the Lab user password changes, restart the add-on — it re-reads the
   stored credential and re-runs the authorization probe.
4. Rolling back: downgrade the add-on version in Supervisor; data is
   preserved as long as the schema version is compatible.

## Troubleshooting

- **GraphQL not reachable**: check the add-on log for `[GraphQL]` lines.
  The integration falls back to a direct Bolt connection automatically.
- **Lab shows "Enterprise required"**: Community edition is running.
  Lab is unavailable by design.
- **Lab shows "Write probe succeeded"**: The Lab user has write access.
  Review the database privileges and restart the add-on.
- **Lab shows "Transport unavailable"**: The GraphQL adapter failed to
  start or crashed. Restart the add-on.

## Networking

| Port | Exposure | Purpose |
|------|----------|---------|
| 7687/tcp | Host-published | Bolt protocol (Ontology integration + external tools) |
| 4000/tcp | Internal only | GraphQL adapter (bearer-token authenticated) |
| 3000/tcp | Supervisor ingress only | Memgraph Lab (admin-only, Enterprise) |


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

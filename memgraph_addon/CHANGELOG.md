# Changelog

## 3.12.1

### New features

- **Authenticated internal GraphQL adapter** on port 4000 (bearer-token, internal-network only). Provides bounded, read-only graph queries for the Ontology Explorer panel without exposing Memgraph's Bolt port to browsers.
- **Supervised multi-process model**: Memgraph, GraphQL adapter, and Memgraph Lab each run as independent supervisor processes. A crash in GraphQL or Lab does not stop Memgraph or the Ontology integration.
- **Memgraph Lab via Supervisor ingress** (admin-only, Enterprise edition with verified read-only user). Lab is disabled by default and fails closed when Enterprise authorization cannot be proven.
- **Aggregate and component health probes**: `healthcheck.sh` reports degraded (not critical) when GraphQL or Lab fail, and only fails when Memgraph itself is unreachable.
- **Supervisor Discovery integration**: the add-on announces its GraphQL URL and bearer token through the Supervisor Discovery API so the Ontology integration can auto-configure without manual input.

### Process changes

- `run.sh` now generates a GraphQL bearer token at startup (`/data/graphql/token`, mode 0600) and starts Memgraph via `supervisord`.
- `supervisor.conf` now declares three programs: `memgraph` (priority 10), `graphql` (priority 20), and `lab` (priority 30, `autostart=false`).
- Ports 4000 (GraphQL) and 3000 (Lab) are **not** host-published.

## 3.12.0

- Initial release of the Memgraph add-on, wrapping `memgraph/memgraph:3.12.0`
  with persistent storage under `/data` for use with the Home Assistant
  Ontology integration.

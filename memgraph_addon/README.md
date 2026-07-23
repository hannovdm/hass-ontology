# Memgraph

Runs a [Memgraph](https://memgraph.com/) graph database as a Home Assistant
add-on, so it lives on the same host as Home Assistant OS / Supervised and
requires no separate server. This is the backing store used by the
[Home Assistant Ontology](https://github.com/hannovdm/hass-ontology) custom
integration.

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮** menu (top right) → **Repositories**, and add:
   `https://github.com/hannovdm/hass-ontology`
3. Find **Memgraph** in the store list and click **Install**.
4. Start the add-on. Leave **Start on boot** and **Watchdog** enabled so it
   comes back up automatically after a restart.
5. Install/configure the **Ontology** custom integration
   (**Settings → Devices & Services → Add Integration → Ontology**) using:
   - **Host**: your Home Assistant instance's IP address (or `localhost` /
     `homeassistant.local` if that resolves for your setup)
   - **Port**: `7687`
   - Leave username/password blank (no authentication is configured by
     default — see [DOCS.md](./DOCS.md) if you need to secure it).

See [DOCS.md](./DOCS.md) for configuration details and
[the integration's quickstart](../specs/001-ha-ontology-integration/quickstart.md)
for end-to-end validation steps.

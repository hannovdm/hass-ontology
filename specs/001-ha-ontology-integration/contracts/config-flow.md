# Contract: Config Flow (Devices & Services)

Defines the user-facing setup/options contract for the `ontology` integration, per FR-001, FR-002, FR-003, FR-004.

## Step: `user` (initial setup)

**Input schema**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `host` | string | yes | Memgraph Bolt host/IP. |
| `port` | integer | yes | Memgraph Bolt port (default `7687`). |
| `username` | string | no | Empty if Memgraph auth is disabled. |
| `password` | string | no | Stored only in the config entry; never logged (FR-004). |
| `database` | string | no | Optional named database (default: server default). |
| `encrypted` | boolean | no | Whether to use TLS for the Bolt connection (default `false` for local-only installs). |

**Behavior**:
1. On submit, attempt an async Bolt connection with a bounded timeout (research.md §6 governs retry policy for post-setup operation, but initial setup validation itself does not retry indefinitely — a single bounded attempt is used so the form fails fast).
2. **Success** → create the config entry; entry data stores `host`/`port`/`username`/`password`/`database`/`encrypted`.
3. **Failure** (connection refused, auth failure, timeout) → redisplay the form with an error keyed to `strings.json` (e.g., `cannot_connect`, `invalid_auth`), no config entry created (FR-002).

## Step: `reconfigure` / Options flow

**Input schema**: same fields as `user` step, pre-filled with current values (password masked/blank-to-keep-existing).

**Behavior**:
1. Re-validate the new connection exactly as in the `user` step before applying.
2. **Success** → update config entry data, trigger `async_reload_entry` (no manual file edits or HA restart required — FR-003).
3. **Failure** → keep the existing (previously validated) configuration active; show the same error keys as `user` step.

## Redaction contract

- `password` (and any future secret field) MUST be excluded from: debug logs, diagnostics payloads, exception messages, and repair issue text (FR-004, SC-007).
- Diagnostics/log output MAY show `host`, `port`, `username`, `database`, `encrypted` in the clear (non-secret).

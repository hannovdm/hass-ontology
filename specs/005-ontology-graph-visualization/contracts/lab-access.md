# Memgraph Lab Access Contract

## Availability Gate

Memgraph Lab is optional at runtime. The add-on owns every credential and database probe and MUST keep Lab unavailable unless all checks pass:

1. The requester is an authenticated Home Assistant administrator.
2. The Lab process is healthy inside the existing Memgraph add-on.
3. Memgraph Enterprise authorization is active.
4. A dedicated Lab database user is assigned `readonly` or equivalent privileges.
5. An add-on-local authenticated `MATCH ... RETURN` probe succeeds.
6. A write-intent probe is rejected by Memgraph authorization and leaves no graph change.
7. Lab quick-connect is configured with that dedicated user and the co-located database.

Community user authentication is not a substitute: official Memgraph documentation states that Community does not enforce query authorization.

## Routing

- Lab listens only on the add-on's internal port 3000.
- Home Assistant Supervisor ingress is the only browser route.
- No host mapping for port 3000 is published.
- Ingress uses a configured base path and supports required WebSocket traffic.
- Add-on panel metadata is administrator-only.
- The Ontology Explorer displays the launch action only after the admin-only `ontology/lab_status` command returns `available: true`.

## Credentials

- Generate the Lab user's password locally during add-on initialization and persist it under `/data` with owner-only permissions.
- Never return the password, Bolt URI, or internal hostname through WebSocket, diagnostics, logs, or UI.
- Lab receives credentials through server-side runtime configuration, not browser form input.
- Rotation requires restarting Lab and re-running both authorization probes.
- Expose only `LabCapability` through the authenticated internal GraphQL endpoint; Home Assistant never reads `/data` or receives the password.

## Read-only Proof

The capability probe must test enforcement, not configuration text alone:

1. Record a sentinel lookup result.
2. Attempt a transaction containing a unique temporary `CREATE` operation as the Lab user.
3. Require an authorization failure.
4. Verify the temporary node does not exist using the add-on's trusted database connection.
5. Mark Lab unavailable with reason `write_probe_succeeded` if the write is accepted or the verification is ambiguous.

The probe never runs through the browser and never exposes its temporary value.

## Failure Behavior

- Lab, ingress, or authorization failure does not stop Memgraph, GraphQL, Home Assistant setup, ontology sync, or the custom graph.
- The Ontology Explorer shows a concise admin-only unavailable reason and retry action.
- Re-probe after add-on restart, credential rotation, license change, or a bounded periodic interval.
- Log only result category and duration; never log credentials or generated queries.
- External/direct-Memgraph backends report `not_addon_backend`; Lab is unavailable while the custom graph remains functional.

## Acceptance Matrix

| Requester / Database | Custom graph | Lab action | Direct Lab access | Writes through Lab |
|----------------------|--------------|------------|-------------------|--------------------|
| Authenticated non-admin / any | allowed | hidden and backend-denied | denied | denied |
| Admin / Community | allowed | unavailable with Enterprise-required reason | denied | denied by absence of access |
| Admin / Enterprise, bad privileges | allowed | unavailable | denied | capability probe fails closed |
| Admin / Enterprise, verified readonly | allowed | available | ingress only | denied by Memgraph authorization |
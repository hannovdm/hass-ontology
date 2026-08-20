# Third-party artifacts

The add-on packages these immutable upstream artifacts:

- Memgraph `3.12.0`, `memgraph/memgraph:3.12.0@sha256:c162cb9a6f76dac6080119da919d9b36e69c8b982af7bf34dd7df2b3723bd69c`, for linux/amd64 and linux/arm64. Memgraph Community License: https://memgraph.com/legal/community-license
- Memgraph Lab, `memgraph/lab:latest@sha256:f288113adc4a30c7a59fcf064af729dffa728ae6c4b8a7d9287286de0ec41cd6`, for linux/amd64 and linux/arm64. Upstream licensing: https://github.com/memgraph/lab
- Node.js `22.18.0`, `node:22.18.0-bookworm-slim@sha256:752ea8a2f758c34002a0461bd9f1cee4f9a3c36d48494586f60ffce1fc708e0e`, for linux/amd64 and linux/arm64. Node.js license: https://github.com/nodejs/node/blob/main/LICENSE
- GraphQL.js `16.11.0` (MIT), Apollo Server `5.5.1` (MIT), and Neo4j JavaScript Driver `6.2.0` (Apache-2.0). Exact transitive versions and declared licenses are recorded in `graphql/package-lock.json`.

Cytoscape.js is integration-owned and is not packaged into this add-on image.
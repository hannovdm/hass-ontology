import { timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { pathToFileURL } from "node:url";

import { ApolloServer } from "@apollo/server";
import neo4j from "neo4j-driver";

import { createResolvers } from "./resolvers.js";

export const MAX_REQUEST_BODY_BYTES = 64 * 1024;
const REQUEST_TIMEOUT_MS = 10_000;

export function authorizeRequest(header, expectedToken) {
  if (!expectedToken || typeof header !== "string" || !header.startsWith("Bearer ")) {
    return false;
  }
  const supplied = Buffer.from(header.slice(7));
  const expected = Buffer.from(expectedToken);
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}

export async function readJsonBody(request) {
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > MAX_REQUEST_BODY_BYTES) throw new RangeError("Request body too large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

export function formatOperationLog(body, durationMs, category) {
  const operation = /^[A-Za-z][A-Za-z0-9_]*$/.test(body?.operationName || "")
    ? body.operationName
    : "anonymous";
  return `graphql operation=${operation} duration_ms=${durationMs} result=${category}`;
}

function sendJson(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
  });
  response.end(body);
}

async function withTimeout(promise) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_resolve, reject) => {
        timer = setTimeout(() => reject(new TimeoutError("GraphQL request timed out")), REQUEST_TIMEOUT_MS);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

export async function startGraphQLServer(environment = process.env) {
  const token = environment.GRAPHQL_BEARER_TOKEN;
  if (!token) throw new Error("GRAPHQL_BEARER_TOKEN is required");
  const typeDefs = await readFile(new URL("./schema.graphql", import.meta.url), "utf8");
  const driver = neo4j.driver(
    environment.MEMGRAPH_URI || "bolt://127.0.0.1:7687",
    environment.MEMGRAPH_USERNAME
      ? neo4j.auth.basic(environment.MEMGRAPH_USERNAME, environment.MEMGRAPH_PASSWORD || "")
      : undefined,
  );
  const runQuery = async (query, parameters) => {
    const session = driver.session();
    try {
      const result = await session.run(query, parameters);
      return result.records.map((record) => record.toObject());
    } finally {
      await session.close();
    }
  };
  const apollo = new ApolloServer({
    typeDefs,
    resolvers: createResolvers({ runQuery }),
    introspection: environment.NODE_ENV !== "production",
    persistedQueries: false,
  });
  await apollo.start();

  const httpServer = createServer(async (request, response) => {
    if (request.method !== "POST" || !["/", "/graphql"].includes(request.url)) {
      sendJson(response, 404, { error: "not_found" });
      return;
    }
    if (!authorizeRequest(request.headers.authorization, token)) {
      sendJson(response, 401, { error: "unauthorized" });
      return;
    }
    const started = Date.now();
    let requestBody;
    try {
      requestBody = await readJsonBody(request);
      const result = await withTimeout(apollo.executeOperation({
        query: requestBody.query,
        operationName: requestBody.operationName,
        variables: requestBody.variables,
      }));
      const payload = result.body.kind === "single"
        ? result.body.singleResult
        : { errors: [{ message: "Incremental delivery is not supported" }] };
      console.info(formatOperationLog(requestBody, Date.now() - started, payload.errors ? "error" : "ok"));
      sendJson(response, 200, payload);
    } catch (error) {
      const status = error instanceof RangeError ? 413 : error instanceof SyntaxError ? 400 : 503;
      console.warn(formatOperationLog(requestBody, Date.now() - started, "rejected"));
      sendJson(response, status, { error: status === 413 ? "request_too_large" : "gateway_unavailable" });
    }
  });
  httpServer.requestTimeout = REQUEST_TIMEOUT_MS + 1000;
  httpServer.headersTimeout = REQUEST_TIMEOUT_MS;
  await new Promise((resolve) => httpServer.listen(Number(environment.GRAPHQL_PORT || 4000), "0.0.0.0", resolve));

  const close = async () => {
    await new Promise((resolve) => httpServer.close(resolve));
    await apollo.stop();
    await driver.close();
  };
  return { httpServer, close };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const service = await startGraphQLServer();
  const shutdown = async () => {
    await service.close();
    process.exit(0);
  };
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
}

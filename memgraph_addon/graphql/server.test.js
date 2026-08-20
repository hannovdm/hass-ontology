import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildSchema } from "graphql";

import {
  MAX_REQUEST_BODY_BYTES,
  authorizeRequest,
  formatOperationLog,
  readJsonBody,
} from "./server.js";

const schemaPath = new URL("./schema.graphql", import.meta.url);

test("schema exposes only the fixed query operations", async () => {
  const typeDefs = await readFile(schemaPath, "utf8");
  const schema = buildSchema(typeDefs);

  assert.equal(schema.getMutationType(), undefined);
  assert.deepEqual(
    Object.keys(schema.getQueryType().getFields()).sort(),
    [
      "expandNode",
      "graphElement",
      "graphHealth",
      "initialGraph",
      "labCapability",
      "searchGraph",
    ],
  );
  assert.doesNotMatch(typeDefs, /\b(cypher|mutation)\b/i);
});

test("bearer authentication rejects missing and mismatched tokens", () => {
  assert.equal(authorizeRequest(undefined, "expected"), false);
  assert.equal(authorizeRequest("Bearer wrong", "expected"), false);
  assert.equal(authorizeRequest("Bearer expected", "expected"), true);
});

test("request reader rejects bodies beyond the fixed byte limit", async () => {
  const request = {
    async *[Symbol.asyncIterator]() {
      yield Buffer.alloc(MAX_REQUEST_BODY_BYTES + 1, "x");
    },
  };

  await assert.rejects(readJsonBody(request), /request body too large/i);
});

test("operation logging contains no variables, token, or query text", () => {
  const line = formatOperationLog({
    operationName: "GraphHealth",
    query: "query GraphHealth { graphHealth { status } }",
    variables: { token: "secret", home: "Kitchen" },
  }, 7, "ok");

  assert.match(line, /GraphHealth/);
  assert.match(line, /7/);
  assert.doesNotMatch(line, /secret|Kitchen|graphHealth\s*\{/);
});

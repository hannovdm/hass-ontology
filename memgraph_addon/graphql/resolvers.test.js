import assert from "node:assert/strict";
import test from "node:test";

import {
  HARD_LIMITS,
  createResolvers,
  serializeGraphNode,
  serializeGraphRelationship,
} from "./resolvers.js";

test("initialGraph uses fixed parameterized Cypher and clamps its limit", async () => {
  const calls = [];
  const resolvers = createResolvers({
    runQuery: async (query, parameters) => {
      calls.push({ query, parameters });
      return [];
    },
  });

  const result = await resolvers.Query.initialGraph(null, { limit: 9999 });

  assert.equal(calls.length, 1);
  assert.match(calls[0].query, /\$limit/);
  assert.doesNotMatch(calls[0].query, /9999/);
  assert.equal(calls[0].parameters.limit, HARD_LIMITS.initialNodes + 1);
  assert.deepEqual(result.nodes, []);
  assert.equal(result.pageInfo.truncated, false);
  assert.match(calls[0].query, /MATCH \(n:Area\)/);
  assert.doesNotMatch(calls[0].query, /n:Device/);
  assert.match(calls[0].query, /startNode\(r\).*ha_id/s);
  assert.match(calls[0].query, /endNode\(r\).*ha_id/s);
});

test("projected relationships preserve stable graph endpoints", () => {
  const relationship = serializeGraphRelationship({
    type: "HAS_DEVICE",
    source: "Area:kitchen",
    target: "Device:lamp",
    id: "primary",
    sourceClass: "home_assistant",
    properties: { source: "home_assistant" },
  });

  assert.equal(relationship.id, "HAS_DEVICE:Area:kitchen:Device:lamp:primary");
  assert.equal(relationship.source, "Area:kitchen");
  assert.equal(relationship.target, "Device:lamp");
  assert.equal(relationship.sourceClass, "home_assistant");
});

test("expand and search reject unsafe or unbounded caller values", async () => {
  const calls = [];
  const resolvers = createResolvers({
    runQuery: async (query, parameters) => {
      calls.push({ query, parameters });
      return [];
    },
  });

  await resolvers.Query.expandNode(null, {
    id: "Entity:sensor.kitchen",
    nodeLimit: 9999,
    edgeLimit: 9999,
  });
  await resolvers.Query.searchGraph(null, { term: " kitchen ", limit: 9999 });

  assert.equal(calls[0].parameters.id, "Entity:sensor.kitchen");
  assert.equal(calls[0].parameters.nodeLimit, HARD_LIMITS.expandNodes + 1);
  assert.equal(calls[0].parameters.edgeLimit, HARD_LIMITS.expandEdges + 1);
  assert.equal(calls[1].parameters.term, "kitchen");
  assert.equal(calls[1].parameters.limit, HARD_LIMITS.search + 1);
  for (const call of calls) {
    assert.doesNotMatch(call.query, /\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL)\b/i);
  }
});

test("safe serialization produces stable IDs and bounded redacted properties", () => {
  const node = serializeGraphNode({
    labels: ["Entity"],
    properties: {
      ha_id: "sensor.kitchen",
      name: "Kitchen Sensor",
      access_token: "must-not-leak",
      state: "x".repeat(4096),
      ...Object.fromEntries(
        Array.from({ length: 30 }, (_, index) => [`safe_${index}`, index]),
      ),
    },
  });

  assert.equal(node.id, "Entity:sensor.kitchen");
  assert.equal(node.haId, "sensor.kitchen");
  assert.equal(node.label, "Kitchen Sensor");
  assert.equal(node.properties.length, 25);
  assert.equal(node.properties.some(({ name }) => name === "access_token"), false);
  assert.ok(node.properties.every(({ displayValue }) => displayValue.length <= 2048));
});

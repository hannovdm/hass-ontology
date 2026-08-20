import { GraphQLScalarType, Kind } from "graphql";

export const HARD_LIMITS = Object.freeze({
  initialNodes: 100,
  initialEdges: 100,
  expandNodes: 250,
  expandEdges: 500,
  search: 100,
  properties: 25,
  propertyBytes: 2048,
});

const NODE_TYPES = new Map([
  ["Area", "AREA"],
  ["Device", "DEVICE"],
  ["Entity", "ENTITY"],
  ["Automation", "AUTOMATION"],
  ["Scene", "SCENE"],
  ["Script", "SCRIPT"],
  ["Dashboard", "DASHBOARD"],
  ["DashboardCard", "DASHBOARD_CARD"],
  ["SemanticType", "SEMANTIC_TYPE"],
  ["ValidationFinding", "VALIDATION_FINDING"],
]);
const SAFE_PROPERTY = /^[A-Za-z_][A-Za-z0-9_]*$/;
const SENSITIVE_PROPERTY = /(password|passphrase|secret|token|credential|connection|uri|url|host)/i;
const CONTROL_CHARACTER = /[\u0000-\u001f\u007f]/;

const INITIAL_GRAPH_QUERY = `
MATCH (n)
WHERE n:Area OR n:Device
WITH n ORDER BY CASE WHEN n:Area THEN 0 ELSE 1 END, coalesce(n.name, n.ha_id), n.ha_id
WITH collect(n)[0..$limit] AS nodes
OPTIONAL MATCH (a:Area)-[r:HAS_DEVICE]->(d:Device)
WHERE a IN nodes AND d IN nodes
RETURN nodes, collect(r)[0..$edgeLimit] AS relationships
`;
const EXPAND_NODE_QUERY = `
MATCH (center)
WHERE any(label IN labels(center) WHERE label + ':' + center.ha_id = $id)
OPTIONAL MATCH (center)-[r]-(neighbor)
WITH center, r, neighbor ORDER BY coalesce(neighbor.name, neighbor.ha_id), type(r)
RETURN [center] + collect(DISTINCT neighbor)[0..$nodeLimit] AS nodes,
       collect(DISTINCT r)[0..$edgeLimit] AS relationships
`;
const SEARCH_GRAPH_QUERY = `
MATCH (n)
WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($term)
   OR toLower(coalesce(n.ha_id, '')) CONTAINS toLower($term)
RETURN n ORDER BY coalesce(n.name, n.ha_id), n.ha_id LIMIT $limit
`;
const GRAPH_ELEMENT_QUERY = `
MATCH (element)
WHERE any(label IN labels(element) WHERE label + ':' + element.ha_id = $id)
OPTIONAL MATCH (element)-[r]-(neighbor)
RETURN element, collect(DISTINCT neighbor)[0..26] AS nodes,
       collect(DISTINCT r)[0..51] AS relationships
`;
const GRAPH_HEALTH_QUERY = "RETURN 1 AS healthy";

function clamp(value, defaultValue, hardLimit) {
  const parsed = Number.isInteger(value) ? value : defaultValue;
  return Math.max(1, Math.min(parsed, hardLimit));
}

function boundedString(value, limit = HARD_LIMITS.propertyBytes) {
  return String(value ?? "").replace(CONTROL_CHARACTER, "").slice(0, limit);
}

function scalarValue(value) {
  if (value === null || ["string", "number", "boolean"].includes(typeof value)) {
    return typeof value === "string" ? boundedString(value) : value;
  }
  return boundedString(JSON.stringify(value));
}

function graphProperties(properties = {}) {
  return Object.entries(properties)
    .filter(([name]) => SAFE_PROPERTY.test(name) && !SENSITIVE_PROPERTY.test(name))
    .sort(([left], [right]) => left.localeCompare(right))
    .slice(0, HARD_LIMITS.properties)
    .map(([name, rawValue]) => {
      const value = scalarValue(rawValue);
      return { name, value, displayValue: boundedString(value) };
    });
}

function rawProperties(value) {
  if (!value) return {};
  if (value.properties) return value.properties;
  if (typeof value === "object") return value;
  return {};
}

function rawLabels(value) {
  const labels = value?.labels;
  if (!labels) return [];
  return Array.isArray(labels) ? labels : [...labels];
}

function stableNodeId(value) {
  const properties = rawProperties(value);
  const label = rawLabels(value).sort()[0] || properties.type || "Other";
  const haId = boundedString(properties.ha_id || properties.id);
  if (!haId || CONTROL_CHARACTER.test(haId)) {
    throw new TypeError("Graph node is missing a safe stable identifier");
  }
  return `${label}:${haId}`;
}

export function serializeGraphNode(value) {
  const properties = rawProperties(value);
  const labels = rawLabels(value);
  const canonicalLabel = labels.find((label) => NODE_TYPES.has(label)) || "Other";
  const haId = boundedString(properties.ha_id || properties.id);
  const label = boundedString(properties.name || properties.friendly_name || haId, 256);
  return {
    id: stableNodeId(value),
    haId,
    type: NODE_TYPES.get(canonicalLabel) || "OTHER",
    label,
    icon: /^mdi:[a-z0-9-]+$/.test(properties.icon || "") ? properties.icon : null,
    state: properties.state == null ? null : boundedString(properties.state, 256),
    unavailable: ["unknown", "unavailable"].includes(String(properties.state).toLowerCase()),
    findingSeverity: properties.severity ? String(properties.severity).toUpperCase() : null,
    properties: graphProperties(properties),
  };
}

function relationshipEndpoint(value, side) {
  const node = value?.[`${side}_node`] || value?.[`${side}Node`];
  if (node) return stableNodeId(node);
  const properties = rawProperties(value);
  return boundedString(properties[side]);
}

export function serializeGraphRelationship(value) {
  const properties = rawProperties(value);
  const type = boundedString(value?.type || properties.type, 128) || "RELATED_TO";
  const source = relationshipEndpoint(value, "start") || boundedString(properties.source);
  const target = relationshipEndpoint(value, "end") || boundedString(properties.target);
  const discriminator = boundedString(properties.ha_id || properties.id || "0", 128);
  return {
    id: `${type}:${source}:${target}:${discriminator}`,
    type,
    source,
    target,
    directed: true,
    sourceClass: properties.source ? String(properties.source).toUpperCase() : null,
    properties: graphProperties(properties),
  };
}

function firstRecord(rows) {
  return rows?.[0] || {};
}

function graphSlice(rows, nodeLimit, edgeLimit, revision) {
  const record = firstRecord(rows);
  const rawNodes = record.nodes || [];
  const rawRelationships = record.relationships || [];
  const truncated = rawNodes.length > nodeLimit || rawRelationships.length > edgeLimit;
  return {
    nodes: rawNodes.slice(0, nodeLimit).filter(Boolean).map(serializeGraphNode),
    relationships: rawRelationships
      .slice(0, edgeLimit)
      .filter(Boolean)
      .map(serializeGraphRelationship),
    pageInfo: { truncated, nextCursor: null },
    revision,
  };
}

export function createResolvers({ runQuery, getRevision = () => 0 } = {}) {
  if (typeof runQuery !== "function") throw new TypeError("runQuery is required");
  return {
    GraphScalar: new GraphQLScalarType({
      name: "GraphScalar",
      serialize: scalarValue,
      parseValue: scalarValue,
      parseLiteral(ast) {
        if ([Kind.STRING, Kind.BOOLEAN, Kind.INT, Kind.FLOAT].includes(ast.kind)) {
          return scalarValue(ast.value);
        }
        if (ast.kind === Kind.NULL) return null;
        throw new TypeError("GraphScalar accepts scalar values only");
      },
    }),
    Query: {
      async initialGraph(_parent, { limit = 100 } = {}) {
        const bounded = clamp(limit, 100, HARD_LIMITS.initialNodes);
        const rows = await runQuery(INITIAL_GRAPH_QUERY, {
          limit: bounded + 1,
          edgeLimit: HARD_LIMITS.initialEdges + 1,
        });
        return graphSlice(rows, bounded, HARD_LIMITS.initialEdges, getRevision());
      },
      async expandNode(_parent, { id, nodeLimit = 25, edgeLimit = 50 }) {
        const boundedNodes = clamp(nodeLimit, 25, HARD_LIMITS.expandNodes);
        const boundedEdges = clamp(edgeLimit, 50, HARD_LIMITS.expandEdges);
        const rows = await runQuery(EXPAND_NODE_QUERY, {
          id: boundedString(id, 512),
          nodeLimit: boundedNodes + 1,
          edgeLimit: boundedEdges + 1,
        });
        return graphSlice(rows, boundedNodes, boundedEdges, getRevision());
      },
      async searchGraph(_parent, { term, limit = 50 }) {
        const cleanedTerm = boundedString(term, 256).trim();
        if (!cleanedTerm) throw new TypeError("Search term is required");
        const bounded = clamp(limit, 50, HARD_LIMITS.search);
        const rows = await runQuery(SEARCH_GRAPH_QUERY, {
          term: cleanedTerm,
          limit: bounded + 1,
        });
        const nodes = rows.map((row) => serializeGraphNode(row.n || row.node || row));
        return {
          matches: nodes.slice(0, bounded).map(({ id, haId, type, label, icon }) => ({
            id, haId, type, label, icon,
          })),
          truncated: nodes.length > bounded,
          revision: getRevision(),
        };
      },
      async graphElement(_parent, { id }) {
        const rows = await runQuery(GRAPH_ELEMENT_QUERY, { id: boundedString(id, 512) });
        if (!rows.length) return null;
        const record = firstRecord(rows);
        return {
          node: record.element ? serializeGraphNode(record.element) : null,
          relationship: null,
          directConnections: graphSlice(rows, 25, 50, getRevision()),
        };
      },
      async graphHealth() {
        const started = Date.now();
        await runQuery(GRAPH_HEALTH_QUERY, {});
        return { status: "HEALTHY", revision: getRevision(), latencyMs: Date.now() - started };
      },
      labCapability() {
        return {
          available: false,
          reason: "ENTERPRISE_REQUIRED",
          ingressPath: null,
          checkedAt: new Date().toISOString(),
        };
      },
    },
  };
}

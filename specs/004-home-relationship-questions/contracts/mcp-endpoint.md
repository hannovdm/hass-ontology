# Local MCP Endpoint Contract

The existing endpoint remains opt-in, authenticated, network-admitted, read-only, bounded, redacted, and audited. Feature 004 adds five tools that delegate directly to the shared read operations.

## Tools

```json
{
  "name": "low_battery_areas",
  "inputSchema": {
    "type": "object",
    "properties": {
      "threshold_percentage": {"type": "number", "minimum": 1, "maximum": 100},
      "max_age_hours": {"type": "number", "exclusiveMinimum": 0},
      "limit": {"type": "integer", "minimum": 1}
    },
    "additionalProperties": false
  }
}
```

```json
{
  "name": "active_consumers",
  "inputSchema": {
    "type": "object",
    "properties": {
      "threshold_watts": {"type": "number", "minimum": 0},
      "max_age_hours": {"type": "number", "exclusiveMinimum": 0},
      "limit": {"type": "integer", "minimum": 1}
    },
    "additionalProperties": false
  }
}
```

```json
{
  "name": "automation_dependencies",
  "inputSchema": {
    "type": "object",
    "required": ["target"],
    "properties": {
      "target": {"type": "string", "minLength": 1},
      "limit": {"type": "integer", "minimum": 1}
    },
    "additionalProperties": false
  }
}
```

```json
{
  "name": "supplied_targets",
  "inputSchema": {
    "type": "object",
    "required": ["cylinder"],
    "properties": {
      "cylinder": {"type": "string", "minLength": 1},
      "limit": {"type": "integer", "minimum": 1}
    },
    "additionalProperties": false
  }
}
```

```json
{
  "name": "device_context",
  "inputSchema": {
    "type": "object",
    "required": ["device"],
    "properties": {
      "device": {"type": "string", "minLength": 1},
      "limit": {"type": "integer", "minimum": 1}
    },
    "additionalProperties": false
  }
}
```

At dispatch, `limit` is capped by the integration's configured maximum. Successful tool content serializes the shared `ToolResult` envelope. Invalid arguments, disabled endpoint, failed authentication/admission, and degraded graph access retain existing safe MCP error behavior.

No supply or energy-role mutation tool is advertised or dispatched. Audit records include tool name, channel, outcome, result count, truncation, timestamp, and sanitized error category only.

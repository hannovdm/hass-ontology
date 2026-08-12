"""Constants for the Ontology integration."""

from __future__ import annotations

DOMAIN = "ontology"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DATABASE = "database"
CONF_ENCRYPTED = "encrypted"

DEFAULT_PORT = 7687
DEFAULT_DATABASE = ""
DEFAULT_ENCRYPTED = False

# Options-flow keys (v2)
CONF_AUTO_CLASSIFY = "auto_classify"
DEFAULT_AUTO_CLASSIFY = True

# Ontology schema version (Constitution Principle VI). Bump whenever labels,
# relationship types, required properties, or graph semantics change.
SCHEMA_VERSION = "2.0.0"
SCHEMA_SINGLETON_ID = "home_assistant_ontology"
HOME_SINGLETON_ID = "home"

# Data-model source tags (Constitution Principle V / data-model.md)
SOURCE_HOME_ASSISTANT = "home_assistant"
SOURCE_GENERATED = "generated"
SOURCE_INFERRED = "inferred"
SOURCE_USER = "user"

# Sources the integration itself owns and may clear/regenerate on rebuild.
# Anything else (SOURCE_INFERRED, SOURCE_USER) must never be deleted.
INTEGRATION_OWNED_SOURCES = (SOURCE_HOME_ASSISTANT, SOURCE_GENERATED)

# Debounce window for state_changed events (research.md §5)
STATE_CHANGE_DEBOUNCE_SECONDS = 3.0

# How often to automatically retry queued failed_updates (FR-020). A burst of
# many entities changing state at once (e.g. right after a restart) can
# exceed the single-pending-slot serialization (FR-013a) and get rejected;
# this periodic sweep drains that backlog without any user action.
FAILED_UPDATE_RETRY_INTERVAL_SECONDS = 300.0

# Retry/backoff policy for Memgraph operations (research.md §6)
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 60.0
RETRY_MAX_ATTEMPTS = 5

# Number of consecutive full-sync failures before raising a repair issue
SUSTAINED_FAILURE_THRESHOLD = 3

# Bounded timeout for a single connectivity check / config-flow validation
CONNECTION_TIMEOUT_SECONDS = 10.0

# Repair issue ids (contracts/diagnostics.md)
ISSUE_SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
ISSUE_SUSTAINED_CONNECTION_FAILURE = "sustained_connection_failure"

# Services (contracts/services.md)
SERVICE_REBUILD = "rebuild"
SERVICE_RESYNC = "resync"
SERVICE_SYNC_ENTITY = "sync_entity"
SERVICE_VALIDATE = "validate"
ATTR_ENTITY_ID = "entity_id"

# Services (contracts/services.md v2 additions)
SERVICE_QUERY = "query"
SERVICE_REFRESH_SEMANTICS = "refresh_semantics"
SERVICE_EXPORT_OVERRIDES = "export_overrides"
SERVICE_IMPORT_OVERRIDES = "import_overrides"
ATTR_CYPHER = "cypher"
ATTR_PARAMETERS = "parameters"
ATTR_LIMIT = "limit"
ATTR_PAYLOAD = "payload"

# ontology.query row-limit defaults (FR-018, FR-021)
DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 1000

# ontology/search default result cap (contracts/websocket-api.md)
DEFAULT_SEARCH_LIMIT = 50

# Cypher keywords rejected by the read-only query safety validator
# (Constitution Principle X, research.md §3). Matched case-insensitively,
# word-boundary, after comments/string literals are stripped.
QUERY_DENYLIST_KEYWORDS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "DROP",
    "LOAD CSV",
    "CALL DBMS",
    "CALL MG",
    "CALL ALGO",
)

# Override export/import payload version (research.md §7)
OVERRIDES_EXPORT_VERSION = 1

# Validation finding categories (data-model.md ValidationFinding, research.md §6)
FINDING_MISSING_AREA = "missing_area"
FINDING_MISSING_DEVICE = "missing_device"
FINDING_ORPHAN_ENTITY = "orphan_entity"
FINDING_ORPHAN_DEVICE = "orphan_device"
FINDING_DUPLICATE_ENTITY = "duplicate_entity"
FINDING_UNAVAILABLE_CRITICAL_ENTITY = "unavailable_critical_entity"
FINDING_INVALID_RELATIONSHIP = "invalid_relationship"
FINDING_SCHEMA_MISMATCH = "schema_mismatch"
FINDING_MISSING_SEMANTIC_CLASSIFICATION = "missing_semantic_classification"

VALIDATION_FINDING_CATEGORIES = (
    FINDING_MISSING_AREA,
    FINDING_MISSING_DEVICE,
    FINDING_ORPHAN_ENTITY,
    FINDING_ORPHAN_DEVICE,
    FINDING_DUPLICATE_ENTITY,
    FINDING_UNAVAILABLE_CRITICAL_ENTITY,
    FINDING_INVALID_RELATIONSHIP,
    FINDING_SCHEMA_MISMATCH,
    FINDING_MISSING_SEMANTIC_CLASSIFICATION,
)

# ValidationFinding severities/status (data-model.md ValidationFinding)
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

FINDING_STATUS_OPEN = "open"
FINDING_STATUS_RESOLVED = "resolved"

# websocket_api command types (contracts/websocket-api.md, US3)
WS_TYPE_AREA_CONTEXT = "ontology/area_context"
WS_TYPE_ENTITY_CONTEXT = "ontology/entity_context"
WS_TYPE_SEARCH = "ontology/search"
ATTR_AREA_ID = "area_id"
ATTR_QUERY = "query"

# Health states (contracts/diagnostics.md)
HEALTH_OK = "ok"
HEALTH_ERROR = "error"
HEALTH_UNAVAILABLE = "unavailable"

PLATFORMS = ["sensor", "button"]

# Node labels (data-model.md "Nodes")
LABEL_HOME = "Home"
LABEL_FLOOR = "Floor"
LABEL_AREA = "Area"
LABEL_DEVICE = "Device"
LABEL_ENTITY = "Entity"
LABEL_DOMAIN = "Domain"
LABEL_INTEGRATION = "Integration"
LABEL_LABEL = "Label"
LABEL_AUTOMATION = "Automation"
LABEL_SCENE = "Scene"
LABEL_SCRIPT = "Script"
LABEL_ONTOLOGY_SCHEMA = "OntologySchema"

# Relationship types (data-model.md "Relationships")
REL_HAS_AREA = "HAS_AREA"
REL_HAS_FLOOR = "HAS_FLOOR"
REL_ON_FLOOR = "ON_FLOOR"
REL_HAS_DEVICE = "HAS_DEVICE"
REL_HAS_ENTITY = "HAS_ENTITY"
REL_IN_DOMAIN = "IN_DOMAIN"
REL_PROVIDED_BY = "PROVIDED_BY"
REL_HAS_LABEL = "HAS_LABEL"
REL_REFERENCES = "REFERENCES"
REL_CONTROLS = "CONTROLS"

# Node labels (data-model.md v2 additions)
LABEL_SEMANTIC_TYPE = "SemanticType"
LABEL_GAS_CYLINDER = "GasCylinder"
LABEL_VEHICLE = "Vehicle"
LABEL_ENERGY_ASSET = "EnergyAsset"
LABEL_SECURITY_DEVICE = "SecurityDevice"
LABEL_OCCUPANCY_SENSOR = "OccupancySensor"
LABEL_CLIMATE_DEVICE = "ClimateDevice"
LABEL_NETWORK_DEVICE = "NetworkDevice"
LABEL_BATTERY_POWERED_DEVICE = "BatteryPoweredDevice"
LABEL_DASHBOARD = "Dashboard"
LABEL_DASHBOARD_CARD = "DashboardCard"
LABEL_VALIDATION_FINDING = "ValidationFinding"

# All semantic asset labels (1:1 with the classified Entity, data-model.md)
SEMANTIC_TYPE_LABELS = (
    LABEL_GAS_CYLINDER,
    LABEL_VEHICLE,
    LABEL_ENERGY_ASSET,
    LABEL_SECURITY_DEVICE,
    LABEL_OCCUPANCY_SENSOR,
    LABEL_CLIMATE_DEVICE,
    LABEL_NETWORK_DEVICE,
    LABEL_BATTERY_POWERED_DEVICE,
)

# Relationship types (data-model.md v2 additions)
REL_CLASSIFIED_AS = "CLASSIFIED_AS"
REL_MEASURED_BY = "MEASURED_BY"
REL_LOCATED_IN = "LOCATED_IN"
REL_OBSERVED_BY = "OBSERVED_BY"
REL_CONTAINS_CARD = "CONTAINS_CARD"
REL_DISPLAYS_ENTITY = "DISPLAYS_ENTITY"
REL_RELATES_TO = "RELATES_TO"
REL_OVERRIDE_OF = "OVERRIDE_OF"

# Domains treated as "scriptable" entities that reference other entities
AUTOMATION_DOMAIN = "automation"
SCENE_DOMAIN = "scene"
SCRIPT_DOMAIN = "script"

# --- v3: Assist, MCP, impact analysis, local AI readiness -----------------

# Services (contracts/services.md v3 additions)
SERVICE_SEARCH = "search"
SERVICE_AREA_CONTEXT = "area_context"
SERVICE_DEVICE_CONTEXT = "device_context"
SERVICE_ENTITY_CONTEXT = "entity_context"
SERVICE_AUTOMATION_DEPENDENCIES = "automation_dependencies"
SERVICE_IMPACT_ANALYSIS = "impact_analysis"
SERVICE_EXPORT_CONTEXT = "export_context"

ATTR_TERM = "term"
ATTR_AREA = "area"
ATTR_DEVICE = "device"
ATTR_ENTITY = "entity"
ATTR_TARGET_TYPE = "target_type"
ATTR_TARGET = "target"
ATTR_EXPORT_TYPE = "export_type"

# Options-flow key: opt-in local MCP-compatible endpoint (research.md §8,
# FR-023). Must default to False - the endpoint MUST be disabled on fresh
# install/upgrade (SC-003).
CONF_MCP_ENABLED = "mcp_enabled"
DEFAULT_MCP_ENABLED = False
CONF_MCP_ALLOWED_NETWORKS = "mcp_allowed_networks"
DEFAULT_MCP_ALLOWED_NETWORKS = "127.0.0.0/8, ::1/128"

# `homeassistant.helpers.storage.Store` key prefixes (research.md §3, §4).
# Each is suffixed with the config entry's `entry_id` to scope the file per
# entry, mirroring how the MCP token/audit log are described in data-model.md
# §5. These are plain local JSON files, never Memgraph nodes (FR-035).
MCP_TOKEN_STORE_KEY_PREFIX = "ontology_mcp_token_"
MCP_TOKEN_STORE_VERSION = 1
AGENT_AUDIT_STORE_KEY_PREFIX = "ontology_agent_audit_"
AGENT_AUDIT_STORE_VERSION = 1

# Redacted Assist/MCP audit log retention window (FR-036). Applied on every
# append and via the periodic sweep (research.md §4).
AGENT_AUDIT_RETENTION_DAYS = 30
AGENT_AUDIT_SWEEP_INTERVAL_SECONDS = 3600.0

# Bounded-depth impact-analysis traversal hop limit (research.md §5). Kept
# small and fixed (no user-configurable traversal depth) so SC-005's <3s
# target is achievable on a several-thousand-node graph.
IMPACT_ANALYSIS_ENTITY_HOP_LIMIT = 2

# Result-shape discriminators for the shared `ToolResult` envelope
# (data-model.md §2).
RESULT_TYPE_SEARCH = "search"
RESULT_TYPE_AREA_CONTEXT = "area_context"
RESULT_TYPE_DEVICE_CONTEXT = "device_context"
RESULT_TYPE_ENTITY_CONTEXT = "entity_context"
RESULT_TYPE_AUTOMATION_DEPENDENCIES = "automation_dependencies"
RESULT_TYPE_IMPACT_ANALYSIS = "impact_analysis"
RESULT_TYPE_QUERY = "query"
RESULT_TYPE_EXPORT_CONTEXT = "export_context"
RESULT_TYPE_NOT_FOUND = "not_found"

# Impact-analysis scopes (data-model.md §3)
IMPACT_SCOPE_ENTITY = "entity"
IMPACT_SCOPE_DEVICE = "device"
IMPACT_SCOPE_AREA = "area"
IMPACT_SCOPES = (IMPACT_SCOPE_ENTITY, IMPACT_SCOPE_DEVICE, IMPACT_SCOPE_AREA)

# Context-export types (contracts/services.md `ontology.export_context`)
EXPORT_TYPE_AREA = "area"
EXPORT_TYPE_ENTITY = "entity"
EXPORT_TYPE_DEVICE = "device"
EXPORT_TYPE_AUTOMATION = "automation"
EXPORT_TYPE_IMPACT = "impact"
EXPORT_TYPE_WHOLE_HOME = "whole_home"
EXPORT_TYPES = (
    EXPORT_TYPE_AREA,
    EXPORT_TYPE_ENTITY,
    EXPORT_TYPE_DEVICE,
    EXPORT_TYPE_AUTOMATION,
    EXPORT_TYPE_IMPACT,
    EXPORT_TYPE_WHOLE_HOME,
)

# Allow-list field projection table (data-model.md §4). Extending this
# requires updating both `context_export.py` and this table - fields not
# listed here are never included in an export document, regardless of
# whether they exist on the underlying node (FR-020, SC-002).
CONTEXT_EXPORT_ALLOWED_FIELDS: dict[str, tuple[str, ...]] = {
    LABEL_AREA: ("ha_id", "name", "floor_id"),
    LABEL_DEVICE: ("ha_id", "name", "manufacturer", "model", "area_id"),
    LABEL_ENTITY: (
        "ha_id",
        "name",
        "domain",
        "device_class",
        "unit_of_measurement",
        "area_id",
        "device_id",
        "source",
    ),
    LABEL_DOMAIN: ("ha_id",),
    LABEL_INTEGRATION: ("ha_id", "name"),
    LABEL_AUTOMATION: ("ha_id", "name", "mode"),
    LABEL_SCENE: ("ha_id", "name"),
    LABEL_SCRIPT: ("ha_id", "name"),
    LABEL_SEMANTIC_TYPE: ("ha_id", "asset_type", "entity_id"),
    LABEL_VALIDATION_FINDING: ("finding_type", "severity", "target_id", "message"),
    LABEL_DASHBOARD: ("ha_id", "title"),
    LABEL_DASHBOARD_CARD: ("ha_id", "title"),
}

# MCP endpoint (research.md §2, contracts/mcp-endpoint.md)
MCP_ENDPOINT_URL = "/api/ontology/mcp"
MCP_TOOL_NAMES = (
    "search",
    "entity_context",
    "area_context",
    "device_context",
    "automation_dependencies",
    "impact_analysis",
    "query",
    "export_context",
)

# Agent-audit event names (data-model.md §5)
AUDIT_EVENT_ASSIST_QUERY = "assist_query"
AUDIT_EVENT_MCP_TOOL_CALL = "mcp_tool_call"
AUDIT_EVENT_MCP_WRITE_REJECTED = "mcp_write_rejected"
AUDIT_EVENT_MCP_AUTH_REJECTED = "mcp_auth_rejected"
AUDIT_EVENT_IMPACT_ANALYSIS = "impact_analysis"
AUDIT_EVENT_CONTEXT_EXPORT = "context_export"

# button.py control entity for MCP token regeneration (research.md §3)
BUTTON_KEY_REGENERATE_MCP_TOKEN = "regenerate_mcp_token"


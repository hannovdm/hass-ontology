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
CONF_GRAPHQL_URL = "graphql_url"
CONF_GRAPHQL_TOKEN = "graphql_token"

DEFAULT_PORT = 7687
DEFAULT_DATABASE = ""
DEFAULT_ENCRYPTED = False
DEFAULT_GRAPHQL_URL = ""
DEFAULT_GRAPHQL_TOKEN = ""

# Fixed visualization operations and bounds. Callers can select an operation
# and variables, but can never submit GraphQL or Cypher text.
GRAPH_OPERATION_NAMES = (
    "initial_graph",
    "expand_node",
    "search_graph",
    "graph_element",
    "graph_health",
)
GRAPH_INITIAL_NODE_LIMIT = 500
GRAPH_INITIAL_EDGE_LIMIT = 1000
GRAPH_EXPAND_NODE_LIMIT = 100
GRAPH_EXPAND_EDGE_LIMIT = 250
GRAPH_EXPAND_NODE_MAX = 250
GRAPH_EXPAND_EDGE_MAX = 500
GRAPH_SEARCH_LIMIT = 50
GRAPH_SEARCH_MAX = 100
GRAPH_PROPERTY_LIMIT = 25
GRAPH_PROPERTY_VALUE_MAX_LENGTH = 2048
GRAPH_REVISION_BUFFER_SIZE = 1000
GRAPH_UPDATE_DEBOUNCE_SECONDS = 0.25
GRAPH_REQUEST_TIMEOUT_SECONDS = 10.0

# Options-flow keys
CONF_AUTO_CLASSIFY = "auto_classify"
DEFAULT_AUTO_CLASSIFY = True
CONF_LOW_BATTERY_THRESHOLD = "low_battery_threshold"
CONF_ACTIVE_POWER_THRESHOLD = "active_power_threshold"
CONF_MAX_MEASUREMENT_AGE_HOURS = "max_measurement_age_hours"
CONF_RELATIONSHIP_RESULT_LIMIT = "relationship_result_limit"
DEFAULT_LOW_BATTERY_THRESHOLD = 20.0
DEFAULT_ACTIVE_POWER_THRESHOLD = 1.0
DEFAULT_MAX_MEASUREMENT_AGE_HOURS = 24.0
DEFAULT_RELATIONSHIP_RESULT_LIMIT = 50
MAX_RELATIONSHIP_RESULT_LIMIT = 1000

# Ontology schema version (Constitution Principle VI). Bump whenever labels,
# relationship types, required properties, or graph semantics change.
SCHEMA_VERSION = "3.0.0"
SCHEMA_PREVIOUS_VERSION = "2.0.0"
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

# Home relationship read and administrator service names.
SERVICE_LOW_BATTERY_AREAS = "low_battery_areas"
SERVICE_ACTIVE_CONSUMERS = "active_consumers"
SERVICE_CREATE_SUPPLY_ASSOCIATION = "create_supply_association"
SERVICE_LIST_SUPPLY_ASSOCIATIONS = "list_supply_associations"
SERVICE_DELETE_SUPPLY_ASSOCIATION = "delete_supply_association"
SERVICE_SET_ENERGY_ROLE = "set_energy_role"
SERVICE_DELETE_ENERGY_ROLE = "delete_energy_role"
SERVICE_EXPORT_USER_KNOWLEDGE = "export_user_knowledge"
SERVICE_IMPORT_USER_KNOWLEDGE = "import_user_knowledge"
SERVICE_SUPPLIED_TARGETS = "supplied_targets"

ATTR_THRESHOLD_PERCENTAGE = "threshold_percentage"
ATTR_THRESHOLD_WATTS = "threshold_watts"
ATTR_MAX_AGE_HOURS = "max_age_hours"
ATTR_CYLINDER = "cylinder"
ATTR_TARGET = "target"
ATTR_TARGET_TYPE = "target_type"
ATTR_ASSOCIATION_ID = "association_id"
ATTR_ROLE = "role"

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
USER_KNOWLEDGE_EXPORT_VERSION = 2

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
FINDING_UNRESOLVED_SUPPLY_SOURCE = "unresolved_supply_source"
FINDING_UNRESOLVED_SUPPLY_TARGET = "unresolved_supply_target"
FINDING_UNRESOLVED_ENERGY_ROLE_ENTITY = "unresolved_energy_role_entity"

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
    FINDING_UNRESOLVED_SUPPLY_SOURCE,
    FINDING_UNRESOLVED_SUPPLY_TARGET,
    FINDING_UNRESOLVED_ENERGY_ROLE_ENTITY,
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
WS_TYPE_GRAPH_SNAPSHOT = "ontology/graph_snapshot"
WS_TYPE_GRAPH_SEARCH = "ontology/graph_search"
WS_TYPE_GRAPH_DETAIL = "ontology/graph_detail"
WS_TYPE_GRAPH_EXPAND = "ontology/graph_expand"
WS_TYPE_GRAPH_SUBSCRIBE = "ontology/graph_subscribe"
WS_TYPE_LAB_STATUS = "ontology/lab_status"
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
LABEL_SUPPLY_ASSOCIATION = "SupplyAssociation"
LABEL_ENERGY_ROLE_ASSIGNMENT = "EnergyRoleAssignment"

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
REL_SUPPLY_SOURCE = "SUPPLY_SOURCE"
REL_SUPPLIES = "SUPPLIES"
REL_ASSIGNS_ROLE_TO = "ASSIGNS_ROLE_TO"

# Normalized current-measurement fields and values.
MEASUREMENT_KIND = "measurement_kind"
MEASUREMENT_STATUS = "measurement_status"
MEASUREMENT_BATTERY_PERCENTAGE = "battery_percentage"
MEASUREMENT_POWER_WATTS = "power_watts"
MEASUREMENT_LAST_UPDATED = "measurement_last_updated"
MEASUREMENT_LAST_UPDATED_EPOCH = "measurement_last_updated_epoch"

MEASUREMENT_KIND_BATTERY = "battery"
MEASUREMENT_KIND_POWER = "power"
MEASUREMENT_STATUS_AVAILABLE = "available"
MEASUREMENT_STATUS_UNAVAILABLE = "unavailable"
MEASUREMENT_STATUS_INVALID_VALUE = "invalid_value"
MEASUREMENT_STATUS_UNSUPPORTED_UNIT = "unsupported_unit"
MEASUREMENT_STATUSES = (
    MEASUREMENT_STATUS_AVAILABLE,
    MEASUREMENT_STATUS_UNAVAILABLE,
    MEASUREMENT_STATUS_INVALID_VALUE,
    MEASUREMENT_STATUS_UNSUPPORTED_UNIT,
)

ENERGY_ROLE_CONSUMER = "consumer"
ENERGY_ROLE_PRODUCER = "producer"
ENERGY_ROLE_STORAGE = "storage"
ENERGY_ROLE_GRID_IMPORT = "grid_import"
ENERGY_ROLE_GRID_EXPORT = "grid_export"
ENERGY_ROLES = (
    ENERGY_ROLE_CONSUMER,
    ENERGY_ROLE_PRODUCER,
    ENERGY_ROLE_STORAGE,
    ENERGY_ROLE_GRID_IMPORT,
    ENERGY_ROLE_GRID_EXPORT,
)

SUPPLY_TARGET_DEVICE = "device"
SUPPLY_TARGET_ENTITY = "entity"
SUPPLY_TARGET_TYPES = (SUPPLY_TARGET_DEVICE, SUPPLY_TARGET_ENTITY)

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
RESULT_TYPE_LOW_BATTERY_AREAS = "low_battery_areas"
RESULT_TYPE_ACTIVE_CONSUMERS = "active_consumers"
RESULT_TYPE_SUPPLIED_TARGETS = "supplied_targets"

OUTCOME_OK = "ok"
OUTCOME_EMPTY = "empty"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_AMBIGUOUS = "ambiguous"
OUTCOME_DEGRADED = "degraded"
TOOL_RESULT_OUTCOMES = (
    OUTCOME_OK,
    OUTCOME_EMPTY,
    OUTCOME_NOT_FOUND,
    OUTCOME_AMBIGUOUS,
    OUTCOME_DEGRADED,
)

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
    "low_battery_areas",
    "active_consumers",
    "supplied_targets",
)

# Assist intent identifiers for relationship questions.
INTENT_LOW_BATTERY_AREAS = "OntologyLowBatteryAreas"
INTENT_ACTIVE_CONSUMERS = "OntologyActiveConsumers"
INTENT_AUTOMATION_DEPENDENCIES = "OntologyAutomationDependencies"
INTENT_SUPPLIED_TARGETS = "OntologySuppliedTargets"
INTENT_DEVICE_CONTEXT = "OntologyDeviceContext"

# Agent-audit event names (data-model.md §5)
AUDIT_EVENT_ASSIST_QUERY = "assist_query"
AUDIT_EVENT_MCP_TOOL_CALL = "mcp_tool_call"
AUDIT_EVENT_MCP_WRITE_REJECTED = "mcp_write_rejected"
AUDIT_EVENT_MCP_AUTH_REJECTED = "mcp_auth_rejected"
AUDIT_EVENT_IMPACT_ANALYSIS = "impact_analysis"
AUDIT_EVENT_CONTEXT_EXPORT = "context_export"

# button.py control entity for MCP token regeneration (research.md §3)
BUTTON_KEY_REGENERATE_MCP_TOKEN = "regenerate_mcp_token"


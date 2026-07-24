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


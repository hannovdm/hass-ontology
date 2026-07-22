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

# Ontology schema version (Constitution Principle VI). Bump whenever labels,
# relationship types, required properties, or graph semantics change.
SCHEMA_VERSION = "1.0.0"
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

# Domains treated as "scriptable" entities that reference other entities
AUTOMATION_DOMAIN = "automation"
SCENE_DOMAIN = "scene"
SCRIPT_DOMAIN = "script"


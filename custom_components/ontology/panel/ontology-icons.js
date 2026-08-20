const SAFE_ICON = /^mdi:[a-z0-9-]+$/;

const TYPE_FALLBACKS = Object.freeze({
  AREA: "mdi:floor-plan",
  DEVICE: "mdi:devices",
  ENTITY: "mdi:home-assistant",
  AUTOMATION: "mdi:robot",
  DASHBOARD: "mdi:view-dashboard-outline",
  SEMANTIC_TYPE: "mdi:tag-outline",
  VALIDATION_FINDING: "mdi:alert-circle-outline",
  OTHER: "mdi:help-circle-outline",
});

function safeIcon(value) {
  return typeof value === "string" && SAFE_ICON.test(value) ? value : null;
}

export function fallbackIconForType(type) {
  return TYPE_FALLBACKS[String(type || "OTHER").toUpperCase()] || TYPE_FALLBACKS.OTHER;
}

export function resolveOntologyIcon(node, hass) {
  const propertyIcon = (node.properties || []).find(({ name }) => name === "icon")?.value;
  const stateIcon = hass?.states?.[node.haId]?.attributes?.icon;
  return safeIcon(node.icon) || safeIcon(propertyIcon) || safeIcon(stateIcon) || fallbackIconForType(node.type);
}
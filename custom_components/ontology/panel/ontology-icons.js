const SAFE_ICON = /^mdi:[a-z0-9-]+$/;

// Icons per HA entity domain, used when no explicit icon is set
const DOMAIN_ICONS = Object.freeze({
  alarm_control_panel: "mdi:alarm-light",
  automation: "mdi:robot",
  binary_sensor: "mdi:circle-small",
  button: "mdi:gesture-tap-button",
  calendar: "mdi:calendar",
  camera: "mdi:camera",
  climate: "mdi:thermostat",
  counter: "mdi:counter",
  cover: "mdi:window-shutter",
  device_tracker: "mdi:map-marker",
  event: "mdi:calendar-check",
  fan: "mdi:fan",
  geo_location: "mdi:map-marker",
  group: "mdi:group",
  humidifier: "mdi:air-humidifier",
  image_processing: "mdi:image-filter-frames",
  input_boolean: "mdi:toggle-switch-variant-off",
  input_datetime: "mdi:calendar-clock",
  input_number: "mdi:ray-vertex",
  input_select: "mdi:format-list-bulleted",
  input_text: "mdi:form-textbox",
  lawn_mower: "mdi:robot-mower",
  light: "mdi:lightbulb",
  lock: "mdi:lock",
  media_player: "mdi:cast-connected",
  notify: "mdi:bell",
  number: "mdi:ray-vertex",
  person: "mdi:account",
  plant: "mdi:flower",
  proximity: "mdi:near-me",
  remote: "mdi:remote",
  scene: "mdi:palette",
  script: "mdi:script-text-outline",
  select: "mdi:format-list-bulleted",
  sensor: "mdi:eye",
  siren: "mdi:alarm-bell",
  sun: "mdi:white-balance-sunny",
  switch: "mdi:toggle-switch-variant",
  tag: "mdi:tag",
  timer: "mdi:timer-outline",
  todo: "mdi:clipboard-check-outline",
  update: "mdi:package-up",
  vacuum: "mdi:robot-vacuum",
  valve: "mdi:valve",
  water_heater: "mdi:water-boiler",
  weather: "mdi:weather-partly-cloudy",
  zone: "mdi:map-marker-radius",
});

const TYPE_FALLBACKS = Object.freeze({
  AREA: "mdi:sofa",
  HOME: "mdi:home-assistant",
  FLOOR: "mdi:layers-outline",
  DEVICE: "mdi:devices",
  ENTITY: "mdi:home-assistant",
  AUTOMATION: "mdi:robot",
  SCENE: "mdi:palette",
  SCRIPT: "mdi:script-text-outline",
  DASHBOARD: "mdi:view-dashboard-outline",
  DASHBOARD_CARD: "mdi:card-outline",
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
  // 1. Explicit icon from graph node data
  if (safeIcon(node.icon)) return node.icon;

  // 2. Icon from stored node properties
  const propertyIcon = (node.properties || []).find(({ name }) => name === "icon")?.value;
  if (safeIcon(propertyIcon)) return propertyIcon;

  // 3. HA state attribute icon (covers entities with custom icons set in UI)
  const stateIcon = hass?.states?.[node.haId]?.attributes?.icon;
  if (safeIcon(stateIcon)) return stateIcon;

  // 4. HA area registry icon
  if (node.type === "AREA" && hass?.areas?.[node.haId]?.icon) {
    const areaIcon = safeIcon(hass.areas[node.haId].icon);
    if (areaIcon) return areaIcon;
  }

  // 5. Entity: derive icon from domain
  if (node.type === "ENTITY" && typeof node.haId === "string" && node.haId.includes(".")) {
    const domain = node.haId.split(".")[0];
    const domainIcon = DOMAIN_ICONS[domain];
    if (domainIcon) return domainIcon;
  }

  return fallbackIconForType(node.type);
}
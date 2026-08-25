import cytoscape from "./vendor/cytoscape.esm.min.js";
import { resolveOntologyIcon } from "./ontology-icons.js?v=4.0.0b11";

export const UNASSIGNED_ID = "presentation:unassigned";
export const SYNTHETIC_HOME_ID = "presentation:home";

// MDI SVG path strings used as inline node icons in the Cytoscape canvas
const _MDI_HOME = "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z";
const _MDI_SOFA = "M21,9V7A2,2 0 0,0 19,5H5C3.89,5 3,5.89 3,7V9A2,2 0 0,0 1,11V17H3V19H5V17H19V19H21V17H23V11A2,2 0 0,0 21,9M5,7H19V9H5V7M23,15H1V11A1,1 0 0,1 2,10H22A1,1 0 0,1 23,11V15Z";

// Base64-encoded SVG data URI — more reliable than URL-encoded across browsers
function _svgUri(path, color) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="${color}" d="${path}"/></svg>`;
  return `data:image/svg+xml;base64,${btoa(svg)}`;
}

function relationshipLabel(type, directed) {
  const words = String(type || "related to").replaceAll("_", " ").toLowerCase();
  return directed ? `${words} →` : words;
}

function graphElements(snapshot, hass, includePresentationGroups = true) {
  const nodesById = new Map();
  for (const node of snapshot.nodes || []) {
    if (node?.id && !nodesById.has(node.id)) nodesById.set(node.id, node);
  }
  const snapshotNodes = [...nodesById.values()];
  const relationships = [];
  const elementIds = new Set(nodesById.keys());
  for (const relationship of snapshot.relationships || []) {
    if (
      !relationship?.id
      || !nodesById.has(relationship.source)
      || !nodesById.has(relationship.target)
      || elementIds.has(relationship.id)
    ) continue;
    elementIds.add(relationship.id);
    relationships.push(relationship);
  }
  const assignedDevices = new Set();
  for (const relationship of relationships) {
    const source = nodesById.get(relationship.source);
    const target = nodesById.get(relationship.target);
    if (source?.type === "AREA" && target?.type === "DEVICE") assignedDevices.add(target.id);
    if (target?.type === "AREA" && source?.type === "DEVICE") assignedDevices.add(source.id);
  }
  const unassignedIds = includePresentationGroups
    ? new Set(snapshotNodes.filter((node) => node.type === "DEVICE" && !assignedDevices.has(node.id)).map((node) => node.id))
    : new Set();
  const nodes = snapshotNodes.map((node) => ({
    data: {
      ...node,
      icon: resolveOntologyIcon(node, hass),
      parent: unassignedIds.has(node.id) ? UNASSIGNED_ID : undefined,
    },
    classes: [
      String(node.type || "other").toLowerCase().replaceAll("_", "-"),
      node.unavailable ? "unavailable" : "",
      node.type === "VALIDATION_FINDING" ? "validation-finding" : "",
      node.findingSeverity ? `severity-${String(node.findingSeverity).toLowerCase()}` : "",
    ].filter(Boolean).join(" "),
  }));
  if (unassignedIds.size) {
    nodes.push({
      data: { id: UNASSIGNED_ID, haId: UNASSIGNED_ID, type: "PRESENTATION_GROUP", label: "Unassigned", icon: "mdi:folder-question-outline", presentationOnly: true },
      classes: "presentation-group",
    });
  }
  const edges = relationships.map((relationship) => ({
    data: { ...relationship, label: relationshipLabel(relationship.type, relationship.directed) },
    classes: relationship.directed ? "directed" : "",
  }));

  // Add synthetic HOME node + edges when the snapshot has no HOME node but has areas.
  // This ensures the star layout always has a central hub regardless of backend.
  const hasHomeNode = snapshotNodes.some((n) => n.type === "HOME");
  const areaNodes = snapshotNodes.filter((n) => n.type === "AREA");
  if (includePresentationGroups && !hasHomeNode && areaNodes.length > 0) {
    const homeName = hass?.config?.location_name || "Home";
    nodes.push({
      data: { id: SYNTHETIC_HOME_ID, haId: SYNTHETIC_HOME_ID, type: "HOME", label: homeName, icon: "mdi:home", synthetic: true },
      classes: "home synthetic",
    });
    for (const area of areaNodes) {
      const edgeId = `${SYNTHETIC_HOME_ID}\u2192${area.id}`;
      if (!elementIds.has(edgeId)) {
        elementIds.add(edgeId);
        edges.push({
          data: { id: edgeId, source: SYNTHETIC_HOME_ID, target: area.id, type: "HAS_AREA", label: "", directed: false },
          classes: "home-edge synthetic",
        });
      }
    }
  }

  return [...nodes, ...edges];
}

function elementClasses(element) {
  if (element.source && element.target) return element.directed ? "directed" : "";
  return [
    String(element.type || "other").toLowerCase().replaceAll("_", "-"),
    element.unavailable ? "unavailable" : "",
    element.type === "VALIDATION_FINDING" ? "validation-finding" : "",
    element.findingSeverity ? `severity-${String(element.findingSeverity).toLowerCase()}` : "",
  ].filter(Boolean).join(" ");
}

class OntologyGraph extends HTMLElement {
  connectedCallback() {
    if (this._container) return;
    Object.assign(this.style, { display: "block", width: "100%", height: "100%" });
    this._container = document.createElement("div");
    Object.assign(this._container.style, { width: "100%", height: "100%" });
    this.append(this._container);
  }

  setSnapshot(snapshot, hass) {
    this.connectedCallback();
    const viewport = this.cy ? { pan: this.cy.pan(), zoom: this.cy.zoom() } : null;
    const selectedId = this.cy?.$(":selected").first().id() || null;
    this.cy?.destroy();
    this.cy = cytoscape({
      container: this._container,
      elements: graphElements(snapshot, hass),
      layout: {
        name: "concentric",
        concentric: (node) => {
          switch (node.data("type")) {
            case "HOME": return 2;
            case "FLOOR": case "AREA": return 1;
            default: return 1;
          }
        },
        levelWidth: () => 1,
        minNodeSpacing: 60,
        padding: 48,
        startAngle: 3 * Math.PI / 2,
      },
      minZoom: 0.2,
      maxZoom: 3,
      style: [
        { selector: "node", style: { "background-color": "#e8f3f5", "border-color": "#236779", "border-width": 2, color: "#14252b", content: "data(label)", "font-size": 11, height: 46, shape: "round-rectangle", "text-background-color": "#fff", "text-background-opacity": 0.9, "text-background-padding": 3, "text-margin-y": 34, width: 56 } },
        { selector: "node.home", style: { "background-color": "#e3f2fd", "border-color": "#1565c0", "border-width": 3, shape: "ellipse", width: 72, height: 72, "font-size": 13, "font-weight": 600, "text-margin-y": 42, "background-image": _svgUri(_MDI_HOME, "#1565c0"), "background-fit": "contain", "background-clip": "node", "background-width": "55%", "background-height": "55%" } },
        { selector: "node.area", style: { "background-color": "#dcebdc", "border-color": "#3b6f47", shape: "ellipse", width: 58, height: 58, "text-margin-y": 34, "background-image": _svgUri(_MDI_SOFA, "#3b6f47"), "background-fit": "contain", "background-clip": "node", "background-width": "52%", "background-height": "52%" } },
        { selector: "node.device", style: { "background-color": "#dcecf4", "border-color": "#35697e" } },
        { selector: "node.entity", style: { "background-color": "#f0eff8", "border-color": "#5c5fa6" } },
        { selector: "node.unavailable", style: { "border-style": "dashed", "border-width": 4, opacity: 0.65 } },
        { selector: "node.validation-finding", style: { "background-color": "#fff1c7", "border-color": "#9b6500", "border-width": 4, shape: "diamond" } },
        { selector: "node.severity-error, node.severity-critical", style: { "background-color": "#f9d7d5", "border-color": "#9e2f2a" } },
        { selector: "node.presentation-group", style: { "background-color": "#f7f8f8", "border-color": "#68777d", "border-style": "dotted", "text-valign": "top", padding: 18 } },
        { selector: "node:selected", style: { "border-color": "#111", "border-width": 5, "overlay-opacity": 0.08 } },
        { selector: "edge", style: { "curve-style": "bezier", "font-size": 9, label: "data(label)", "line-color": "#718087", "target-arrow-color": "#718087", "target-arrow-shape": "none", "text-background-color": "#fff", "text-background-opacity": 0.85, "text-background-padding": 2, width: 2 } },
        { selector: "edge.home-edge", style: { "line-color": "#90caf9", "line-style": "solid", width: 1, label: "", opacity: 0.6 } },
        { selector: "edge:loop", style: { "curve-style": "bezier", "loop-direction": "45deg", "loop-sweep": "70deg" } },
        { selector: "edge.directed", style: { "target-arrow-shape": "triangle" } },
      ],
    });
    if (viewport) {
      this.cy.zoom(viewport.zoom);
      this.cy.pan(viewport.pan);
      if (selectedId) this.cy.getElementById(selectedId).select();
    } else {
      this._fitToTop();
    }
    this._initialViewport = { pan: this.cy.pan(), zoom: this.cy.zoom() };
    this.cy.on("select unselect", "node, edge", (event) => {
      if (this._suppressSelectionEvents) return;
      let selectedId = this.cy.$(":selected").first().id() || null;
      if (event.type === "select") {
        this._suppressSelectionEvents = true;
        try {
          this.cy.$(":selected").not(event.target).unselect();
        } finally {
          this._suppressSelectionEvents = false;
        }
        selectedId = event.target.id();
      }
      this.dispatchEvent(new CustomEvent("graph-selection-changed", {
        detail: { id: selectedId },
        bubbles: true,
      }));
    });
  }

  applySlice(slice, hass, centerId = null) {
    if (!this.cy) {
      this.setSnapshot(slice, hass);
      return;
    }
    const selectedId = this.cy.$(":selected").first().id() || null;
    // Only preserve viewport when not centering on a specific element
    const savedViewport = centerId ? null : { pan: this.cy.pan(), zoom: this.cy.zoom() };
    const center = centerId ? this.cy.getElementById(centerId) : null;
    const centerPosition = center?.nonempty() ? center.position() : { x: 0, y: 0 };
    const incoming = graphElements(slice, hass, false);
    const newNodes = [];

    this._suppressSelectionEvents = true;
    try {
      this.cy.batch(() => {
        for (const element of incoming) {
          const existing = this.cy.getElementById(element.data.id);
          if (existing.nonempty()) {
            existing.data(element.data);
            existing.classes(element.classes || elementClasses(element.data));
            continue;
          }
          const added = this.cy.add(element);
          if (added.isNode()) newNodes.push(added);
        }
      });

      const selected = selectedId ? this.cy.getElementById(selectedId) : null;
      if (selected?.nonempty() && !selected.selected()) selected.select();
    } finally {
      this._suppressSelectionEvents = false;
    }

    newNodes.forEach((node, index) => {
      const angle = (2 * Math.PI * index) / Math.max(newNodes.length, 1);
      node.position({
        x: centerPosition.x + Math.cos(angle) * 120,
        y: centerPosition.y + Math.sin(angle) * 120,
      });
    });

    if (savedViewport) {
      this.cy.zoom(savedViewport.zoom);
      this.cy.pan(savedViewport.pan);
    } else if (center?.nonempty()) {
      // Smoothly center the view on the area that was just expanded
      const zoom = Math.max(this.cy.zoom(), 0.9);
      this.cy.animate({ center: { eles: center }, zoom }, { duration: 280 });
    }
  }

  removeElements(elementIds) {
    if (!this.cy) return;
    const viewport = { pan: this.cy.pan(), zoom: this.cy.zoom() };
    this.cy.batch(() => {
      for (const elementId of new Set(elementIds || [])) this.cy.getElementById(elementId).remove();
    });
    this.cy.zoom(viewport.zoom);
    this.cy.pan(viewport.pan);
  }

  updateElements(elements, hass) {
    this.applySlice({
      nodes: (elements || []).filter((element) => !element.source),
      relationships: (elements || []).filter((element) => element.source),
    }, hass);
  }

  setFilters(hiddenNodeTypes = new Set(), hiddenRelationshipTypes = new Set()) {
    if (!this.cy) return;
    this.cy.batch(() => {
      this.cy.nodes().forEach((node) => {
        const visible = node.data("presentationOnly") || !hiddenNodeTypes.has(node.data("type"));
        node.style("display", visible ? "element" : "none");
      });
      this.cy.edges().forEach((edge) => {
        const endpointsVisible = edge.source().visible() && edge.target().visible();
        const typeVisible = !hiddenRelationshipTypes.has(edge.data("type"));
        edge.style("display", endpointsVisible && typeVisible ? "element" : "none");
      });
    });
  }

  zoomBy(factor) {
    if (!this.cy) return;
    this.cy.zoom({ level: Math.min(3, Math.max(0.2, this.cy.zoom() * factor)), renderedPosition: { x: this.clientWidth / 2, y: this.clientHeight / 2 } });
  }

  fit() {
    this._fitToTop();
  }

  resetView() {
    if (!this.cy) return;
    this._fitToTop();
    this._initialViewport = { pan: this.cy.pan(), zoom: this.cy.zoom() };
  }

  _fitToTop() {
    if (!this.cy) return;
    const visible = this.cy.$(":visible");
    this.cy.fit(visible, 36);
    const bounds = visible.renderedBoundingBox({ includeLabels: true });
    this.cy.panBy({ x: 0, y: 36 - bounds.y1 });
  }

  selectNode(nodeId) {
    if (!this.cy) return;
    this.cy.nodes().unselect();
    const node = this.cy.getElementById(nodeId);
    if (node.nonempty()) {
      node.select();
      this.cy.center(node);
    }
  }
}

customElements.define("ontology-graph", OntologyGraph);
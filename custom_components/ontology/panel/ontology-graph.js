import cytoscape from "./vendor/cytoscape.esm.min.js";
import { resolveOntologyIcon } from "./ontology-icons.js";

export const UNASSIGNED_ID = "presentation:unassigned";

function relationshipLabel(type, directed) {
  const words = String(type || "related to").replaceAll("_", " ").toLowerCase();
  return directed ? `${words} →` : words;
}

function graphElements(snapshot, hass) {
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
  const unassignedIds = new Set(
    snapshotNodes.filter((node) => node.type === "DEVICE" && !assignedDevices.has(node.id)).map((node) => node.id),
  );
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
    this.cy?.destroy();
    this.cy = cytoscape({
      container: this._container,
      elements: graphElements(snapshot, hass),
      layout: { name: "breadthfirst", directed: true, padding: 36, spacingFactor: 1.25 },
      minZoom: 0.2,
      maxZoom: 3,
      style: [
        { selector: "node", style: { "background-color": "#e8f3f5", "border-color": "#236779", "border-width": 2, color: "#14252b", content: "data(label)", "font-size": 11, height: 42, shape: "round-rectangle", "text-background-color": "#fff", "text-background-opacity": 0.9, "text-background-padding": 3, "text-margin-y": 32, width: 52 } },
        { selector: "node.area", style: { "background-color": "#dcebdc", "border-color": "#3b6f47", shape: "hexagon" } },
        { selector: "node.device", style: { "background-color": "#dcecf4", "border-color": "#35697e" } },
        { selector: "node.unavailable", style: { "border-style": "dashed", "border-width": 4, opacity: 0.65 } },
        { selector: "node.validation-finding", style: { "background-color": "#fff1c7", "border-color": "#9b6500", "border-width": 4, shape: "diamond" } },
        { selector: "node.severity-error, node.severity-critical", style: { "background-color": "#f9d7d5", "border-color": "#9e2f2a" } },
        { selector: "node.presentation-group", style: { "background-color": "#f7f8f8", "border-color": "#68777d", "border-style": "dotted", "text-valign": "top", padding: 18 } },
        { selector: "node:selected", style: { "border-color": "#111", "border-width": 5, "overlay-opacity": 0.08 } },
        { selector: "edge", style: { "curve-style": "bezier", "font-size": 9, label: "data(label)", "line-color": "#718087", "target-arrow-color": "#718087", "target-arrow-shape": "none", "text-background-color": "#fff", "text-background-opacity": 0.85, "text-background-padding": 2, width: 2 } },
        { selector: "edge:loop", style: { "curve-style": "bezier", "loop-direction": "45deg", "loop-sweep": "70deg" } },
        { selector: "edge.directed", style: { "target-arrow-shape": "triangle" } },
      ],
    });
    this._initialViewport = { pan: this.cy.pan(), zoom: this.cy.zoom() };
    this.cy.on("select unselect", "node, edge", () => {
      this.dispatchEvent(new CustomEvent("graph-selection-changed", {
        detail: { id: this.cy.$(":selected").first().id() || null },
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
    const viewport = { pan: this.cy.pan(), zoom: this.cy.zoom() };
    const center = centerId ? this.cy.getElementById(centerId) : null;
    const centerPosition = center?.nonempty() ? center.position() : { x: 0, y: 0 };
    const incoming = graphElements(slice, hass).filter(({ data }) => data.id !== UNASSIGNED_ID);
    const newNodes = [];

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

    newNodes.forEach((node, index) => {
      const angle = (2 * Math.PI * index) / Math.max(newNodes.length, 1);
      node.position({
        x: centerPosition.x + Math.cos(angle) * 120,
        y: centerPosition.y + Math.sin(angle) * 120,
      });
    });
    if (selectedId) this.cy.getElementById(selectedId).select();
    this.cy.zoom(viewport.zoom);
    this.cy.pan(viewport.pan);
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
    this.cy?.fit(this.cy.$(":visible"), 36);
  }

  resetView() {
    if (!this.cy) return;
    this.cy.fit(this.cy.$(":visible"), 36);
    this._initialViewport = { pan: this.cy.pan(), zoom: this.cy.zoom() };
  }

  selectNode(nodeId) {
    if (!this.cy) return;
    this.cy.nodes().unselect();
    const node = this.cy.getElementById(nodeId);
    if (node.nonempty()) {
      node.select();
      this.cy.animate({ center: { eles: node }, duration: 150 });
    }
  }
}

customElements.define("ontology-graph", OntologyGraph);
import { resolveOntologyIcon } from "./ontology-icons.js?v=4.0.0b28";

export const UNASSIGNED_ID = "presentation:unassigned";
export const SYNTHETIC_HOME_ID = "presentation:home";

// ─── Visual constants ────────────────────────────────────────────────────────

const NODE_COLORS = Object.freeze({
  HOME: "#1565c0", FLOOR: "#5c5fa6", AREA: "#3b6f47",
  DEVICE: "#35697e", ENTITY: "#68777d", AUTOMATION: "#7e5721",
  SCENE: "#6b4fa0", SCRIPT: "#4a7050", DASHBOARD: "#236779",
  SEMANTIC_TYPE: "#9b6500", VALIDATION_FINDING: "#9e2f2a",
  PRESENTATION_GROUP: "#8899aa",
});

// nodeVal drives sphere volume; radius = ∛(val × nodeRelSize), default nodeRelSize = 4
const NODE_VALS = Object.freeze({
  HOME: 20, FLOOR: 10, AREA: 8, DEVICE: 3, ENTITY: 2,
  AUTOMATION: 3, SCENE: 3, SCRIPT: 3, DASHBOARD: 3,
  VALIDATION_FINDING: 4, PRESENTATION_GROUP: 5,
});

// ─── Vendor library loader ───────────────────────────────────────────────────
// Load a compatible Three.js module first; the 3d-force-graph UMD factory then
// adopts window.THREE so custom objects and the renderer share one instance.

let _libPromise = null;
let _THREE = null;

function _loadLibs() {
  if (_libPromise) return _libPromise;
  _libPromise = import("/ontology_static/vendor/three.module.min.js?v=0.179.1")
    .then((three) => { _THREE = three; window.THREE = three; })
    .then(() => _injectScript("/ontology_static/vendor/3d-force-graph.min.js"));
  return _libPromise;
}

function _injectScript(src) {
  return new Promise((ok, fail) => {
    if (document.head.querySelector(`script[src="${src}"]`)) { ok(); return; }
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => fail(new Error(`Cannot load ${src}`));
    document.head.appendChild(s);
  });
}

// ─── Three.js helpers ────────────────────────────────────────────────────────

function _nodeColor(node) {
  if (node._selected) return "#ffffff";
  if (node.findingSeverity === "CRITICAL" || node.findingSeverity === "ERROR") return "#9e2f2a";
  return NODE_COLORS[node.type] ?? "#718087";
}

// ─── Graph data builder ──────────────────────────────────────────────────────

function _buildData(snapshot, hass, includePresentation = true, knownNodeIds = new Set()) {
  const byId = new Map();
  for (const n of snapshot.nodes ?? []) if (n?.id && !byId.has(n.id)) byId.set(n.id, n);
  const snapshotNodes = [...byId.values()];

  const seen = new Set(byId.keys());
  const rels = [];
  for (const r of snapshot.relationships ?? []) {
    const sourceKnown = byId.has(r.source) || knownNodeIds.has(r.source);
    const targetKnown = byId.has(r.target) || knownNodeIds.has(r.target);
    if (!r?.id || !sourceKnown || !targetKnown || seen.has(r.id)) continue;
    seen.add(r.id); rels.push(r);
  }

  const assigned = new Set();
  for (const r of rels) {
    const s = byId.get(r.source), t = byId.get(r.target);
    if (s?.type === "AREA" && t?.type === "DEVICE") assigned.add(t.id);
    if (t?.type === "AREA" && s?.type === "DEVICE") assigned.add(s.id);
  }

  const unassigned = includePresentation
    ? new Set(snapshotNodes.filter((n) => n.type === "DEVICE" && !assigned.has(n.id)).map((n) => n.id))
    : new Set();

  const areaNodes = snapshotNodes.filter((n) => n.type === "AREA");

  const nodes = snapshotNodes.map((node) => {
    const n = { ...node, icon: resolveOntologyIcon(node, hass) };
    // Pin HOME at origin so areas orbit it during force simulation
    if (node.type === "HOME") { n.fx = 0; n.fy = 0; n.fz = 0; }
    // Seed area positions in a circle to speed up force convergence
    if (node.type === "AREA") {
      const idx = areaNodes.indexOf(node);
      const a = (2 * Math.PI * idx) / Math.max(areaNodes.length, 1);
      n.x = Math.cos(a) * 250; n.y = Math.sin(a) * 250; n.z = 0;
    }
    return n;
  });

  if (unassigned.size) {
    nodes.push({ id: UNASSIGNED_ID, haId: UNASSIGNED_ID, type: "PRESENTATION_GROUP", label: "Unassigned", icon: "mdi:folder-question-outline", presentationOnly: true });
  }

  const links = rels.map((r) => ({ id: r.id, source: r.source, target: r.target, type: r.type, label: r.label, directed: !!r.directed }));

  const hasHome = snapshotNodes.some((n) => n.type === "HOME");
  if (includePresentation && !hasHome && areaNodes.length > 0) {
    nodes.push({ id: SYNTHETIC_HOME_ID, haId: SYNTHETIC_HOME_ID, type: "HOME", label: hass?.config?.location_name || "Home", icon: "mdi:home-assistant", synthetic: true, fx: 0, fy: 0, fz: 0, x: 0, y: 0, z: 0 });
    for (const area of areaNodes) {
      const lid = `${SYNTHETIC_HOME_ID}\u2192${area.id}`;
      if (!seen.has(lid)) { seen.add(lid); links.push({ id: lid, source: SYNTHETIC_HOME_ID, target: area.id, type: "HAS_AREA", directed: false, synthetic: true }); }
    }
  }

  return { nodes, links };
}

// d3-force mutates link.source/target from id strings to node objects after layout
const _normalise = (l) => ({ ...l, source: l.source?.id ?? l.source, target: l.target?.id ?? l.target });

// ─── Custom element ──────────────────────────────────────────────────────────

class OntologyGraph extends HTMLElement {
  constructor() {
    super();
    this._fg = null; this._container = null;
    this._iconLayer = null; this._iconElements = new Map();
    this._nodeLabelElements = new Map(); this._linkLabelElements = new Map();
    this._nodeMap = new Map(); this._linkMap = new Map();
    this._selectedId = null;
    this._hiddenNodeTypes = new Set(); this._hiddenLinkTypes = new Set();
    this._ro = null;
    this._animationFrame = null; this._initialFitTimer = null;
    this._viewInteracted = false; this._lastNodeClick = null;
  }

  // Public query API consumed by ontology-panel.js
  get selectedId() { return this._selectedId; }
  hasNode(id) { return this._nodeMap.has(id); }
  hasNodes() { return this._nodeMap.size > 0; }
  getNodeType(id) { return this._nodeMap.get(id)?.type; }

  connectedCallback() {
    if (this._container) return;
    Object.assign(this.style, { display: "block", width: "100%", height: "100%", position: "relative" });
    this._container = document.createElement("div");
    Object.assign(this._container.style, { width: "100%", height: "100%", overflow: "hidden" });
    this._iconLayer = document.createElement("div");
    Object.assign(this._iconLayer.style, { position: "absolute", inset: "0", overflow: "hidden", pointerEvents: "none", zIndex: "2" });
    this.append(this._container, this._iconLayer);
    _loadLibs().catch(console.error);
  }

  disconnectedCallback() {
    this._ro?.disconnect();
    cancelAnimationFrame(this._animationFrame);
    clearTimeout(this._initialFitTimer);
    if (this._fg) { this._fg.pauseAnimation(); this._fg._destructor?.(); this._fg = null; }
  }

  // Overlay shown while vendor libraries load or when they fail
  _showOverlay(text, isError = false) {
    if (!this._overlay) {
      this._overlay = document.createElement("div");
      Object.assign(this._overlay.style, {
        position: "absolute", inset: "0", display: "flex",
        alignItems: "center", justifyContent: "center", zIndex: "5",
        background: "rgba(255,255,255,0.92)", fontFamily: "sans-serif",
        fontSize: "13px", padding: "20px", textAlign: "center",
      });
      this.append(this._overlay);
    }
    this._overlay.textContent = text;
    this._overlay.style.color = isError ? "#9e2f2a" : "#555";
    this._overlay.style.display = "flex";
  }

  _hideOverlay() { if (this._overlay) this._overlay.style.display = "none"; }

  async setSnapshot(snapshot, hass, includePresentation = true) {
    this.connectedCallback();
    this._showOverlay("Loading 3D visualization…");
    try {
      await _loadLibs();
      if (!window.ForceGraph3D) {
        throw new Error("vendor/3d-force-graph.min.js loaded but ForceGraph3D global is missing — check vendor deployment");
      }
      if (!this._fg) this._init();
      const { nodes, links } = _buildData(snapshot, hass, includePresentation);
      this._nodeMap = new Map(nodes.map((n) => [n.id, n]));
      this._linkMap = new Map(links.map((l) => [l.id, l]));
      this._selectedId = null;
      this._viewInteracted = false;
      this._fg.graphData({ nodes: nodes.slice(), links: links.slice() });
      this._rebuildIconOverlay();
      clearTimeout(this._initialFitTimer);
      this._initialFitTimer = setTimeout(() => {
        if (!this._viewInteracted) this._fg?.zoomToFit(500, 80);
      }, 300);
      this._hideOverlay();
    } catch (err) {
      const msg = err?.message ?? String(err);
      this._showOverlay(`3D graph error: ${msg}`, true);
      console.error("[ontology-graph]", err);
      throw err;
    }
  }

  async setFocus(slice, hass, nodeId) {
    await this.setSnapshot(slice, hass, false);
    this._setSelected(nodeId);
    this.fitNodes((slice.nodes || []).map((node) => node.id), nodeId);
  }

  applySlice(slice, hass, centerId = null) {
    if (!this._fg) return;
    const { nodes: cur, links: curL } = this._fg.graphData();
    const curIds = new Set(cur.map((n) => n.id));
    const { nodes: inc, links: incLinks } = _buildData(slice, hass, false, curIds);
    const curLIds = new Set(curL.map((l) => l.id));

    // Update existing nodes in-place to preserve force-simulation positions
    for (const n of inc) {
      if (!curIds.has(n.id)) continue;
      const ex = cur.find((e) => e.id === n.id);
      if (ex) Object.assign(ex, n);
      this._nodeMap.set(n.id, ex ?? n);
    }

    const add = inc.filter((n) => !curIds.has(n.id));
    const addL = incLinks.filter((l) => !curLIds.has(l.id));

    if (centerId) {
      const c = cur.find((n) => n.id === centerId);
      const cx = c?.x ?? 0, cy = c?.y ?? 0, cz = c?.z ?? 0;
      add.forEach((n, i) => {
        const a = (2 * Math.PI * i) / Math.max(add.length, 1);
        const radius = n.type === "ENTITY" ? 125 : 90;
        n.x = cx + Math.cos(a) * radius;
        n.y = cy + Math.sin(a) * radius;
        n.z = cz + ((i % 3) - 1) * 28;
      });
    }

    add.forEach((n) => this._nodeMap.set(n.id, n));
    addL.forEach((l) => this._linkMap.set(l.id, l));
    if (add.length || addL.length) {
      this._fg.graphData({ nodes: [...cur, ...add], links: [...curL.map(_normalise), ...addL] });
      this._rebuildIconOverlay();
    } else {
      this._fg.refresh();
      this._syncIconPositions();
    }

    if (centerId) setTimeout(() => this._focusNode(centerId), 150);
  }

  fitNodes(nodeIds, centerId = null) {
    if (!this._fg) return;
    const ids = new Set(nodeIds || []);
    if (!ids.size) return;
    this._viewInteracted = true;
    setTimeout(() => {
      this._fg?.zoomToFit(650, 110, (node) => ids.has(node.id));
      if (!centerId) return;
      setTimeout(() => {
        const center = this._nodeMap.get(centerId);
        if (!center || !this._fg) return;
        const target = this._fg.controls().target;
        const camera = this._fg.camera().position;
        const centerPosition = { x: center.x ?? 0, y: center.y ?? 0, z: center.z ?? 0 };
        const distanceScale = 1.65;
        this._fg.cameraPosition(
          {
            x: centerPosition.x + (camera.x - target.x) * distanceScale,
            y: centerPosition.y + (camera.y - target.y) * distanceScale,
            z: centerPosition.z + (camera.z - target.z) * distanceScale,
          },
          centerPosition,
          350,
        );
      }, 700);
    }, 350);
  }

  removeElements(ids) {
    if (!this._fg) return;
    const rm = new Set(ids ?? []);
    rm.forEach((id) => { this._nodeMap.delete(id); this._linkMap.delete(id); });
    const { nodes, links } = this._fg.graphData();
    this._fg.graphData({
      nodes: nodes.filter((n) => !rm.has(n.id)),
      links: links.map(_normalise).filter((l) => !rm.has(l.id) && !rm.has(l.source) && !rm.has(l.target)),
    });
    this._rebuildIconOverlay();
  }

  updateElements(elements, hass) {
    this.applySlice({ nodes: (elements ?? []).filter((e) => !e.source), relationships: (elements ?? []).filter((e) => e.source) }, hass);
  }

  setFilters(hiddenNodeTypes = new Set(), hiddenRelTypes = new Set()) {
    this._hiddenNodeTypes = hiddenNodeTypes; this._hiddenLinkTypes = hiddenRelTypes;
    if (!this._fg) return;
    this._fg
      .nodeVisibility((n) => n.presentationOnly || !this._hiddenNodeTypes.has(n.type))
      .linkVisibility((l) => !this._hiddenLinkTypes.has(l.type));
    this._syncIconPositions();
  }

  zoomBy(factor) {
    if (!this._fg) return;
    this._viewInteracted = true;
    const { x, y, z } = this._fg.camera().position;
    const target = this._fg.controls().target ?? { x: 0, y: 0, z: 0 };
    const s = 1 / factor;
    this._fg.cameraPosition({
      x: target.x + (x - target.x) * s,
      y: target.y + (y - target.y) * s,
      z: target.z + (z - target.z) * s,
    }, target, 200);
  }

  fit() { this._viewInteracted = true; this._fg?.zoomToFit(400, 80); }
  resetView() { this._viewInteracted = true; this._fg?.zoomToFit(400, 80); }

  selectNode(nodeId) {
    if (!this._fg) return;
    this._viewInteracted = true;
    this._setSelected(nodeId);
    if (nodeId) this.dispatchEvent(new CustomEvent("graph-selection-changed", { detail: { id: nodeId }, bubbles: true }));
    this._focusNode(nodeId);
  }

  _focusNode(nodeId) {
    const n = this._nodeMap.get(nodeId ?? "");
    if (!n) return;
    const { x = 0, y = 0, z = 0 } = n;
    const camera = this._fg.camera().position;
    const dx = camera.x - x, dy = camera.y - y, dz = camera.z - z;
    const length = Math.hypot(dx, dy, dz) || 1;
    const distance = n.type === "AREA" ? 130 : 90;
    this._fg.cameraPosition({
      x: x + (dx / length) * distance,
      y: y + (dy / length) * distance,
      z: z + (dz / length) * distance,
    }, { x, y, z }, 600);
  }

  _rebuildIconOverlay() {
    this._iconLayer.replaceChildren();
    this._iconElements.clear();
    this._nodeLabelElements.clear();
    this._linkLabelElements.clear();
    for (const link of this._linkMap.values()) {
      const label = document.createElement("span");
      label.textContent = link.label ?? link.type ?? "relationship";
      Object.assign(label.style, {
        position: "absolute", left: "0", top: "0", display: "none",
        transform: "translate(-50%, -50%)", padding: "2px 5px",
        borderRadius: "3px", background: "rgb(255 255 255 / 88%)",
        color: "#33474f", font: "600 10px/1.2 sans-serif",
        whiteSpace: "nowrap", boxShadow: "0 1px 2px rgb(0 0 0 / 18%)",
      });
      this._iconLayer.append(label);
      this._linkLabelElements.set(link.id, label);
    }
    for (const node of this._nodeMap.values()) {
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", node.icon);
      icon.setAttribute("aria-hidden", "true");
      Object.assign(icon.style, {
        position: "absolute", left: "0", top: "0", color: "white",
        transform: "translate(-50%, -50%)", filter: "drop-shadow(0 1px 2px rgb(0 0 0 / 65%))",
      });
      icon.style.setProperty("--mdc-icon-size", node.type === "HOME" ? "28px" : "20px");
      this._iconLayer.append(icon);
      this._iconElements.set(node.id, icon);
      const label = document.createElement("span");
      label.textContent = node.label ?? node.haId ?? node.id;
      Object.assign(label.style, {
        position: "absolute", left: "0", top: "0", display: "none",
        transform: "translate(-50%, 12px)", maxWidth: "150px",
        padding: "2px 5px", borderRadius: "3px",
        background: "rgb(255 255 255 / 90%)", color: "#14252b",
        font: "600 11px/1.25 sans-serif", textAlign: "center",
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        boxShadow: "0 1px 2px rgb(0 0 0 / 18%)",
      });
      this._iconLayer.append(label);
      this._nodeLabelElements.set(node.id, label);
    }
    this._syncIconPositions();
  }

  _syncIconPositions() {
    if (!this._fg) return;
    for (const link of this._fg.graphData().links) {
      const label = this._linkLabelElements.get(link.id);
      if (!label) continue;
      const source = link.source, target = link.target;
      const sourceVisible = source && !this._hiddenNodeTypes.has(source.type);
      const targetVisible = target && !this._hiddenNodeTypes.has(target.type);
      const visible = sourceVisible && targetVisible && !this._hiddenLinkTypes.has(link.type)
        && [source.x, source.y, source.z, target.x, target.y, target.z].every(Number.isFinite);
      if (!visible) {
        label.style.display = "none";
        continue;
      }
      const { x, y } = this._fg.graph2ScreenCoords(
        (source.x + target.x) / 2,
        (source.y + target.y) / 2,
        (source.z + target.z) / 2,
      );
      label.style.display = "block";
      label.style.left = `${x}px`;
      label.style.top = `${y}px`;
    }
    for (const [id, icon] of this._iconElements) {
      const node = this._nodeMap.get(id);
      const visible = node && (node.presentationOnly || !this._hiddenNodeTypes.has(node.type));
      if (!visible || ![node.x, node.y, node.z].every(Number.isFinite)) {
        icon.style.display = "none";
        this._nodeLabelElements.get(id).style.display = "none";
        continue;
      }
      const { x, y } = this._fg.graph2ScreenCoords(node.x, node.y, node.z);
      const label = this._nodeLabelElements.get(id);
      icon.style.display = "block";
      icon.style.color = node._selected ? "#1565c0" : "white";
      icon.style.left = `${x}px`;
      icon.style.top = `${y}px`;
      label.style.display = "block";
      label.style.left = `${x}px`;
      label.style.top = `${y}px`;
    }
  }

  _setSelected(id) {
    const prev = this._nodeMap.get(this._selectedId ?? "");
    if (prev) delete prev._selected;
    this._selectedId = id;
    const next = this._nodeMap.get(id ?? "");
    if (next) next._selected = true;
    this._fg?.refresh(); // redraws spheres and label sprites with updated _selected flag
  }

  _init() {
    const w = this._container.clientWidth || 800;
    const h = this._container.clientHeight || 600;
    this._fg = window.ForceGraph3D()(this._container)
      .width(w)
      .height(h)
      .backgroundColor("rgba(0,0,0,0)")
      .showNavInfo(false)
      .cooldownTicks(120)
      .nodeId("id")
      .linkSource("source")
      .linkTarget("target")
      .nodeLabel((n) => `${n.label ?? n.id} · ${(n.type ?? "").toLowerCase().replaceAll("_", " ")}`)
      .nodeColor((n) => _nodeColor(n))
      .nodeVal((n) => NODE_VALS[n.type] ?? 2)
      .nodeVisibility((n) => !this._hiddenNodeTypes.has(n.type))
      .linkColor((l) => l.synthetic ? "#6aa7c8" : "#547984")
      .linkWidth((l) => l.synthetic ? 1.2 : (l.directed ? 2.2 : 1.7))
      .linkOpacity(0.9)
      .linkDirectionalArrowLength((l) => l.directed ? 4 : 0)
      .linkDirectionalArrowRelPos(1)
      .linkVisibility((l) => !this._hiddenLinkTypes.has(l.type))
      .onNodeClick((n) => {
        this._viewInteracted = true;
        this._setSelected(n.id);
        this._focusNode(n.id);
        this.dispatchEvent(new CustomEvent("graph-selection-changed", { detail: { id: n.id }, bubbles: true }));
      })
      .onBackgroundClick(() => {
        this._viewInteracted = true;
        this._setSelected(null);
        this.dispatchEvent(new CustomEvent("graph-selection-changed", { detail: { id: null }, bubbles: true }));
      });

    const controls = this._fg.controls();
    controls.enabled = true;
    controls.enableZoom = true;
    controls.enableRotate = true;
    controls.enablePan = true;
    controls.addEventListener("start", () => { this._viewInteracted = true; });
    const syncOverlay = () => {
      this._syncIconPositions();
      this._animationFrame = requestAnimationFrame(syncOverlay);
    };
    this._animationFrame = requestAnimationFrame(syncOverlay);

    try {
      this._fg.d3Force("charge").strength(-340);
      this._fg.d3Force("link").distance((l) => (l.synthetic || l.type === "HAS_AREA") ? 220 : (l.type === "HAS_DEVICE" ? 110 : 80));
    } catch { /* non-d3 build variant */ }

    if (_THREE?.AmbientLight) {
      const dir = new _THREE.DirectionalLight(0xffffff, 1);
      dir.position.set(300, 300, 300);
      this._fg.lights([new _THREE.AmbientLight(0xcccccc, 2), dir]);
    }

    this._ro = new ResizeObserver(() => {
      const { clientWidth: w, clientHeight: h } = this._container;
      if (this._fg && w > 0 && h > 0) this._fg.width(w).height(h);
    });
    this._ro.observe(this._container);
  }
}

if (!customElements.get("ontology-graph")) customElements.define("ontology-graph", OntologyGraph);

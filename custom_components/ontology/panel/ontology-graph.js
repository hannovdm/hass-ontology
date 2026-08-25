import { resolveOntologyIcon } from "./ontology-icons.js?v=4.0.0b14";

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
// three.min.js is loaded first to set window.THREE; the 3d-force-graph UMD
// factory then receives global.THREE, so both share the same Three.js instance.

let _libPromise = null;
let _THREE = null;

function _loadLibs() {
  if (_libPromise) return _libPromise;
  _libPromise = _injectScript("/ontology_static/vendor/three.min.js")
    .then(() => { _THREE = window.THREE; })
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

// Canvas text sprite added below each sphere; returns null if THREE unavailable.
function _labelSprite(text) {
  if (!_THREE?.CanvasTexture) return null;
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 256; canvas.height = 44;
    const ctx = canvas.getContext("2d");
    ctx.font = "bold 20px system-ui, -apple-system, sans-serif";
    const label = text.length > 22 ? `${text.substring(0, 21)}\u2026` : text;
    const bgW = Math.min(ctx.measureText(label).width + 16, 250);
    ctx.fillStyle = "rgba(255,255,255,0.88)";
    if (ctx.roundRect) ctx.roundRect((256 - bgW) / 2, 6, bgW, 32, 6); else ctx.rect((256 - bgW) / 2, 6, bgW, 32);
    ctx.fill();
    ctx.fillStyle = "#14252b";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, 128, 22);
    const mat = new _THREE.SpriteMaterial({ map: new _THREE.CanvasTexture(canvas), depthWrite: false, transparent: true });
    const sp = new _THREE.Sprite(mat);
    sp.scale.set(30, 4.5, 1);
    return sp;
  } catch { return null; }
}

// ─── Graph data builder ──────────────────────────────────────────────────────

function _buildData(snapshot, hass, includePresentation = true) {
  const byId = new Map();
  for (const n of snapshot.nodes ?? []) if (n?.id && !byId.has(n.id)) byId.set(n.id, n);
  const snapshotNodes = [...byId.values()];

  const seen = new Set(byId.keys());
  const rels = [];
  for (const r of snapshot.relationships ?? []) {
    if (!r?.id || !byId.has(r.source) || !byId.has(r.target) || seen.has(r.id)) continue;
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

  const links = rels.map((r) => ({ id: r.id, source: r.source, target: r.target, type: r.type, directed: !!r.directed }));

  const hasHome = snapshotNodes.some((n) => n.type === "HOME");
  if (includePresentation && !hasHome && areaNodes.length > 0) {
    nodes.push({ id: SYNTHETIC_HOME_ID, haId: SYNTHETIC_HOME_ID, type: "HOME", label: hass?.config?.location_name || "Home", icon: "mdi:home", synthetic: true, fx: 0, fy: 0, fz: 0, x: 0, y: 0, z: 0 });
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
    this._nodeMap = new Map(); this._linkMap = new Map();
    this._selectedId = null;
    this._hiddenNodeTypes = new Set(); this._hiddenLinkTypes = new Set();
    this._ro = null;
  }

  // Public query API consumed by ontology-panel.js
  get selectedId() { return this._selectedId; }
  hasNode(id) { return this._nodeMap.has(id); }
  hasNodes() { return this._nodeMap.size > 0; }
  getNodeType(id) { return this._nodeMap.get(id)?.type; }

  connectedCallback() {
    if (this._container) return;
    Object.assign(this.style, { display: "block", width: "100%", height: "100%" });
    this._container = document.createElement("div");
    Object.assign(this._container.style, { width: "100%", height: "100%", overflow: "hidden" });
    this.append(this._container);
    _loadLibs().catch(console.error);
  }

  disconnectedCallback() {
    this._ro?.disconnect();
    if (this._fg) { this._fg.pauseAnimation(); this._fg._destructor?.(); this._fg = null; }
  }

  setSnapshot(snapshot, hass) {
    this.connectedCallback();
    _loadLibs().then(() => {
      if (!this._fg) this._init();
      const { nodes, links } = _buildData(snapshot, hass);
      this._nodeMap = new Map(nodes.map((n) => [n.id, n]));
      this._linkMap = new Map(links.map((l) => [l.id, l]));
      this._selectedId = null;
      this._fg.graphData({ nodes: nodes.slice(), links: links.slice() });
      this._fg.onEngineStop(() => { this._fg.zoomToFit(500, 80); this._fg.onEngineStop(null); });
    }).catch(console.error);
  }

  applySlice(slice, hass, centerId = null) {
    if (!this._fg) return;
    const { nodes: inc, links: incLinks } = _buildData(slice, hass, false);
    const { nodes: cur, links: curL } = this._fg.graphData();
    const curIds = new Set(cur.map((n) => n.id));
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
      add.forEach((n, i) => { const a = (2 * Math.PI * i) / Math.max(add.length, 1); n.x = cx + Math.cos(a) * 60; n.y = cy + Math.sin(a) * 60; n.z = cz; });
    }

    add.forEach((n) => this._nodeMap.set(n.id, n));
    addL.forEach((l) => this._linkMap.set(l.id, l));
    this._fg.graphData({ nodes: [...cur, ...add], links: [...curL.map(_normalise), ...addL] });

    if (centerId) setTimeout(() => this.selectNode(centerId), 150);
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
  }

  zoomBy(factor) {
    if (!this._fg) return;
    const { x, y, z } = this._fg.camera().position;
    const s = 1 / factor;
    this._fg.cameraPosition({ x: x * s, y: y * s, z: z * s }, { x: 0, y: 0, z: 0 }, 200);
  }

  fit() { this._fg?.zoomToFit(400, 80); }
  resetView() { this._fg?.zoomToFit(400, 80); }

  selectNode(nodeId) {
    if (!this._fg) return;
    this._setSelected(nodeId);
    if (nodeId) this.dispatchEvent(new CustomEvent("graph-selection-changed", { detail: { id: nodeId }, bubbles: true }));
    const n = this._nodeMap.get(nodeId ?? "");
    if (!n) return;
    const { x = 0, y = 0, z = 0 } = n;
    this._fg.cameraPosition({ x: x + 100, y: y + 40, z: z + 100 }, { x, y, z }, 600);
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
      .nodeId("id")
      .linkSource("source")
      .linkTarget("target")
      .nodeLabel((n) => `${n.label ?? n.id} · ${(n.type ?? "").toLowerCase().replaceAll("_", " ")}`)
      .nodeColor((n) => _nodeColor(n))
      .nodeVal((n) => NODE_VALS[n.type] ?? 2)
      .nodeVisibility((n) => !this._hiddenNodeTypes.has(n.type))
      .linkColor((l) => l.synthetic ? "#90caf9" : "#9ab4bc")
      .linkWidth((l) => l.directed ? 1.5 : 0.8)
      .linkOpacity(0.6)
      .linkDirectionalArrowLength((l) => l.directed ? 4 : 0)
      .linkDirectionalArrowRelPos(1)
      .linkVisibility((l) => !this._hiddenLinkTypes.has(l.type))
      .nodeThreeObject((n) => {
        const sp = _labelSprite(n.label ?? n.id);
        if (sp) { const r = Math.cbrt((NODE_VALS[n.type] ?? 2) * 4); sp.position.set(0, -(r + 4), 0); }
        return sp;
      })
      .nodeThreeObjectExtend(true)
      .onNodeClick((n) => {
        this._setSelected(n.id);
        this.dispatchEvent(new CustomEvent("graph-selection-changed", { detail: { id: n.id }, bubbles: true }));
      })
      .onBackgroundClick(() => {
        this._setSelected(null);
        this.dispatchEvent(new CustomEvent("graph-selection-changed", { detail: { id: null }, bubbles: true }));
      });

    try {
      this._fg.d3Force("charge").strength(-250);
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

customElements.define("ontology-graph", OntologyGraph);

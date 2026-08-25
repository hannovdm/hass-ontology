import { UNASSIGNED_ID, SYNTHETIC_HOME_ID } from "./ontology-graph.js?v=4.0.0b20";
import { resolveOntologyIcon } from "./ontology-icons.js?v=4.0.0b20";

const STATE_MESSAGES = {
  loading: ["Loading ontology graph", "Preparing areas."],
  empty: ["No ontology graph yet", "Run an ontology resync, then try again."],
  partial: ["Showing partial results", "The 100-area overview limit was reached. Search or select an area to drill down."],
  unavailable: ["Ontology graph unavailable", "Check the integration and Memgraph connection, then retry."],
  error: ["Graph could not be loaded", "Retry the request or check Home Assistant logs."],
};

const SUBSCRIPTION_RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000, 10000];
const SUBSCRIPTION_MAX_RECONNECT_ATTEMPTS = 5;

class OntologyPanel extends HTMLElement {
  connectedCallback() {
    if (!this._rendered) this._renderShell();
    if (this._hass && !this._loadStarted) this._loadSnapshot();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && !this._loadStarted) this._loadSnapshot();
  }

  get graph() {
    return this._graph;
  }

  _renderShell() {
    this._rendered = true;
    this.innerHTML = `
      <style>
        ontology-panel { display: block; min-height: 100vh; background: var(--primary-background-color, #f4f7f8); color: var(--primary-text-color, #172126); }
        .ontology-shell { display: grid; grid-template-rows: auto minmax(420px, 1fr); min-height: 100vh; }
        .ontology-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; padding: 20px 24px 14px; border-bottom: 1px solid var(--divider-color, #d5dddf); background: var(--card-background-color, #fff); }
        .ontology-header h1 { margin: 0; font: 600 24px/1.2 var(--paper-font-headline_-_font-family, sans-serif); }
        .ontology-summary { margin: 5px 0 0; color: var(--secondary-text-color, #56666d); font-size: 14px; }
        .graph-toolbar { display: flex; gap: 6px; }
        .icon-button { display: inline-grid; place-items: center; width: 40px; height: 40px; padding: 0; border: 1px solid var(--divider-color, #cbd5d8); border-radius: 4px; background: var(--card-background-color, #fff); color: var(--primary-text-color, #172126); cursor: pointer; }
        .icon-button:hover, .icon-button:focus-visible { border-color: var(--primary-color, #23728a); outline: 2px solid color-mix(in srgb, var(--primary-color, #23728a) 35%, transparent); outline-offset: 1px; }
        .ontology-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 290px; min-height: 0; }
        .graph-stage { position: relative; min-height: 420px; background: var(--card-background-color, #fff); }
        ontology-graph { position: absolute; inset: 0; }
        .graph-state { position: absolute; z-index: 2; top: 18px; left: 50%; transform: translateX(-50%); max-width: min(460px, calc(100% - 32px)); padding: 10px 14px; border: 1px solid var(--divider-color, #cbd5d8); border-radius: 6px; background: var(--card-background-color, #fff); box-shadow: 0 3px 12px rgb(20 37 43 / 14%); text-align: center; }
        .graph-state[hidden] { display: none; }
        .graph-state strong, .graph-state span { display: block; }
        .graph-state span { margin-top: 3px; color: var(--secondary-text-color, #56666d); font-size: 13px; }
        .graph-state button { margin-top: 9px; min-height: 36px; padding: 0 14px; border: 1px solid var(--primary-color, #23728a); border-radius: 4px; background: transparent; color: var(--primary-color, #155f75); cursor: pointer; }
        .subscription-indicator { position: absolute; z-index: 3; top: 8px; right: 8px; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .subscription-indicator[data-subscription-state="stale"] { background: #fff3cd; color: #856404; border: 1px solid #ffc107; }
        .subscription-indicator[data-subscription-state="reconnecting"] { background: #cce5ff; color: #004085; border: 1px solid #b8daff; }
        [data-subscription-state]:not([data-subscription-state="live"]) { display: block; }
        [data-subscription-state="live"] { display: none; }
        .ontology-sidebar { overflow: auto; padding: 18px; border-left: 1px solid var(--divider-color, #d5dddf); background: var(--secondary-background-color, #f7f9f9); }
        .ontology-sidebar h2 { margin: 0 0 10px; font-size: 15px; }
        .sidebar-section { padding-bottom: 18px; margin-bottom: 18px; border-bottom: 1px solid var(--divider-color, #d5dddf); }
        .search-form { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; }
        .search-form input { min-width: 0; height: 40px; padding: 0 10px; border: 1px solid var(--divider-color, #aebbc0); border-radius: 4px; background: var(--card-background-color, #fff); color: inherit; }
        .command-button { min-height: 40px; padding: 0 12px; border: 1px solid var(--primary-color, #23728a); border-radius: 4px; background: var(--primary-color, #23728a); color: var(--text-primary-color, #fff); cursor: pointer; }
        .command-button.secondary { background: transparent; color: var(--primary-color, #155f75); }
        .search-results { display: grid; gap: 4px; margin: 8px 0 0; padding: 0; list-style: none; }
        .search-results button { width: 100%; padding: 7px 8px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: inherit; text-align: left; cursor: pointer; }
        .search-results button:hover, .search-results button:focus-visible { border-color: var(--primary-color, #23728a); background: var(--card-background-color, #fff); outline: none; }
        .search-results small, .detail-record small { display: block; color: var(--secondary-text-color, #56666d); overflow-wrap: anywhere; }
        .details[hidden] { display: none; }
        .details h2 { overflow-wrap: anywhere; }
        .detail-properties { display: grid; grid-template-columns: minmax(80px, .8fr) minmax(0, 1.2fr); gap: 5px 10px; margin: 10px 0 12px; font-size: 13px; }
        .detail-properties dt { font-weight: 600; }
        .detail-properties dd { margin: 0; overflow-wrap: anywhere; }
        .filter-group { display: grid; gap: 7px; margin-bottom: 12px; }
        .filter-group label { display: flex; align-items: center; gap: 8px; font-size: 13px; }
        .legend { display: grid; grid-template-columns: 12px 1fr; gap: 8px; align-items: center; margin: 0 0 20px; font-size: 13px; }
        .legend-swatch { width: 10px; height: 10px; border: 2px solid #35697e; background: #dcecf4; }
        .legend-swatch.area { border-color: #3b6f47; background: #dcebdc; }
        .legend-swatch.finding { transform: rotate(45deg); border-color: #9b6500; background: #fff1c7; }
        .legend-swatch.unavailable { border-style: dashed; opacity: .65; }
        .node-list { display: grid; gap: 5px; margin: 0; padding: 0; list-style: none; }
        .node-list button { display: grid; grid-template-columns: 24px minmax(0, 1fr); align-items: center; width: 100%; min-height: 42px; padding: 7px 8px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: inherit; text-align: left; cursor: pointer; }
        .node-list button:hover, .node-list button:focus-visible, .node-list button[aria-pressed="true"] { border-color: var(--primary-color, #23728a); background: var(--card-background-color, #fff); outline: none; }
        .node-list small { display: block; color: var(--secondary-text-color, #56666d); }
        @media (max-width: 720px) {
          .ontology-shell { grid-template-rows: auto auto; }
          .ontology-header { align-items: start; padding: 16px; }
          .graph-toolbar { flex-wrap: wrap; justify-content: end; }
          .ontology-workspace { grid-template-columns: 1fr; grid-template-rows: minmax(420px, 62vh) auto; }
          .ontology-sidebar { max-height: none; border-top: 1px solid var(--divider-color, #d5dddf); border-left: 0; }
        }
      </style>
      <main class="ontology-shell">
        <header class="ontology-header">
          <div><h1>Ontology Explorer</h1><p class="ontology-summary" aria-live="polite">Loading graph summary</p></div>
          <div class="graph-toolbar" aria-label="Graph view controls">
            <button class="icon-button" type="button" data-command="zoom-in" aria-label="Zoom in" title="Zoom in"><ha-icon icon="mdi:plus"></ha-icon></button>
            <button class="icon-button" type="button" data-command="zoom-out" aria-label="Zoom out" title="Zoom out"><ha-icon icon="mdi:minus"></ha-icon></button>
            <button class="icon-button" type="button" data-command="fit" aria-label="Fit graph" title="Fit graph"><ha-icon icon="mdi:fit-to-screen-outline"></ha-icon></button>
            <button class="icon-button" type="button" data-command="reset" aria-label="Reset view" title="Reset view"><ha-icon icon="mdi:restore"></ha-icon></button>
          </div>
        </header>
        <div class="ontology-workspace">
          <section class="graph-stage" aria-label="Ontology graph visualization">
            <ontology-graph></ontology-graph>
            <div class="graph-state" data-state="loading" role="status" aria-live="polite"><strong></strong><span></span></div>
            <div class="subscription-indicator" data-subscription-state="live" aria-live="polite" aria-atomic="true"></div>
          </section>
          <aside class="ontology-sidebar">
            <section class="sidebar-section" aria-label="Graph search">
              <h2>Search</h2>
              <form class="search-form" role="search">
                <input type="search" aria-label="Search ontology" maxlength="256" autocomplete="off" />
                <button class="command-button" type="submit">Search</button>
              </form>
              <ul class="search-results" role="listbox" aria-label="Search results"></ul>
            </section>
            <section class="sidebar-section details" aria-live="polite" hidden>
              <h2></h2>
              <small class="detail-record"></small>
              <dl class="detail-properties"></dl>
              <button class="command-button" type="button" data-command="expand">Expand one hop</button>
              <p class="expansion-status" role="status"></p>
            </section>
            <section class="sidebar-section filters" aria-label="Graph filters">
              <h2>Filters</h2>
              <div class="filter-group node-filters"></div>
              <div class="filter-group relationship-filters"></div>
              <button class="command-button secondary" type="button" data-command="clear-filters">Clear filters</button>
            </section>
            <section class="sidebar-section" aria-label="Graph legend" role="region">
              <h2>Legend</h2>
              <div class="legend">
                <span class="legend-swatch area"></span><span>Area</span>
                <span class="legend-swatch"></span><span>Device</span>
                <span class="legend-swatch unavailable"></span><span>Unavailable (dashed)</span>
                <span class="legend-swatch finding"></span><span>Validation finding (diamond)</span>
                <span class="legend-swatch unavailable"></span><span>Presentation group</span>
              </div>
            </section>
            <section aria-labelledby="ontology-node-list-heading">
              <h2 id="ontology-node-list-heading">Graph nodes</h2>
              <ul class="node-list" aria-label="Ontology graph nodes"></ul>
            </section>
            <section class="sidebar-section lab-workspace" hidden aria-label="Advanced graph workspace">
              <h2>Memgraph Lab</h2>
              <p class="lab-status-text" aria-live="polite"></p>
              <a class="command-button lab-launch-link" href="#" target="_blank" rel="noopener noreferrer" hidden>Open Memgraph Lab</a>
              <button class="command-button secondary lab-retry-button" type="button" hidden>Retry</button>
            </section>
          </aside>
        </div>
      </main>
    `;
    this._graph = this.querySelector("ontology-graph");
    this._summary = this.querySelector(".ontology-summary");
    this._state = this.querySelector(".graph-state");
    this._subscriptionIndicator = this.querySelector(".subscription-indicator");
    this._list = this.querySelector(".node-list");
    this._searchForm = this.querySelector(".search-form");
    this._searchResults = this.querySelector(".search-results");
    this._details = this.querySelector(".details");
    this._nodeFilters = this.querySelector(".node-filters");
    this._relationshipFilters = this.querySelector(".relationship-filters");
    this._labWorkspace = this.querySelector(".lab-workspace");
    this._labStatusText = this.querySelector(".lab-status-text");
    this._labLaunchLink = this.querySelector(".lab-launch-link");
    this._labRetryButton = this.querySelector(".lab-retry-button");
    this._hiddenNodeTypes = new Set();
    this._hiddenRelationshipTypes = new Set();
    this._subscriptionUnsubscribe = null;
    this._subscriptionReconnectAttempt = 0;
    this._subscriptionReconnectTimer = null;
    this._state.addEventListener("click", (event) => {
      if (event.target.closest("button")) this._loadSnapshot(true);
    });
    this.addEventListener("graph-selection-changed", ({ detail }) => this._selectionChanged(detail.id));
    this._searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      this._search(this._searchForm.elements[0].value);
    });
    this.querySelector("[data-command='expand']").addEventListener("click", () => this._expandSelection());
    this.querySelector("[data-command='clear-filters']").addEventListener("click", () => this._clearFilters());
    this.querySelector("[data-command='zoom-in']").addEventListener("click", () => this._graph.zoomBy(1.2));
    this.querySelector("[data-command='zoom-out']").addEventListener("click", () => this._graph.zoomBy(1 / 1.2));
    this.querySelector("[data-command='fit']").addEventListener("click", () => this._graph.fit());
    this.querySelector("[data-command='reset']").addEventListener("click", () => this._graph.resetView());
    this._labRetryButton.addEventListener("click", () => this._loadLabStatus());
    this._showState("loading");
  }

  async _loadLabStatus() {
    if (!this._hass?.user?.is_admin) return;
    try {
      const status = await this._hass.callWS({ type: "ontology/lab_status" });
      this._renderLabStatus(status);
    } catch {
      this._renderLabStatus({ available: false, reason: "not_addon_backend" });
    }
  }

  _renderLabStatus(status) {
    if (!this._hass?.user?.is_admin) {
      this._labWorkspace.hidden = true;
      return;
    }
    this._labWorkspace.hidden = false;
    const REASON_MESSAGES = {
      READY: "Available",
      NOT_ADDON_BACKEND: "Requires the Memgraph add-on.",
      not_addon_backend: "Requires the Memgraph add-on.",
      TRANSPORT_UNAVAILABLE: "Add-on GraphQL adapter not reachable.",
      LAB_UNHEALTHY: "Memgraph Lab process is not healthy.",
      ENTERPRISE_REQUIRED: "Requires Memgraph Enterprise edition.",
      READONLY_USER_MISSING: "Read-only Lab user not configured.",
      WRITE_PROBE_SUCCEEDED: "Write authorization probe failed — Lab disabled for safety.",
    };
    if (status.available) {
      this._labStatusText.textContent = "Memgraph Lab is available.";
      this._labLaunchLink.href = status.ingress_path || "#";
      this._labLaunchLink.hidden = false;
      this._labRetryButton.hidden = true;
    } else {
      const reason = REASON_MESSAGES[status.reason] || status.reason || "Unavailable.";
      this._labStatusText.textContent = reason;
      this._labLaunchLink.hidden = true;
      this._labRetryButton.hidden = false;
    }
  }

  async _loadSnapshot(force = false, silent = false) {
    if (this._loadStarted && !force) return;
    this._loadStarted = true;
    if (!silent) this._showState("loading");
    this._unsubscribe();
    try {
      const snapshot = await this._hass.callWS({ type: "ontology/graph_snapshot", limit: 100, cursor: null });
      this._snapshot = snapshot;
      if (!snapshot.nodes?.length) {
        this._summary.textContent = "0 nodes and 0 relationships";
        this._renderNodeList([]);
        this._showState("empty", true);
        return;
      }
      if (silent && this._graph.hasNodes()) {
        // Silent reconcile: refresh base-node data without rebuilding the graph.
        // Preserves device/entity nodes the user expanded by clicking areas.
        this._graph.updateElements(snapshot.nodes, this._hass);
      } else {
        await this._graph.setSnapshot(snapshot, this._hass);
      }
      const homeName = this._hass?.config?.location_name || "Home";
      this._summary.textContent = `${snapshot.nodes.length} nodes · ${snapshot.relationships?.length || 0} relationships · ${homeName}`;
      this._renderNodeList(snapshot.nodes);
      this._renderFilters();
      this._showState(snapshot.truncated ? "partial" : null);
      this._subscriptionReconnectAttempt = 0;
      this._startSubscription(snapshot.revision ?? 0);
      if (!silent) this._loadLabStatus();
    } catch (error) {
      this._showState(error?.code === "gateway_unavailable" ? "unavailable" : "error", true);
    }
  }

  _startSubscription(fromRevision) {
    if (!this._hass?.connection?.subscribeMessage) return;
    // Generation counter: events from a superseded subscription are silently dropped
    const gen = (this._subscriptionGeneration = (this._subscriptionGeneration || 0) + 1);
    this._hass.connection.subscribeMessage(
      (event) => {
        if (gen !== this._subscriptionGeneration) return;
        this._handleLiveEvent(event);
      },
      { type: "ontology/graph_subscribe", from_revision: fromRevision },
    ).then(
      (unsubscribe) => {
        if (gen !== this._subscriptionGeneration) {
          // A newer subscription started before this promise resolved — cancel this one
          try { unsubscribe(); } catch { }
        } else {
          this._subscriptionUnsubscribe = unsubscribe;
        }
      },
      () => {
        if (gen === this._subscriptionGeneration) {
          this._setSubscriptionState("stale");
          this._scheduleReconnect();
        }
      },
    );
    this._setSubscriptionState("live");
  }

  _unsubscribe() {
    // Invalidate all pending subscription promise callbacks before cancelling
    this._subscriptionGeneration = (this._subscriptionGeneration || 0) + 1;
    if (typeof this._subscriptionUnsubscribe === "function") {
      try { this._subscriptionUnsubscribe(); } catch { }
    }
    this._subscriptionUnsubscribe = null;
    if (this._subscriptionReconnectTimer != null) {
      clearTimeout(this._subscriptionReconnectTimer);
      this._subscriptionReconnectTimer = null;
    }
  }

  _setSubscriptionState(state) {
    if (!this._subscriptionIndicator) return;
    this._subscriptionIndicator.dataset.subscriptionState = state;
    const messages = { stale: "Updates paused", reconnecting: "Reconnecting…", live: "" };
    this._subscriptionIndicator.textContent = messages[state] ?? "";
  }

  _scheduleReconnect() {
    const attempt = this._subscriptionReconnectAttempt;
    if (attempt >= SUBSCRIPTION_MAX_RECONNECT_ATTEMPTS) return;
    this._subscriptionReconnectAttempt += 1;
    this._setSubscriptionState("reconnecting");
    const delay = SUBSCRIPTION_RECONNECT_DELAYS_MS[Math.min(attempt, SUBSCRIPTION_RECONNECT_DELAYS_MS.length - 1)];
    this._subscriptionReconnectTimer = setTimeout(async () => {
      this._subscriptionReconnectTimer = null;
      try {
        const snapshot = await this._hass.callWS({ type: "ontology/graph_snapshot", limit: 100, cursor: null });
        this._snapshot = snapshot;
        await this._graph.setSnapshot(snapshot, this._hass);
        this._renderNodeList(snapshot.nodes);
        this._renderFilters();
        this._subscriptionReconnectAttempt = 0;
        this._startSubscription(snapshot.revision ?? 0);
      } catch {
        this._setSubscriptionState("stale");
        this._scheduleReconnect();
      }
    }, delay);
  }

  _handleLiveEvent(event) {
    if (!event || !this._graph) return;
    const { kind, node_ids = [], relationship_ids = [] } = event;
    if (kind === "reconcile") {
      // Reload silently — no flashing loading banner when graph is already visible
      this._loadSnapshot(true, true);
      return;
    }
    if (kind === "remove") {
      const currentSelectedId = this._graph.selectedId;
      this._graph.removeElements([...node_ids, ...relationship_ids]);
      if (currentSelectedId && node_ids.includes(currentSelectedId)) {
        this._details.hidden = true;
      }
      // Rebuild snapshot without removed elements
      if (this._snapshot) {
        this._snapshot = {
          ...this._snapshot,
          nodes: (this._snapshot.nodes || []).filter((n) => !node_ids.includes(n.id)),
          relationships: (this._snapshot.relationships || []).filter((r) => !relationship_ids.includes(r.id)),
        };
        this._renderNodeList(this._snapshot.nodes);
        this._renderFilters();
        this._summary.textContent = `${this._snapshot.nodes.length} nodes and ${this._snapshot.relationships.length} relationships`;
      }
      return;
    }
    if (kind === "upsert") {
      // Refresh visible nodes that are in the changed set
      for (const nodeId of node_ids) {
        if (this._graph.hasNode(nodeId)) {
          this._hass.callWS({ type: "ontology/graph_detail", element_id: nodeId })
            .then((detail) => {
              if (detail?.node) this._graph.updateElements([detail.node], this._hass);
            })
            .catch(() => {});
        }
      }
    }
  }

  _showState(state, retry = false) {
    if (!state) {
      this._state.hidden = true;
      this._state.removeAttribute("data-state");
      return;
    }
    const [title, detail] = STATE_MESSAGES[state];
    this._state.hidden = false;
    this._state.dataset.state = state;
    this._state.querySelector("strong").textContent = title;
    this._state.querySelector("span").textContent = detail;
    this._state.querySelector("button")?.remove();
    if (retry) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Retry";
      this._state.append(button);
    }
  }

  _renderNodeList(nodes) {
    this._list.replaceChildren();
    const uniqueNodes = [...new Map(nodes.map((node) => [node.id, node])).values()];
    const unassigned = uniqueNodes.some((node) => node.type === "DEVICE" && !this._isAssigned(node.id));
    const visibleNodes = unassigned
      ? [...uniqueNodes, { id: UNASSIGNED_ID, haId: UNASSIGNED_ID, type: "PRESENTATION_GROUP", label: "Unassigned", icon: "mdi:folder-question-outline", presentationOnly: true }]
      : uniqueNodes;
    for (const node of visibleNodes) {
      // Synthetic nodes (HOME hub, unassigned group) don't belong in the nav list
      if (node.synthetic) continue;
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.nodeId = node.id;
      button.setAttribute("aria-pressed", "false");
      const status = node.unavailable ? ", unavailable" : node.type === "VALIDATION_FINDING" ? ", validation finding" : "";
      button.setAttribute("aria-label", `${node.label}, ${node.type.toLowerCase().replaceAll("_", " ")}${status}`);
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", resolveOntologyIcon(node, this._hass));
      icon.setAttribute("aria-hidden", "true");
      const text = document.createElement("span");
      text.textContent = node.label;
      const detail = document.createElement("small");
      detail.textContent = node.presentationOnly ? "Presentation only" : node.unavailable ? "Unavailable" : node.type.toLowerCase().replaceAll("_", " ");
      text.append(detail);
      button.append(icon, text);
      button.addEventListener("click", () => this._graph.selectNode(node.id));
      item.append(button);
      this._list.append(item);
    }
  }

  _isAssigned(deviceId) {
    const nodes = new Map((this._snapshot?.nodes || []).map((node) => [node.id, node]));
    return (this._snapshot?.relationships || []).some((relationship) => {
      const source = nodes.get(relationship.source);
      const target = nodes.get(relationship.target);
      return (source?.type === "AREA" && relationship.target === deviceId) || (target?.type === "AREA" && relationship.source === deviceId);
    });
  }

  _syncSelection(nodeId) {
    for (const button of this._list.querySelectorAll("button[data-node-id]")) {
      button.setAttribute("aria-pressed", String(button.dataset.nodeId === nodeId));
    }
    this.dataset.selectedId = nodeId || "";
  }

  async _selectionChanged(elementId) {
    this._currentDetailId = elementId;
    this._syncSelection(elementId);
    if (!elementId || elementId === UNASSIGNED_ID || elementId === SYNTHETIC_HOME_ID) {
      this._details.hidden = true;
      return;
    }
    const type = this._graph.getNodeType(elementId);
    await this._loadDetail(elementId, type === "AREA" || type === "DEVICE");
  }

  async _search(rawTerm) {
    const term = String(rawTerm || "").trim();
    this._searchResults.replaceChildren();
    if (!term) return;
    try {
      const result = await this._hass.callWS({ type: "ontology/graph_search", term, limit: 50 });
      for (const match of result.matches || []) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("role", "option");
        button.textContent = match.label;
        const id = document.createElement("small");
        id.textContent = match.haId;
        button.append(id);
        button.addEventListener("click", () => this._focusSearchResult(match));
        item.append(button);
        this._searchResults.append(item);
      }
    } catch (error) {
      this._showState(error?.code === "gateway_unavailable" ? "unavailable" : "error", true);
    }
  }

  async _focusSearchResult(match) {
    if (!this._graph.hasNode(match.id)) await this._loadDetail(match.id, true);
    this._graph.selectNode(match.id);
  }

  async _loadDetail(elementId, addConnections = false) {
    try {
      const detail = await this._hass.callWS({ type: "ontology/graph_detail", element_id: elementId });
      // Guard: if the user selected a different element while the WS call was in flight, discard this result
      if (this._currentDetailId !== elementId) return;
      const element = detail.node || detail.relationship;
      if (!element) return;
      if (addConnections && detail.directConnections) {
        this._mergeSnapshot(detail.directConnections);
        this._graph.applySlice(detail.directConnections, this._hass, elementId);
        this._renderNodeList(this._snapshot.nodes);
        this._renderFilters();
      }
      this._renderDetails(element);
    } catch (error) {
      this._showState(error?.code === "gateway_unavailable" ? "unavailable" : "error", true);
    }
  }

  _renderDetails(element) {
    this._details.hidden = false;
    this._details.querySelector("h2").textContent = element.label || element.type || element.id;
    const elementKind = element.source && element.target ? "Relationship" : element.type || "Node";
    this._details.querySelector(".detail-record").textContent = `${elementKind} · ${element.haId || element.id}`;
    const properties = this._details.querySelector(".detail-properties");
    properties.replaceChildren();
    for (const property of element.properties || []) {
      const name = document.createElement("dt");
      name.textContent = property.name;
      const value = document.createElement("dd");
      value.textContent = property.displayValue;
      properties.append(name, value);
    }
    this._details.querySelector("[data-command='expand']").hidden = Boolean(element.source && element.target);
  }

  async _expandSelection() {
    const nodeId = this._graph.selectedId;
    if (!nodeId || nodeId === UNASSIGNED_ID) return;
    const status = this._details.querySelector(".expansion-status");
    try {
      const slice = await this._hass.callWS({ type: "ontology/graph_expand", node_id: nodeId, node_limit: 25, edge_limit: 50, cursor: null });
      this._mergeSnapshot(slice);
      this._graph.applySlice(slice, this._hass, nodeId);
      this._renderNodeList(this._snapshot.nodes);
      this._renderFilters();
      status.textContent = slice.truncated ? "Expansion is truncated. Expand again to continue." : "One-hop relationships loaded.";
    } catch (error) {
      status.textContent = error?.code === "stale_cursor" ? "The graph changed. Start this expansion again." : "Expansion could not be completed.";
    }
  }

  _mergeSnapshot(slice) {
    const nodes = new Map((this._snapshot?.nodes || []).map((node) => [node.id, node]));
    const relationships = new Map((this._snapshot?.relationships || []).map((relationship) => [relationship.id, relationship]));
    for (const node of slice.nodes || []) nodes.set(node.id, node);
    for (const relationship of slice.relationships || []) relationships.set(relationship.id, relationship);
    this._snapshot = { ...this._snapshot, ...slice, nodes: [...nodes.values()], relationships: [...relationships.values()] };
    this._summary.textContent = `${nodes.size} nodes and ${relationships.size} relationships`;
  }

  _renderFilters() {
    const nodeTypes = [...new Set((this._snapshot?.nodes || []).map((node) => node.type))].sort();
    const relationshipTypes = [...new Set((this._snapshot?.relationships || []).map((relationship) => relationship.type))].sort();
    this._renderFilterGroup(this._nodeFilters, nodeTypes, this._hiddenNodeTypes, "node");
    this._renderFilterGroup(this._relationshipFilters, relationshipTypes, this._hiddenRelationshipTypes, "relationship");
  }

  _renderFilterGroup(container, types, hiddenTypes, kind) {
    container.replaceChildren();
    for (const type of types) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = !hiddenTypes.has(type);
      const readableType = type.toLowerCase().replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
      input.setAttribute("aria-label", kind === "node" ? readableType : `Relationship: ${readableType}`);
      input.addEventListener("change", () => {
        if (input.checked) hiddenTypes.delete(type);
        else hiddenTypes.add(type);
        this._graph.setFilters(this._hiddenNodeTypes, this._hiddenRelationshipTypes);
      });
      label.append(input, document.createTextNode(`${kind === "node" ? "" : "Relationship: "}${type.toLowerCase().replaceAll("_", " ")}`));
      container.append(label);
    }
  }

  _clearFilters() {
    this._hiddenNodeTypes.clear();
    this._hiddenRelationshipTypes.clear();
    this._graph.setFilters(this._hiddenNodeTypes, this._hiddenRelationshipTypes);
    this._renderFilters();
  }
}

customElements.define("ontology-panel", OntologyPanel);


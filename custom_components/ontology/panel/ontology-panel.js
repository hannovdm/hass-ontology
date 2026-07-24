// Ontology sidebar panel (User Story 8).
//
// Dependency-free ES module, no build step (research.md §2). Communicates
// exclusively through the `ontology/area_context`, `ontology/entity_context`,
// and `ontology/search` websocket_api commands (contracts/websocket-api.md).

class OntologyPanel extends HTMLElement {
  connectedCallback() {
    if (this._rendered) {
      return;
    }
    this._rendered = true;
    this.style.display = "block";
    this.style.padding = "16px";
    this.style.fontFamily = "var(--paper-font-body1_-_font-family, sans-serif)";
    this.innerHTML = `
      <div style="max-width: 720px; margin: 0 auto;">
        <h1>Ontology Explorer</h1>
        <input id="ontology-search-input" type="text" placeholder="Search areas, devices, entities..."
          style="width: 100%; padding: 8px; box-sizing: border-box; font-size: 1rem;" />
        <div id="ontology-results" style="margin-top: 16px;"></div>
        <div id="ontology-detail" style="margin-top: 16px;"></div>
      </div>
    `;
    this._searchInput = this.querySelector("#ontology-search-input");
    this._resultsEl = this.querySelector("#ontology-results");
    this._detailEl = this.querySelector("#ontology-detail");
    this._searchInput.addEventListener("input", () => this._onSearchInput());
  }

  set hass(hass) {
    this._hass = hass;
  }

  _onSearchInput() {
    const query = this._searchInput.value.trim();
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }
    if (!query) {
      this._resultsEl.innerHTML = "";
      return;
    }
    this._debounceTimer = setTimeout(() => this._runSearch(query), 250);
  }

  async _runSearch(query) {
    if (!this._hass) {
      return;
    }
    try {
      const response = await this._hass.callWS({
        type: "ontology/search",
        query,
        limit: 50,
      });
      this._renderResults(response.results || []);
    } catch (err) {
      this._resultsEl.innerHTML = `<p style="color: var(--error-color, red);">Search failed: ${
        (err && err.message) || err
      }</p>`;
    }
  }

  _renderResults(results) {
    if (!results.length) {
      this._resultsEl.innerHTML = "<p>No matches.</p>";
      return;
    }
    this._resultsEl.innerHTML = "";
    const list = document.createElement("ul");
    list.style.listStyle = "none";
    list.style.padding = "0";
    for (const item of results) {
      const li = document.createElement("li");
      li.style.padding = "8px";
      li.style.cursor = "pointer";
      li.style.borderBottom = "1px solid var(--divider-color, #e0e0e0)";
      li.textContent = `[${item.type}] ${item.name || item.ha_id}`;
      li.addEventListener("click", () => this._openDetail(item));
      list.appendChild(li);
    }
    this._resultsEl.appendChild(list);
  }

  async _openDetail(item) {
    if (!this._hass) {
      return;
    }
    this._detailEl.innerHTML = "<p>Loading...</p>";
    try {
      let response;
      if (item.type === "Area") {
        response = await this._hass.callWS({
          type: "ontology/area_context",
          area_id: item.ha_id,
        });
      } else if (item.type === "Entity") {
        response = await this._hass.callWS({
          type: "ontology/entity_context",
          entity_id: item.ha_id,
        });
      } else {
        this._detailEl.innerHTML = `<p>Detail view not available for type "${item.type}". Full node id: ${item.ha_id}</p>`;
        return;
      }
      this._renderDetail(item, response);
    } catch (err) {
      this._detailEl.innerHTML = `<p style="color: var(--error-color, red);">Failed to load detail: ${
        (err && err.message) || err
      }</p>`;
    }
  }

  _renderDetail(item, response) {
    const pre = document.createElement("pre");
    pre.style.whiteSpace = "pre-wrap";
    pre.style.background = "var(--secondary-background-color, #f5f5f5)";
    pre.style.padding = "12px";
    pre.style.borderRadius = "4px";
    pre.textContent = JSON.stringify(response, null, 2);
    this._detailEl.innerHTML = `<h2>${item.name || item.ha_id}</h2>`;
    this._detailEl.appendChild(pre);
  }
}

customElements.define("ontology-panel", OntologyPanel);


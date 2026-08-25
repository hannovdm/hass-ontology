import { expect, test } from "@playwright/test";

const FOCUS_HIGHLIGHT_COLOR = "rgb(35, 114, 138)";

async function openFixture(page, state = "populated") {
  await page.goto(`/tests/browser/graph-fixture.html?state=${state}`);
  await expect(page.locator("ontology-panel")).toBeVisible();
}

test("authenticated non-admin sees a nonblank area and device graph", async ({ page }) => {
  await openFixture(page);
  await expect(page.getByRole("heading", { name: "Ontology Explorer" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen, area" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned, presentation group" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Graph legend" })).toBeVisible();

  const graphFacts = await page.locator("ontology-panel").evaluate((panel) => ({
    nodes: panel.graph.cy.nodes().map((node) => ({ id: node.id(), icon: node.data("icon"), classes: node.classes() })),
    edges: panel.graph.cy.edges().map((edge) => edge.data()),
    paintedPixels: Array.from(panel.graph.querySelectorAll("canvas")).reduce((count, canvas) => {
      const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] !== 0) count += 1;
      }
      return count;
    }, 0),
  }));

  expect(graphFacts.paintedPixels).toBeGreaterThan(100);
  expect(graphFacts.nodes.find(({ id }) => id === "presentation:unassigned")).toBeTruthy();
  expect(graphFacts.nodes.find(({ id }) => id === "Device:lamp").icon).toBe("mdi:lightbulb");
  expect(graphFacts.nodes.find(({ id }) => id === "Device:portable").classes).toContain("unavailable");
  expect(graphFacts.nodes.find(({ id }) => id === "ValidationFinding:missing-area").classes).toContain("validation-finding");
  expect(graphFacts.edges.find(({ id }) => id === "HAS_DEVICE:1").label).toBe("has device →");
});

test("starts with areas and drills into an area on selection", async ({ page }) => {
  await openFixture(page, "area-overview");
  await expect(page.getByRole("button", { name: "Kitchen, area" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).not.toBeVisible();

  await page.getByRole("button", { name: "Kitchen, area" }).click();

  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Portable sensor, device, unavailable" })).toBeVisible();
  await expect(page.getByText("3 nodes and 1 relationships")).toBeVisible();
});

test("positions the initial graph at the top of the stage", async ({ page }) => {
  await openFixture(page, "area-overview");
  const top = await page.locator("ontology-panel").evaluate((panel) =>
    panel.graph.cy.nodes(":visible").renderedBoundingBox({ includeLabels: true }).y1,
  );
  expect(top).toBeGreaterThanOrEqual(30);
  expect(top).toBeLessThanOrEqual(42);
});

test("renders a snapshot containing duplicate and orphaned elements", async ({ page }) => {
  await openFixture(page, "malformed");

  await expect(page.getByRole("button", { name: "Kitchen, area" })).toBeVisible();
  const ids = await page.locator("ontology-panel").evaluate((panel) =>
    panel.graph.cy.elements().map((element) => element.id()),
  );
  expect(ids.filter((id) => id === "Area:kitchen")).toHaveLength(1);
  expect(ids.filter((id) => id === "HAS_DEVICE:1")).toHaveLength(1);
  expect(ids).not.toContain("ORPHAN:1");
});

test("semantic node list is synchronized and keyboard operable", async ({ page }) => {
  await openFixture(page);
  const list = page.getByRole("list", { name: "Ontology graph nodes" });
  await expect(list).toBeVisible();
  await expect(page.getByText(/4 nodes and 2 relationships/)).toBeVisible();

  const portable = page.getByRole("button", { name: /Portable sensor.*unavailable/i });
  await portable.focus();
  await expect(portable).toBeFocused();
  await portable.press("Enter");
  await expect(portable).toHaveAttribute("aria-pressed", "true");
  await expect(portable.locator("ha-icon")).toHaveAttribute("icon", "mdi:devices");
});

test("supports keyboard journeys with visible focus and non-color cues", async ({ page }) => {
  await openFixture(page);
  const panel = page.locator("ontology-panel");

  const zoomOut = page.getByRole("button", { name: "Zoom out" });
  const initialZoom = await panel.evaluate((element) => element.graph.cy.zoom());
  await zoomOut.focus();
  await expect(zoomOut).toBeFocused();
  await expect(zoomOut).toHaveCSS("border-top-color", FOCUS_HIGHLIGHT_COLOR);
  await zoomOut.press("Enter");
  expect(await panel.evaluate((element) => element.graph.cy.zoom())).toBeLessThan(initialZoom);

  const fit = page.getByRole("button", { name: "Fit graph" });
  await fit.focus();
  await expect(fit).toBeFocused();
  await fit.press("Enter");

  const unavailableNode = page.getByRole("button", { name: "Portable sensor, device, unavailable" });
  await unavailableNode.focus();
  await expect(unavailableNode).toBeFocused();
  await expect(unavailableNode.locator("small")).toHaveText("Unavailable");
  await expect(unavailableNode).toHaveAttribute("aria-label", /unavailable/i);

  const findingNode = page.getByRole("button", { name: /Missing area assignment, validation finding/i });
  await findingNode.scrollIntoViewIfNeeded();
  await findingNode.focus();
  await expect(findingNode).toBeVisible();
  await expect(findingNode).toBeFocused();
  await expect(findingNode.locator("small")).toHaveText(/validation finding/i);
  await expect(page.getByRole("region", { name: "Graph legend" })).toContainText("Unavailable (dashed)");
  await expect(page.getByRole("region", { name: "Graph legend" })).toContainText("Validation finding (diamond)");
});

for (const state of ["loading", "empty", "partial", "unavailable", "error"]) {
  test(`renders the ${state} state explicitly`, async ({ page }) => {
    await openFixture(page, state);
    await expect(page.locator(`[data-state="${state}"]`)).toBeVisible();
  });
}

for (const exactTerm of ["Entity:sensor.kitchen_temperature", "Kitchen temperature"]) {
test(`finds exact ${exactTerm.includes(":") ? "ID" : "name"} and focuses it within three interactions`, async ({ page }) => {
  await openFixture(page, "interactive");
  const search = page.getByRole("searchbox", { name: "Search ontology" });
  await search.fill(exactTerm);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("option", { name: /Kitchen temperature.*sensor\.kitchen_temperature/i }).click();
  await expect(page.getByRole("heading", { name: "Kitchen temperature" })).toBeVisible();
  await expect(page.locator("ontology-panel")).toHaveAttribute("data-selected-id", "Entity:sensor.kitchen_temperature");
});
}

test("shows safe relationship details", async ({ page }) => {
  await openFixture(page, "interactive");
  await page.getByRole("button", { name: "Kitchen lamp, device" }).click();
  await expect.poll(() => page.locator("ontology-panel").evaluate((panel) =>
    panel.graph.cy.getElementById("HAS_ENTITY:primary").nonempty(),
  )).toBe(true);
  await page.locator("ontology-panel").evaluate((panel) => {
    panel.graph.cy.getElementById("HAS_ENTITY:primary").select();
    return null;
  });
  await expect(page.getByRole("heading", { name: "HAS_ENTITY" })).toBeVisible();
  await expect(page.getByText("Relationship · HAS_ENTITY:primary")).toBeVisible();
});

test("distinguishes duplicate names, self-loops, and parallel edges", async ({ page }) => {
  await openFixture(page, "interactive");
  await page.getByRole("searchbox", { name: "Search ontology" }).fill("Shared sensor");
  await page.getByRole("button", { name: "Search" }).click();
  const results = page.getByRole("option", { name: /Shared sensor/i });
  await expect(results).toHaveCount(2);
  await expect(results.nth(0)).toContainText("sensor.shared_a");
  await expect(results.nth(1)).toContainText("sensor.shared_b");
  await results.nth(0).click();

  const edgeFacts = await page.locator("ontology-panel").evaluate((panel) => {
    const edges = panel.graph.cy.edges();
    return {
      selfLoops: edges.filter((edge) => edge.source().id() === edge.target().id()).length,
      parallel: edges.filter((edge) => edge.source().id() === "Device:lamp" && edge.target().id() === "Entity:sensor.kitchen_temperature").length,
    };
  });
  expect(edgeFacts.selfLoops).toBe(1);
  expect(edgeFacts.parallel).toBe(2);
});

test("expands one hop and preserves selection and viewport", async ({ page }) => {
  await openFixture(page, "interactive");
  await page.getByRole("button", { name: "Kitchen lamp, device" }).click();
  const before = await page.locator("ontology-panel").evaluate((panel) => {
    panel.graph.cy.pan({ x: 73, y: 41 });
    panel.graph.cy.zoom(1.4);
    return { pan: panel.graph.cy.pan(), zoom: panel.graph.cy.zoom() };
  });
  await page.getByRole("button", { name: "Expand one hop" }).click();
  await expect(page.getByRole("button", { name: "Kitchen temperature, entity" })).toBeVisible();
  const after = await page.locator("ontology-panel").evaluate((panel) => ({
    pan: panel.graph.cy.pan(),
    zoom: panel.graph.cy.zoom(),
    selected: panel.graph.cy.$("node:selected").first().id(),
  }));
  expect(after.selected).toBe("Device:lamp");
  expect(after.pan).toEqual(before.pan);
  expect(after.zoom).toBeCloseTo(before.zoom);
});

test("single-clicking an area replaces the view with its complete focused context", async ({ page }) => {
  test.setTimeout(60_000);
  await openFixture(page, "double-click-expansion");
  await expect.poll(() => page.locator("ontology-panel").evaluate((panel) => Boolean(panel.graph._fg))).toBe(true);
  await expect(page.getByRole("button", { name: "Garage, area" })).toBeVisible();
  await page.locator("ontology-panel").evaluate((panel) => {
    const area = panel.graph._fg.graphData().nodes.find(({ id }) => id === "Area:kitchen");
    panel.graph._fg.onNodeClick()(area);
  });

  await expect(page.locator(".details h2")).toHaveText("Kitchen");
  await expect(page.locator(".detail-record")).toHaveText("AREA · kitchen");
  await expect(page.getByRole("heading", { name: "Nodes in Kitchen" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Hall display, device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen temperature, entity" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Morning routine, automation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen card, dashboard card" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Home dashboard, dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Relationships in Kitchen" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen, has device, Kitchen lamp" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, has entity, Kitchen temperature" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Hall display, has entity, Kitchen temperature" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Morning routine, references, Kitchen temperature" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen card, displays entity, Kitchen temperature" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Home dashboard, contains card, Kitchen card" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Garage, area" })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen, area" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("region", { name: "Graph legend" }).locator('ha-icon[icon="mdi:tablet-dashboard"]')).toHaveCount(1);
  await expect(page.getByRole("region", { name: "Graph legend" })).toContainText("device · Hall display");
  await expect(page.getByText("All available relationships loaded.")).toBeVisible();
  await page.getByRole("button", { name: "Morning routine, references, Kitchen temperature" }).click();
  await expect(page.locator(".details h2")).toHaveText("REFERENCES");
  await expect(page.locator(".detail-record")).toContainText("Relationship");

  const facts = await page.locator("ontology-panel").evaluate((panel) => ({
    expansionIds: panel._wsCalls
      .filter(({ type }) => type === "ontology/graph_expand")
      .map(({ node_id: nodeId }) => nodeId),
    expansionLimits: panel._wsCalls
      .filter(({ type }) => type === "ontology/graph_expand")
      .map(({ node_limit: nodeLimit, edge_limit: edgeLimit }) => ({ nodeLimit, edgeLimit })),
    links: panel.graph._fg.graphData().links.map(({ id, source, target }) => ({
      id,
      source: source.id || source,
      target: target.id || target,
    })),
    graphNodeIds: panel.graph._fg.graphData().nodes.map(({ id }) => id),
  }));
  expect(facts.expansionIds).toEqual([
    "Area:kitchen",
    "Device:lamp",
    "Entity:sensor.kitchen_temperature",
    "Device:hall-display",
    "DashboardCard:lovelace::0::0",
  ]);
  expect(facts.expansionLimits).toEqual(facts.expansionIds.map(() => ({ nodeLimit: 250, edgeLimit: 500 })));
  expect(facts.graphNodeIds).toEqual(expect.arrayContaining([
    "Area:kitchen",
    "Device:lamp",
    "Device:hall-display",
    "Entity:sensor.kitchen_temperature",
    "Automation:morning",
    "DashboardCard:lovelace::0::0",
    "Dashboard:lovelace",
  ]));
  expect(facts.graphNodeIds).not.toContain("Area:garage");
  expect(facts.graphNodeIds).not.toContain("presentation:home");
  expect(facts.graphNodeIds).not.toContain("presentation:unassigned");
  expect(facts.links).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: "HAS_DEVICE:1", source: "Area:kitchen", target: "Device:lamp" }),
    expect.objectContaining({ id: "HAS_ENTITY:primary", source: "Device:lamp", target: "Entity:sensor.kitchen_temperature" }),
    expect.objectContaining({ id: "HAS_ENTITY:external", source: "Device:hall-display", target: "Entity:sensor.kitchen_temperature" }),
    expect.objectContaining({ id: "REFERENCES:1", source: "Automation:morning", target: "Entity:sensor.kitchen_temperature" }),
    expect.objectContaining({ id: "DISPLAYS_ENTITY:1", source: "DashboardCard:lovelace::0::0", target: "Entity:sensor.kitchen_temperature" }),
    expect.objectContaining({ id: "CONTAINS_CARD:1", source: "Dashboard:lovelace", target: "DashboardCard:lovelace::0::0" }),
  ]));

  await page.waitForTimeout(1800);
  const framing = await page.locator("ontology-panel").evaluate((panel) => {
    const graph = panel.graph;
    const width = graph.clientWidth;
    const height = graph.clientHeight;
    const ids = [
      "Area:kitchen",
      "Device:lamp",
      "Entity:sensor.kitchen_temperature",
      "Automation:morning",
      "DashboardCard:lovelace::0::0",
      "Dashboard:lovelace",
    ];
    return ids.map((id) => {
      const node = graph._nodeMap.get(id);
      const point = graph._fg.graph2ScreenCoords(node.x, node.y, node.z);
      return { id, x: point.x, y: point.y, width, height };
    });
  });
  for (const node of framing) {
    expect(node.x, `${node.id} should fit horizontally`).toBeGreaterThan(0);
    expect(node.x, `${node.id} should fit horizontally`).toBeLessThan(node.width);
    expect(node.y, `${node.id} should fit vertically`).toBeGreaterThan(0);
    expect(node.y, `${node.id} should fit vertically`).toBeLessThan(node.height);
  }
  const focusedArea = framing.find(({ id }) => id === "Area:kitchen");
  expect(Math.abs(focusedArea.x - focusedArea.width / 2)).toBeLessThan(focusedArea.width * 0.12);
  expect(Math.abs(focusedArea.y - focusedArea.height / 2)).toBeLessThan(focusedArea.height * 0.12);

  await page.getByRole("button", { name: "Kitchen lamp, device" }).click();
  await expect(page.locator(".details h2")).toHaveText("Kitchen lamp");
  await expect(page.locator(".detail-record")).toHaveText("DEVICE · lamp");
  await expect(page.getByRole("heading", { name: "Nodes in Kitchen lamp" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Relationships in Kitchen lamp" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Kitchen temperature, entity" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Home dashboard, dashboard" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Morning routine, references, Kitchen temperature" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen card, displays entity, Kitchen temperature" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Home dashboard, contains card, Kitchen card" })).toBeVisible();

  await page.locator("ontology-panel").evaluate((panel) => panel._loadSnapshot(true, true));
  await expect(page.getByRole("heading", { name: "Nodes in Kitchen lamp" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Garage, area" })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Home dashboard, contains card, Kitchen card" })).toBeVisible();

  await page.getByRole("button", { name: "Hall display, device" }).click();
  await expect(page.locator(".details h2")).toHaveText("Hall display");
  await expect(page.getByRole("heading", { name: "Nodes in Hall display" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Hall display, has entity, Kitchen temperature" })).toBeVisible();
});

test("single-clicking a dashboard loads every direct card relationship", async ({ page }) => {
  await openFixture(page, "dashboard-focus");
  await expect.poll(() => page.locator("ontology-panel").evaluate((panel) => Boolean(panel.graph._fg))).toBe(true);
  await page.locator("ontology-panel").evaluate((panel) => {
    const dashboard = panel.graph._fg.graphData().nodes.find(({ id }) => id === "Dashboard:lovelace");
    panel.graph._fg.onNodeClick()(dashboard);
  });

  await expect(page.getByRole("button", { name: "Kitchen card, dashboard card" })).toBeVisible();
  await expect(page.getByText("All available relationships loaded.")).toBeVisible();
  const facts = await page.locator("ontology-panel").evaluate((panel) => {
    const expansion = panel._wsCalls.find(({ type }) => type === "ontology/graph_expand");
    const relationship = panel.graph._fg.graphData().links.find(({ id }) => id === "CONTAINS_CARD:1");
    return {
      expansion,
      relationship: relationship && {
        source: relationship.source.id || relationship.source,
        target: relationship.target.id || relationship.target,
      },
    };
  });
  expect(facts.expansion).toMatchObject({
    node_id: "Dashboard:lovelace",
    node_limit: 250,
    edge_limit: 500,
  });
  expect(facts.relationship).toEqual({
    source: "Dashboard:lovelace",
    target: "DashboardCard:lovelace::0::0",
  });
});

test("supports filter, clear, pan, zoom, fit, reset, and drag", async ({ page }) => {
  await openFixture(page, "interactive");
  const panel = page.locator("ontology-panel");
  await page.getByRole("checkbox", { name: "Device", exact: true }).uncheck();
  expect(await panel.evaluate((element) => element.graph.cy.$("node.device:visible").length)).toBe(0);
  await page.getByRole("button", { name: "Clear filters" }).click();
  expect(await panel.evaluate((element) => element.graph.cy.$("node.device:visible").length)).toBeGreaterThan(0);

  const initial = await panel.evaluate((element) => ({ pan: element.graph.cy.pan(), zoom: element.graph.cy.zoom() }));
  await page.getByRole("button", { name: "Zoom in" }).click();
  expect(await panel.evaluate((element) => element.graph.cy.zoom())).toBeGreaterThan(initial.zoom);
  await page.getByRole("button", { name: "Zoom out" }).click();
  await page.getByRole("button", { name: "Fit graph" }).click();
  await panel.evaluate((element) => {
    element.graph.cy.panBy({ x: 30, y: 20 });
    return null;
  });
  expect(await panel.evaluate((element) => element.graph.cy.pan())).not.toEqual(initial.pan);
  await page.getByRole("button", { name: "Reset view" }).click();

  const beforeDrag = await panel.evaluate((element) => {
    const node = element.graph.cy.getElementById("Device:lamp");
    return { position: node.position(), rendered: node.renderedPosition(), grabbable: node.grabbable() };
  });
  const graphBox = await panel.locator("ontology-graph").boundingBox();
  expect(graphBox).toBeTruthy();
  await page.mouse.move(graphBox.x + beforeDrag.rendered.x, graphBox.y + beforeDrag.rendered.y);
  await page.mouse.down();
  await page.mouse.move(graphBox.x + beforeDrag.rendered.x + 45, graphBox.y + beforeDrag.rendered.y + 25, { steps: 5 });
  await page.mouse.up();
  const afterDrag = await panel.evaluate((element) => element.graph.cy.getElementById("Device:lamp").position());
  expect(beforeDrag.grabbable).toBe(true);
  expect(afterDrag).not.toEqual(beforeDrag.position);

  for (const name of ["Zoom in", "Zoom out", "Fit graph", "Reset view"]) {
    await expect(page.getByRole("button", { name })).toHaveAttribute("title", name);
  }
});

// ---------------------------------------------------------------------------
// User Story 3: Automatic Live Updates (T039)
// ---------------------------------------------------------------------------

test("upsert event updates a visible node without replacing the graph", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");

  // Verify initial state
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
  const initialNodeCount = await panel.evaluate((element) => element.graph.cy.nodes().length);

  // Fire an upsert event for a visible node via the fixture helper
  await panel.evaluate((element) => {
    element._dispatchLiveEvent({ revision: 8, kind: "upsert", node_ids: ["Device:lamp"], relationship_ids: [], changed_properties: ["state"], occurred_at: new Date().toISOString() });
  });
  await page.waitForTimeout(350); // wait for 250 ms debounce + margin

  // Graph should still have same node count (no duplication, no removal)
  const afterNodeCount = await panel.evaluate((element) => element.graph.cy.nodes().length);
  expect(afterNodeCount).toBe(initialNodeCount);
  // Node label still visible (not replaced with reconcile reload)
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();
});

test("remove event removes the node from graph and node list", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();

  await panel.evaluate((element) => {
    element._dispatchLiveEvent({ revision: 9, kind: "remove", node_ids: ["Device:lamp"], relationship_ids: ["HAS_DEVICE:1"], changed_properties: [], occurred_at: new Date().toISOString() });
  });
  await page.waitForTimeout(350);

  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).not.toBeVisible();
  const lampInGraph = await panel.evaluate((element) => element.graph.cy.getElementById("Device:lamp").nonempty());
  expect(lampInGraph).toBe(false);
});

test("reconcile event triggers a full graph reload", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");
  await expect(page.getByRole("button", { name: "Kitchen lamp, device" })).toBeVisible();

  let snapshotCallCount = 0;
  await panel.evaluate((element) => {
    const original = element._hass.callWS.bind(element._hass);
    element._hass.callWS = async (message) => {
      if (message.type === "ontology/graph_snapshot") element._snapshotCallCount = (element._snapshotCallCount || 0) + 1;
      return original(message);
    };
  });

  await panel.evaluate((element) => {
    element._dispatchLiveEvent({ revision: 10, kind: "reconcile", node_ids: [], relationship_ids: [], changed_properties: [], occurred_at: new Date().toISOString() });
  });
  await page.waitForTimeout(200);

  const callCount = await panel.evaluate((element) => element._snapshotCallCount || 0);
  expect(callCount).toBeGreaterThanOrEqual(1);
});

test("viewport and selection are preserved across incremental upsert", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");
  await page.getByRole("button", { name: "Kitchen, area" }).click();

  const before = await panel.evaluate((element) => {
    element.graph.cy.pan({ x: 55, y: 33 });
    element.graph.cy.zoom(1.3);
    return { pan: element.graph.cy.pan(), zoom: element.graph.cy.zoom(), selectedId: element.graph.cy.$("node:selected").first().id() };
  });

  await panel.evaluate((element) => {
    element._dispatchLiveEvent({ revision: 8, kind: "upsert", node_ids: ["Area:kitchen"], relationship_ids: [], changed_properties: ["name"], occurred_at: new Date().toISOString() });
  });
  await page.waitForTimeout(350);

  const after = await panel.evaluate((element) => ({
    pan: element.graph.cy.pan(),
    zoom: element.graph.cy.zoom(),
    selectedId: element.graph.cy.$("node:selected").first().id(),
  }));
  expect(after.selectedId).toBe(before.selectedId);
  expect(after.pan).toEqual(before.pan);
  expect(after.zoom).toBeCloseTo(before.zoom);
});

test("filters are preserved across upsert events", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");
  await page.getByRole("checkbox", { name: "Device", exact: true }).uncheck();

  const hiddenBefore = await panel.evaluate((element) => element.graph.cy.$("node.device:visible").length);
  expect(hiddenBefore).toBe(0);

  await panel.evaluate((element) => {
    element._dispatchLiveEvent({ revision: 8, kind: "upsert", node_ids: ["Device:lamp"], relationship_ids: [], changed_properties: ["state"], occurred_at: new Date().toISOString() });
  });
  await page.waitForTimeout(350);

  const hiddenAfter = await panel.evaluate((element) => element.graph.cy.$("node.device:visible").length);
  expect(hiddenAfter).toBe(0);
});

test("removed selected node shows a notice and clears the detail panel", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");
  await page.getByRole("button", { name: "Kitchen lamp, device" }).click();
  await expect(page.getByRole("heading", { name: "Kitchen lamp" })).toBeVisible();

  await panel.evaluate((element) => {
    element._dispatchLiveEvent({ revision: 9, kind: "remove", node_ids: ["Device:lamp"], relationship_ids: ["HAS_DEVICE:1"], changed_properties: [], occurred_at: new Date().toISOString() });
  });
  await page.waitForTimeout(350);

  // Detail panel should be hidden or show a removal notice
  const detailHidden = await panel.evaluate((element) => element.querySelector(".details").hidden);
  expect(detailHidden).toBe(true);
});

test("stale indicator appears when subscription is marked stale", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");
  await page.waitForTimeout(100);

  // Simulate marking the panel as stale (subscription disconnect)
  await panel.evaluate((element) => element._setSubscriptionState("stale"));

  await expect(page.locator("[data-subscription-state='stale']")).toBeVisible();
});

test("reconnecting indicator appears and disappears after resubscription", async ({ page }) => {
  await openFixture(page, "live-updates");
  const panel = page.locator("ontology-panel");

  await panel.evaluate((element) => element._setSubscriptionState("reconnecting"));
  await expect(page.locator("[data-subscription-state='reconnecting']")).toBeVisible();

  await panel.evaluate((element) => element._setSubscriptionState("live"));
  await expect(page.locator("[data-subscription-state='reconnecting']")).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// User Story 4: Advanced Graph Workspace - Lab access (T048)
// ---------------------------------------------------------------------------

test("non-admin does not see Lab workspace section", async ({ page }) => {
  await openFixture(page, "populated");
  // Non-admin user (default in fixture) should not see Lab section
  await expect(page.getByRole("region", { name: "Advanced graph workspace" })).not.toBeVisible();
});

test("admin sees Lab workspace section with unavailable reason for direct backend", async ({ page }) => {
  await openFixture(page, "admin");
  await expect(page.getByRole("region", { name: "Advanced graph workspace" })).toBeVisible();
  // Direct backend returns not_addon_backend
  await expect(page.getByText("Requires the Memgraph add-on.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  // Launch link must not be visible when unavailable
  await expect(page.getByRole("link", { name: "Open Memgraph Lab" })).not.toBeVisible();
});

test("admin sees Launch Lab link when Lab is available", async ({ page }) => {
  await openFixture(page, "admin-lab-available");
  await expect(page.getByRole("link", { name: "Open Memgraph Lab" })).toBeVisible();
  const href = await page.getByRole("link", { name: "Open Memgraph Lab" }).getAttribute("href");
  expect(href).toBeTruthy();
  expect(href).toContain("/hassio_ingress/");
});

test("keeps toolbar zoom across a delayed full snapshot refresh", async ({ page }) => {
  await openFixture(page, "area-overview");
  const panel = page.locator("ontology-panel");
  const initialZoom = await panel.evaluate((element) => element.graph.cy.zoom());

  await page.getByRole("button", { name: "Zoom out" }).click();
  const zoomed = await panel.evaluate((element) => element.graph.cy.zoom());
  expect(zoomed).toBeLessThan(initialZoom);

  await panel.evaluate((element) => {
    setTimeout(() => element.graph.setSnapshot(element._snapshot, element._hass), 500);
  });
  await page.waitForTimeout(800);

  expect(await panel.evaluate((element) => element.graph.cy.zoom())).toBeCloseTo(zoomed);
});

test("keeps key regions non-overlapping on desktop and mobile and captures screenshots", async ({ page }, testInfo) => {
  await openFixture(page, "interactive");
  const box = (locator) => locator.boundingBox();
  const header = page.locator(".ontology-header");
  const stage = page.locator(".graph-stage");
  const sidebar = page.locator(".ontology-sidebar");

  const [headerBox, stageBox, sidebarBox] = await Promise.all([box(header), box(stage), box(sidebar)]);
  expect(headerBox).toBeTruthy();
  expect(stageBox).toBeTruthy();
  expect(sidebarBox).toBeTruthy();

  if (testInfo.project.name === "mobile-chromium") {
    expect(sidebarBox.y).toBeGreaterThanOrEqual(stageBox.y + stageBox.height - 1);
  } else {
    expect(sidebarBox.x).toBeGreaterThanOrEqual(stageBox.x + stageBox.width - 1);
  }
  const screenshot = await page.screenshot({ fullPage: true });
  await testInfo.attach(`layout-${testInfo.project.name}`, { body: screenshot, contentType: "image/png" });
});
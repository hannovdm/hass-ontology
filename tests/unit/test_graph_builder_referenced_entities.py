"""Regression test: automations and scripts must yield REFERENCES edges to
the entities they actually act on (data-model.md, US3).

HA automation/script entities do NOT expose their referenced entities via
state attributes - `extra_state_attributes` only ever contains
`last_triggered`/`mode`/`current`/`max`. The real referenced-entity set lives
on the in-memory entity object's `referenced_entities` property, reachable
only via `homeassistant.components.automation.entities_in_automation()` /
`homeassistant.components.script.entities_in_script()`. Reading
`state.attributes.get("entity_id")` (as `graph_builder` used to) silently
returned `[]` for every automation/script, so `ontology.automation_dependencies`
and "what automations depend on X" in Assist never found anything - this test
guards against that regression. Scenes are unaffected (their state attributes
genuinely do include `entity_id`), so they are not covered here.
"""

from __future__ import annotations

from homeassistant.setup import async_setup_component

from custom_components.ontology import graph_builder
from custom_components.ontology.const import REL_REFERENCES


async def test_collect_automations_creates_references_edge_via_action_target(
    hass, mock_memgraph_client
) -> None:
    await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": "Bar lights on",
                    "trigger": [{"platform": "event", "event_type": "test_event"}],
                    "action": [
                        {
                            "service": "homeassistant.turn_on",
                            "target": {"entity_id": "light.bar_lights"},
                        }
                    ],
                }
            ]
        },
    )
    await hass.async_block_till_done()

    await graph_builder.collect_automations(hass, mock_memgraph_client)

    relationship_calls = [
        call.args
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if f"[r:{REL_REFERENCES}]" in call.args[0]
    ]
    assert any(
        params["from_ha_id"] == "automation.bar_lights_on"
        and params["to_ha_id"] == "light.bar_lights"
        for _query, params in relationship_calls
    )


async def test_collect_scripts_creates_references_edge_via_action_target(
    hass, mock_memgraph_client
) -> None:
    await async_setup_component(
        hass,
        "script",
        {
            "script": {
                "turn_on_bar_lights": {
                    "sequence": [
                        {
                            "service": "homeassistant.turn_on",
                            "target": {"entity_id": "light.bar_lights"},
                        }
                    ]
                }
            }
        },
    )
    await hass.async_block_till_done()

    await graph_builder.collect_scripts(hass, mock_memgraph_client)

    relationship_calls = [
        call.args
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if f"[r:{REL_REFERENCES}]" in call.args[0]
    ]
    assert any(
        params["from_ha_id"] == "script.turn_on_bar_lights"
        and params["to_ha_id"] == "light.bar_lights"
        for _query, params in relationship_calls
    )


async def test_fake_automation_state_without_real_config_yields_no_reference(
    hass, mock_memgraph_client
) -> None:
    """A bare `hass.states.async_set` (no real automation config) must NOT
    produce a REFERENCES edge - it never did in production, and this test
    documents why integration test fixtures need a real `automation:`/
    `script:` component setup rather than a fabricated state."""
    hass.states.async_set(
        "automation.fake",
        "on",
        {"entity_id": ["light.bar_lights"], "friendly_name": "Fake"},
    )
    await hass.async_block_till_done()

    await graph_builder.collect_automations(hass, mock_memgraph_client)

    relationship_calls = [
        call.args
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if f"[r:{REL_REFERENCES}]" in call.args[0]
    ]
    assert relationship_calls == []

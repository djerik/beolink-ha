"""Scene helper utilities for BeoLink integration."""

import logging
from typing import Any

from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .entity_helpers import is_entity_name_valid

_LOGGER = logging.getLogger(__name__)


def get_scene_entities(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all scene entities with their area information.

    Returns a list of dicts with keys:
        - state: The scene state object
        - entity_entry: The entity registry entry
        - area_id: The area ID the scene is assigned to
        - name: The scene's friendly name
        - entity_id: The scene's entity ID

    Only includes scenes that have an area assigned and valid names.
    """
    ent_reg = er.async_get(hass)
    result: list[dict[str, Any]] = []

    for state in hass.states.async_all():
        if state.domain != SCENE_DOMAIN:
            continue

        # Get the entity registry entry to check for area assignment
        entity_entry = ent_reg.async_get(state.entity_id)
        if entity_entry is None or entity_entry.area_id is None:
            continue

        # Get scene name (friendly_name or state.name)
        scene_name = state.attributes.get("friendly_name", state.name)
        if not is_entity_name_valid(scene_name):
            _LOGGER.debug(
                "Scene %s has invalid name for BeoLink usage",
                state.entity_id,
            )
            continue

        result.append({
            "state": state,
            "entity_entry": entity_entry,
            "area_id": entity_entry.area_id,
            "name": scene_name,
            "entity_id": state.entity_id,
        })

    return result


def find_scene_by_name(hass: HomeAssistant, scene_name: str) -> State | None:
    """Find scene state by friendly name or entity name.

    Searches through all scenes and returns the first one matching
    the given name (by friendly_name attribute or state name).
    """
    for state in hass.states.async_all():
        if state.domain != SCENE_DOMAIN:
            continue

        current_name = state.attributes.get("friendly_name", state.name)
        if current_name == scene_name:
            return state

    return None

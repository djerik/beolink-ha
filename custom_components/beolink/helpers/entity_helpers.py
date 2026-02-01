"""Entity helper utilities for BeoLink integration."""

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_DOMAIN
from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr

_LOGGER = logging.getLogger(__name__)

# Supported domains for BeoLink resources
SUPPORTED_RESOURCE_DOMAINS = {
    COVER_DOMAIN,
    LIGHT_DOMAIN,
    CAMERA_DOMAIN,
    CLIMATE_DOMAIN,
    ALARM_DOMAIN,
    MEDIA_PLAYER_DOMAIN,
}


def is_entity_name_valid(name: str | None) -> bool:
    """Check if entity name is valid for BeoLink usage.

    Names containing '?' or '/' are not valid as they conflict with
    the BeoLink protocol path format.
    """
    if name is None:
        return False
    return "?" not in name and "/" not in name


def get_entity_from_state(hass: HomeAssistant, state: State) -> Any | None:
    """Get entity object from state.

    Returns the entity if found and has a registry entry, None otherwise.
    """
    domain_data = hass.data.get(state.domain)
    if domain_data is None:
        return None
    entity = domain_data.get_entity(state.entity_id)
    if entity is None or entity.registry_entry is None:
        return None
    return entity


def get_entity_area_id(
    hass: HomeAssistant,
    entity: Any,
    dr_reg: dr.DeviceRegistry | None = None,
) -> str | None:
    """Get area ID from entity or its parent device.

    First checks the entity's direct area assignment, then falls back
    to the device's area if the entity doesn't have one.
    """
    if dr_reg is None:
        dr_reg = dr.async_get(hass)

    area_id = entity.registry_entry.area_id
    if area_id is None and entity.registry_entry.device_id:
        device = dr_reg.async_get(entity.registry_entry.device_id)
        if device is not None:
            area_id = device.area_id
    return area_id


def is_beoplay_media_player(entity: Any) -> bool:
    """Check if entity is a beoplay media player.

    Only beoplay media players are supported by the BeoLink integration.
    """
    return (
        hasattr(entity, "platform")
        and hasattr(entity.platform, "platform_name")
        and entity.platform.platform_name == "beoplay"
    )

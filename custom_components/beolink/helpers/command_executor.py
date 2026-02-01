"""Command execution utilities for BeoLink integration."""

import logging

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.cover import ATTR_POSITION, DOMAIN as COVER_DOMAIN
from homeassistant.components.light import (
    ATTR_BRIGHTNESS_PCT,
    ATTR_HS_COLOR,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant

from .scene_helpers import find_scene_by_name
from .state_helpers import map_beolink_mode_to_hvac

_LOGGER = logging.getLogger(__name__)


class CommandExecutor:
    """Executes BeoLink commands on Home Assistant entities."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the command executor."""
        self.hass = hass

    async def execute_shade_command(
        self,
        entity_id: str,
        command: str,
        params: dict,
    ) -> None:
        """Execute shade (cover) commands.

        Supported commands: RAISE, LOWER, STOP, SET
        """
        service = None
        service_data: dict = {ATTR_ENTITY_ID: entity_id}

        if command == "RAISE":
            service = SERVICE_OPEN_COVER
        elif command == "LOWER":
            service = SERVICE_CLOSE_COVER
        elif command == "STOP":
            service = SERVICE_STOP_COVER
        elif command == "SET":
            service = SERVICE_SET_COVER_POSITION
            level = params.get("LEVEL")
            if level:
                service_data[ATTR_POSITION] = int(level)
            else:
                _LOGGER.warning("Missing LEVEL parameter in shade SET command")
                return

        if service:
            await self.hass.services.async_call(COVER_DOMAIN, service, service_data)

    async def execute_dimmer_command(
        self,
        entity_id: str,
        command: str,
        params: dict,
    ) -> None:
        """Execute dimmer (light) commands.

        Supported commands: SET, SET COLOR
        """
        service_data: dict = {ATTR_ENTITY_ID: entity_id}

        if command == "SET":
            level = params.get("LEVEL")
            if level:
                service_data[ATTR_BRIGHTNESS_PCT] = int(level)
        elif command == "SET COLOR":
            # Handle HSV color format: hsv(hue,saturation,value)
            color_value = params.get("LEVEL", "")
            if color_value.startswith("hsv(") and color_value.endswith(")"):
                hsv_parts = color_value[4:-1].split(",")
                if len(hsv_parts) >= 3:
                    hue = float(hsv_parts[0])
                    saturation = float(hsv_parts[1])
                    brightness = float(hsv_parts[2])
                    service_data[ATTR_HS_COLOR] = (hue, saturation)
                    service_data[ATTR_BRIGHTNESS_PCT] = int(brightness)

        await self.hass.services.async_call(LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)

    async def execute_thermostat_command(
        self,
        entity_id: str,
        command: str,
        params: dict,
    ) -> None:
        """Execute thermostat (climate) commands.

        Supported commands: SET SETPOINT, SET MODE
        """
        service_data: dict = {ATTR_ENTITY_ID: entity_id}

        if command == "SET SETPOINT":
            value = params.get("VALUE")
            if value:
                service_data[ATTR_TEMPERATURE] = float(value)
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, service_data
                )
        elif command == "SET MODE":
            value = params.get("VALUE")
            if value:
                hvac_mode = map_beolink_mode_to_hvac(value)
                service_data[ATTR_HVAC_MODE] = hvac_mode
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, service_data
                )

    async def execute_scene_command(
        self,
        scene_name: str,
        command: str,
    ) -> None:
        """Execute scene (macro) commands.

        Macros in BeoLink map to Home Assistant scenes.
        Supported commands: FIRE
        """
        if command != "FIRE":
            _LOGGER.warning("Unsupported macro command: %s", command)
            return

        # Find the scene by its friendly name
        scene_state = find_scene_by_name(self.hass, scene_name)
        if scene_state:
            _LOGGER.debug(
                "Firing scene %s (entity: %s)", scene_name, scene_state.entity_id
            )
            await self.hass.services.async_call(
                SCENE_DOMAIN,
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: scene_state.entity_id},
            )
        else:
            _LOGGER.warning("Scene not found for macro: %s", scene_name)

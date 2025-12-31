"""Module for returning data formatted in json."""
import json
import logging

from aiohttp import MultipartWriter, web
from aiohttp.client_exceptions import ClientConnectionResetError
from aiohttp_basicauth import BasicAuthMiddleware
import jsonpickle

from homeassistant import core
from homeassistant.auth.providers.homeassistant import (
    AuthProvider,
    HassAuthProvider,
    InvalidAuth,
)
from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_DOMAIN
from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN, async_get_image
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN, CoverEntityFeature
from homeassistant.components.light import (
    ATTR_SUPPORTED_COLOR_MODES,
    DOMAIN as LIGHT_DOMAIN,
    color_supported,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar, device_registry as dr

from .const import MODE_EXCLUDE, MODE_INCLUDE
from .model.blgwpwebservices import Area, Zone, blgwpwebservices

_LOGGER = logging.getLogger(__name__)

class CustomBasicAuth(BasicAuthMiddleware):
    """Class for handlig authentication against Home Assistant users."""

    def __init__(self, providers: list[AuthProvider]) -> None:
        """Init CustomBasicAuth."""
        self.providers = providers
        super().__init__()

    async def check_credentials(self, username: str, password: str, request: web.Request) -> bool:
        """Check ip / credentials against Home Assistant."""
        for provider in self.providers:
            if isinstance (provider, HassAuthProvider):
                try:
                    await provider.async_validate_login(username, password) # type: ignore[attr-defined]
                except InvalidAuth:
                    return False
                return True
        return False


class BLGWServer:
    """Handles BLGW HTTP requests."""

    def __init__(self, name: str, serial_number: str, include_entities: list[str], exclude_entities: list[str], include_exclude_mode: str, hass: core.HomeAssistant) -> None:
        """Init BLGWServer."""
        self.name = name
        self.serial_number = serial_number
        self.include_entities = include_entities
        self.exclude_entities = exclude_entities
        self.include_exclude_mode = include_exclude_mode
        self.hass = hass

    def _should_include_entity(self, entity_id: str) -> bool:
        """Check if entity should be included based on include/exclude mode."""
        if self.include_exclude_mode == MODE_INCLUDE and entity_id not in self.include_entities:
            return False
        if self.include_exclude_mode == MODE_EXCLUDE and entity_id in self.exclude_entities:
            return False
        return True

    def _create_cover_resource(self, state, entity) -> dict[str, object]:
        """Create a cover/shade resource."""
        commands = ["LOWER", "RAISE", "STOP"]
        states = []
        if (
            state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            & CoverEntityFeature.SET_POSITION
        ):
            commands.append("SET")
            states.append("LEVEL")
        return {
            "type": "SHADE",
            "name": state.name,
            "id": entity.entity_id,
            "systemAddress": "HomeAssistant",
            "hide": False,
            "commands": commands,
            "states": states,
            "events": [],
        }

    def _create_light_resource(self, state, entity) -> dict[str, object]:
        """Create a light/dimmer resource."""
        dimmer = {
            "type": "DIMMER",
            "name": state.name,
            "id": entity.entity_id,
            "systemAddress": "HomeAssistant",
            "hide": False,
            "commands": ["SET"],
            "states": ["LEVEL"],
        }
        color_modes = (state.attributes.get(ATTR_SUPPORTED_COLOR_MODES) or [])
        if color_supported(color_modes):
            dimmer['commands'].append("SET COLOR")
            dimmer['states'].append("COLOR")
        return dimmer

    def _create_camera_resource(self, state, entity) -> dict[str, object]:
        """Create a camera resource."""
        return {
            "type": "CAMERA",
            "name": state.name,
            "rtspSupport": False,
            "commands": [],
        }

    def _create_climate_resource(self, state, entity) -> dict[str, object]:
        """Create a climate/thermostat resource."""
        return {
            "type": "THERMOSTAT_1SP",
            "name": state.name,
            "id": entity.entity_id,
            "systemAddress": "HomeAssistant",
            "hide": False,
            "commands": ["SET SETPOINT", "SET MODE", "SET FAN AUTO"],
            "states": [
                "TEMPERATURE",
                "SETPOINT",
                "MODE",
                "FAN AUTO",
                "VALUE",
            ],
            "events": ["STATE_UPDATE"],
        }

    def _create_alarm_resource(self, state, entity) -> dict[str, object]:
        """Create an alarm resource."""
        return {
            "type": "ALARM",
            "name": state.name,
            "id": entity.entity_id,
            "systemAddress": "HomeAssistant",
            "hide": False,
            "commands": ["ARM", "DISARM"],
            "states": ["ALARM", "MODE", "READY"],
            "events": [],
        }

    async def _create_media_player_resource(self, state, entity) -> dict[str, object]:
        """Create a media player resource."""
        # Extract serial number from unique_id (format: "beoplay-{serial}-media_player")
        serial_number = "unknown"
        if hasattr(entity, 'unique_id') and entity.unique_id:
            parts = entity.unique_id.split('-')
            if len(parts) >= 2:
                serial_number = parts[1]

        # Get sources using public API if available
        bl_sources = []
        if hasattr(entity, '_speaker') and hasattr(entity._speaker, 'async_getReq'):
            try:
                sources = await entity._speaker.async_getReq("BeoZone/Zone/Sources")
                if sources:
                    for source in sources.get('sources', []):
                        if 1 in source and "id" in source[1]:
                            bl_source = {
                                "name": source[1]["friendlyName"],
                                "uiType": "0.2",
                                "code": "HDMI",
                                "format": "F0",
                                "networkBit": False,
                                "select": {
                                    "cmds": [
                                        "Select source by id?"+source[1]["id"]
                                    ]
                                },
                                "sourceId": source[1]["id"],
                                "sourceType": source[1]["sourceType"]["type"],
                                "profiles": "",
                            }
                            bl_sources.append(bl_source)
            except Exception as err:
                error_text = f"Problems handling sources for entity: {entity.name}. Sources error: {err}"
                _LOGGER.exception(error_text)

        return {
            "type": "AV renderer",
            "name": state.name,
            "id": entity.entity_id,
            "systemAddress": "HomeAssistant",
            "hide": False,
            "commands": [
                "All standby",
                "Beo4 advanced command",
                "Beo4 command",
                "BeoRemote One Source Selection",
                "BeoRemote One command",
                "Channel selection",
                "Cinema mode",
                "Master volume adjust",
                "Master volume level",
                "Picture Mute",
                "Picture mode",
                "Playqueue add Deezer playlist",
                "Playqueue add TuneIn station",
                "Playqueue add URL",
                "Playqueue clean",
                "Recall profile",
                "Save profile",
                "Select channel",
                "Select source",
                "Select source by id",
                "Send command",
                "Send digit",
                "Sound mode",
                "Speaker group",
                "Stand position",
                "Standby",
                "Volume adjust",
                "Volume level",
            ],
            "events": ["All standby", "Control", "Light"],
            "states": [
                "nowPlaying",
                "nowPlayingDetails",
                "online",
                "sourceName",
                "sourceUniqueId",
                "state",
                "volume",
            ],
            "Beo4NavButton": True,
            "sn": serial_number,
            "sources": bl_sources,
            "playQueueCapabilities": "deezer,dlna",
            "integratedRole": "none",
            "integratedSN": "",
        }

    async def camera_mjpeg(self, request: web.Request) -> web.StreamResponse:
        """Handle a mjpeg stream."""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=beolink-camera-stream",
            },
        )
        await response.prepare(request)
        states = self.hass.states.async_all()
        camera_state = next(
            x
            for x in states
            if x.attributes.get("friendly_name") == request.match_info["camera_name"]
        )

        while True:
            try:
                image = await async_get_image(self.hass, camera_state.entity_id)
                with MultipartWriter("image/jpeg", boundary="beolink-camera-stream") as mpwriter:
                    mpwriter.append(image.content, {"Content-Type": image.content_type})
                    await mpwriter.write(response, close_boundary=False)
                await response.drain()
            except ClientConnectionResetError:
                # Client disconnected, exit gracefully
                logging.getLogger(__name__).debug(
                    "Client disconnected from camera stream: %s",
                    camera_state.entity_id,
                )
                break
            except HomeAssistantError as err:
                logging.getLogger(__name__).error(
                    "Error fetching camera image for %s: %s",
                    camera_state.entity_id,
                    err,
                )
                break
        return response

    async def blgwpservices(self, request: web.Request) -> web.Response:
        """Handle the blgwpservices.json request."""
        dr_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        bl_areas: dict[str, Area] = {}
        bl_zones: dict[str, Zone] = {}
        bl_ressources: dict[str, dict[str, dict[str, object]]] = {}

        states = self.hass.states.async_all()
        for state in states:
            if state.domain not in {
                COVER_DOMAIN,
                LIGHT_DOMAIN,
                CAMERA_DOMAIN,
                CLIMATE_DOMAIN,
                ALARM_DOMAIN,
                MEDIA_PLAYER_DOMAIN,
            }:
                continue

            if not self._should_include_entity(state.entity_id):
                continue

            domain = self.hass.data.get(state.domain)
            if domain is None:
                continue
            entity = domain.get_entity(state.entity_id)
            if entity is None or entity.registry_entry is None:
                continue
            if state.name is None:
                _LOGGER.info("Entity %s has no entity name", entity.entity_id)
                continue
            if "?" in state.name or "/" in state.name:
                _LOGGER.info("Entity %s contains illegal character (? or /) for BeoLink usage", state.name)
                continue

            area_id = entity.registry_entry.area_id
            if area_id is None:
                device = dr_reg.async_get(entity.registry_entry.device_id)
                if device is None:
                    continue
                area_id = device.area_id
                if area_id is None:
                    continue

            if area_id not in bl_zones:
                area = area_reg.async_get_area(area_id)
                if area is None:
                    continue
                bl_zones[area_id] = Zone(area.name, "house", False, False, {})
                bl_ressources[area_id] = {}

            resource = None
            if state.domain == COVER_DOMAIN:
                resource = self._create_cover_resource(state, entity)
            elif state.domain == LIGHT_DOMAIN:
                resource = self._create_light_resource(state, entity)
            elif state.domain == CAMERA_DOMAIN:
                resource = self._create_camera_resource(state, entity)
            elif state.domain == CLIMATE_DOMAIN:
                resource = self._create_climate_resource(state, entity)
            elif state.domain == ALARM_DOMAIN:
                resource = self._create_alarm_resource(state, entity)
            elif state.domain == MEDIA_PLAYER_DOMAIN and entity.platform.platform_name == "beoplay":
                resource = await self._create_media_player_resource(state, entity)

            if resource:
                bl_ressources[area_id][state.entity_id] = resource

        for bl_zone_key, bl_zone in bl_zones.items():
            sorted_resources = list(bl_ressources[bl_zone_key].values())
            sorted_resources.sort(key=lambda x: str(x.get("name", "")))
            bl_zone.resources = sorted_resources

        sorted_zones = list(bl_zones.values())
        sorted_zones.sort(key=lambda x: x.name)
        house_area = Area("House", sorted_zones)
        house_area.zones = sorted_zones
        bl_areas["House"] = house_area

        main_zone = Zone("global", "house", True, False, [])
        main_area = Area("Main", [main_zone])
        bl_areas["main"] = main_area

        data = blgwpwebservices(self.name, self.serial_number, list(bl_areas.values()))

        return web.Response(body=jsonpickle.encode(data, unpicklable=False))

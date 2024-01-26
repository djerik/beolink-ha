"""Module for returning data formatted in json."""
import ipaddress
import json
import logging

from aiohttp import MultipartWriter, web
from aiohttp_basicauth import BasicAuthMiddleware
import jsonpickle

from .const import MODE_EXCLUDE, MODE_INCLUDE
from homeassistant import core
from homeassistant.auth import InvalidAuthError
from homeassistant.auth.providers.homeassistant import (
    AuthProvider,
    HassAuthProvider,
    InvalidAuth,
)
from homeassistant.auth.providers.trusted_networks import TrustedNetworksAuthProvider
from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_DOMAIN
from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN, CoverEntityFeature
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.helpers import area_registry as ar, device_registry as dr

from .model.blgwpwebservices import Area, Zone, blgwpwebservices

_LOGGER = logging.getLogger(__name__)

class CustomBasicAuth(BasicAuthMiddleware):
    """Class for handlig authentication against Home Assistant users."""

    def __init__(self, providers: list[AuthProvider]) -> None:
        """Init CustomBasicAuth."""
        self.providers = providers
        super().__init__()

    async def check_credentials(self, username, password, request):
        """Check ip / credentials against Home Assistant."""
        for provider in self.providers:
            if isinstance (provider, TrustedNetworksAuthProvider):
                ip = ipaddress.ip_address(request.remote)
                try:
                    provider.async_validate_access(ip)
                except InvalidAuthError:
                    return False
                return True
            elif isinstance (provider, HassAuthProvider):
                try:
                    await provider.async_validate_login(username, password)
                except InvalidAuth:
                    return False
                return True
        return False


class BLGWServer:
    """Handles BLGW HTTP requests."""

    def __init__(self, name : str, serial_number : str, include_entities, exclude_entities, include_exclude_mode : str,  hass: core.HomeAssistant) -> None:
        """Init BLGWServer."""
        self.name = name
        self.serial_number = serial_number
        self.include_entities = include_entities
        self.exclude_entities = exclude_entities
        self.include_exclude_mode = include_exclude_mode
        self.hass = hass

    async def camera_mjpeg(self, request):
        """Handle a mjpeg stream."""
        boundary = "myboundary"
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "multipart/x-mixed-replace; " "boundary=%s" % boundary,
            },
        )
        await response.prepare(request)
        states = self.hass.states.async_all()
        camera_state = next(
            x
            for x in states
            if x.attributes["friendly_name"] == request.match_info["camera_name"]
        )
        camera = self.hass.data["camera"].get_entity(camera_state.entity_id)

        while True:
            image_cb = await camera.async_camera_image()
            with MultipartWriter("image/jpeg", boundary=boundary) as mpwriter:
                mpwriter.append(image_cb, {"Content-Type": "image/jpeg"})
                await mpwriter.write(response, close_boundary=False)
            await response.drain()

    async def blgwpservices(self, request):
        """Handle the blgwpservices.json request."""
        dr_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        bl_areas: dict[str, Area] = {}
        bl_zones: dict[str, Zone] = {}
        bl_ressources: dict[str, dict[str, object]] = {}

        states = self.hass.states.async_all()
        for state in states:
            if state.domain in {
                COVER_DOMAIN,
                LIGHT_DOMAIN,
                CAMERA_DOMAIN,
                CLIMATE_DOMAIN,
                ALARM_DOMAIN,
                MEDIA_PLAYER_DOMAIN,
            }:
                if( self.include_exclude_mode == MODE_INCLUDE and state.entity_id not in self.include_entities ):
                    continue
                if( self.include_exclude_mode == MODE_EXCLUDE and state.entity_id in self.exclude_entities ):
                    continue
                domain = self.hass.data.get(state.domain)
                if( domain is None):
                    continue
                entity = domain.get_entity(state.entity_id)
                if entity is None or entity.registry_entry is None:
                    continue
                if state.name is None:
                    message = f"Entity {entity.entity_id} has no entity name"
                    _LOGGER.info( message )
                    continue
                if "?" in state.name or "/" in state.name:
                    message = f"Entity {state.name} contains illegal character (? or /) for BeoLink usage"
                    _LOGGER.info( message )
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
                if state.domain == COVER_DOMAIN:
                    commands = ["LOWER", "RAISE", "STOP"]
                    states = []
                    if (
                        state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
                        & CoverEntityFeature.SET_POSITION
                    ):
                        commands.append("SET")
                        states.append("LEVEL")
                    shade = {
                        "type": "SHADE",
                        "name": state.name,
                        "id": entity.entity_id,
                        "systemAddress": "HomeAssistant",
                        "hide": False,
                        "commands": commands,
                        "states": states,
                        "events": [],
                    }
                    bl_ressources[area_id][state.entity_id] = shade
                if state.domain == LIGHT_DOMAIN:
                    dimmer = {
                        "type": "DIMMER",
                        "name": state.name,
                        "id": entity.entity_id,
                        "systemAddress": "HomeAssistant",
                        "hide": False,
                        "commands": ["SET"],
                        "states": ["LEVEL"],
                    }
                    if( entity.supported_color_modes is not None ):
                        dimmer['commands'].append("SET COLOR")
                        dimmer['states'].append("COLOR")
                    bl_ressources[area_id][state.entity_id] = dimmer
                if state.domain == CAMERA_DOMAIN:
                    camera = {
                        "type": "CAMERA",
                        "name": state.name,
                        "rtspSupport": False,
                        "commands": [],
                    }
                    bl_ressources[area_id][state.entity_id] = camera
                if state.domain == "climate":
                    thermostate = {
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
                    bl_ressources[area_id][state.entity_id] = thermostate
                if state.domain == ALARM_DOMAIN:
                    alarm = {
                        "type": "ALARM",
                        "name": state.name,
                        "id": entity.entity_id,
                        "systemAddress": "HomeAssistant",
                        "hide": False,
                        "commands": ["ARM", "DISARM"],
                        "states": ["ALARM", "MODE", "READY"],
                        "events": [],
                    }
                    bl_ressources[area_id][state.entity_id] = alarm
                if state.domain == MEDIA_PLAYER_DOMAIN and entity.platform.platform_name == "beoplay":
                    sources = await entity._speaker.async_getReq("BeoZone/Zone/Sources")
                    bl_sources = []
                    if sources:
                        try:
                            for source in sources['sources']:
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
                            error_text = f"Problems handling sources for entity: {entity.name}. Sources: {json.dumps(sources)}. Error: {err}"
                            _LOGGER.exception(error_text)
                    media_player = {
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
                        "sn": entity._serial_number,
                        "sources": bl_sources,
                        "playQueueCapabilities": "deezer,dlna",
                        "integratedRole": "none",
                        "integratedSN": "",
                    }
                    bl_ressources[area_id][state.entity_id] = media_player

        for bl_zone_key, bl_zone in bl_zones.items():
            sorted_resources = list(bl_ressources[bl_zone_key].values())
            sorted_resources.sort(key=lambda x: x.get("name"))
            bl_zone.resources = sorted_resources

        house_area = Area("House")
        sorted_zones = list(bl_zones.values())
        sorted_zones.sort(key=lambda x: x.name)
        house_area.zones = sorted_zones
        bl_areas["House"] = house_area

        main_zone = Zone("global", "house", True, False, [])
        main_area = Area("Main")
        main_area.zones = {main_zone}
        bl_areas["main"] = main_area

        data = blgwpwebservices(self.name, self.serial_number, list(bl_areas.values()))

        return web.Response(body=jsonpickle.encode(data, unpicklable=False))

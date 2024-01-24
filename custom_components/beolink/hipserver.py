"""Module for handling the tcp communication."""
import asyncio
import ipaddress
import logging
from typing import Any
from urllib.parse import parse_qs, quote, unquote

from homeassistant import core
from homeassistant.auth import InvalidAuthError
from homeassistant.auth.providers.homeassistant import HassAuthProvider, InvalidAuth
from homeassistant.auth.providers.trusted_networks import TrustedNetworksAuthProvider
from homeassistant.components.alarm_control_panel import (
    DOMAIN as ALARM_DOMAIN,
    SERVICE_ALARM_ARM_AWAY,
    SERVICE_ALARM_ARM_HOME,
    SERVICE_ALARM_DISARM,
)
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    CoverEntityFeature,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS_PCT,
    ATTR_HS_COLOR,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.components.remote import (
    DOMAIN as REMOTE_DOMAIN,
    SERVICE_SEND_COMMAND,
)
from homeassistant.const import (
    ATTR_CODE,
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_TRIGGERED,
    STATE_PLAYING,
)
from homeassistant.core import CALLBACK_TYPE, Context, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.typing import EventType

from .const import MODE_EXCLUDE, MODE_INCLUDE

REMOTE_MAPPING = { "BACK" : "Cursor/Back",
                "CURSOR_LEFT" : "Cursor/Left",
                "CURSOR_RIGHT" : "Cursor/Right",
                "CURSOR_UP" : "Cursor/Up",
                "CURSOR_DW" : "Cursor/Down",
                "EXIT" : "Cursor/Exit",
                "SELECT_Cursor_SELECT" : "Cursor/Select",
                "MENU" : "Menu/Root",
                "PAUSE" : "Stream/Pause",
                "PLAY" : "Stream/Play",
                "STOP" : "Stream/Stop",
                "RECORD" : "Record/Record",
                "REWIND" : "Stream/Rewind",
                "WIND" : "Stream/Forward"
                }

_LOGGER = logging.getLogger(__name__)

class HIPRessource:
    """Representation of af HIP Ressource."""

    def __init__(self, domain, entity, entity_name, area_name, features) -> None:
        """Init HIPRessource."""
        self.domain = domain
        self.entity = entity
        self.entity_id = entity.entity_id
        self.entity_name = entity_name
        self.area_name = area_name
        self.features = features
        if self.domain == CLIMATE_DOMAIN:
            self.hip_type = "THERMOSTAT_1SP"
        elif self.domain == LIGHT_DOMAIN:
            self.hip_type = "DIMMER"
        elif self.domain == COVER_DOMAIN:
            self.hip_type = "SHADE"
        elif self.domain == ALARM_DOMAIN:
            self.hip_type = "ALARM"
        elif self.domain == MEDIA_PLAYER_DOMAIN:
            self.hip_type = "AV renderer"
            self.product_id = None
            if entity.platform.platform_name == "beoplay":
                self.product_id = entity._type_number + "."+ entity._item_number+ "." + entity._serial_number + "@products.bang-olufsen.com"

        self.path = "House/" + quote(self.area_name, safe='') + "/" + quote(self.hip_type,  safe='') + "/" + quote(self.entity_name, safe='') + "/"
        self.state_path = self.path + "STATE_UPDATE?"

    def state_updates(self, state, attributes : dict) -> list:
        """Generate state update."""
        states = []
        if self.domain == COVER_DOMAIN:
            if self.features & CoverEntityFeature.SET_POSITION:
                states.append(
                    self.state_path + "LEVEL=" + str(attributes[ATTR_CURRENT_POSITION])
                )
        elif self.domain == CLIMATE_DOMAIN:
            states.append(
                self.state_path
                + "TEMPERATURE="
                + str(round(attributes["current_temperature_air"]))
            )
            states.append(
                self.state_path + "SETPOINT=" + str(round(attributes[ATTR_TEMPERATURE]))
            )
            states.append(self.state_path + "MODE=Auto")
            states.append(self.state_path + "FAN AUTO=true")
        elif self.domain == LIGHT_DOMAIN:
            if ATTR_BRIGHTNESS_PCT in attributes:
                states.append(
                    self.state_path + "LEVEL=" + str(attributes[ATTR_BRIGHTNESS_PCT])
                )
            else:
                states.append(self.state_path + "LEVEL=0")
            if ATTR_HS_COLOR in attributes:
                try:
                    states[0] = (
                        states[0]
                        + "&COLOR=hsv("
                        + str(round(attributes[ATTR_HS_COLOR][0]))
                        + ","
                        + str(round(attributes[ATTR_HS_COLOR][1]))
                        + ","
                        #+ str(attributes[ATTR_BRIGHTNESS_PCT])
                        + "100"
                        + ")"
                    )
                except TypeError:
                    error_text = f"Problems handling color for state: {state.name} - HS Color Attributes: {attributes[ATTR_HS_COLOR]}"
                    _LOGGER.Exception( error_text)
        elif self.domain == ALARM_DOMAIN:
            if state.state == STATE_ALARM_ARMED_HOME:
                states.append(self.state_path + "ALARM=0&READY=1&MODE=ARM")
            elif state.state == STATE_ALARM_ARMED_AWAY:
                states.append(self.state_path + "ALARM=0&READY=1&MODE=ARM")
            elif state.state == STATE_ALARM_TRIGGERED:
                states.append(self.state_path + "ALARM=1&READY=1&MODE=ARM")
            else:
                states.append(self.state_path + "ALARM=0&READY=1&MODE=DISARM")
        elif self.domain == MEDIA_PLAYER_DOMAIN:
            temp = "nowPlaying="
            temp += "&nowPlayingDetails="
            temp += "&online=" + "Yes"
            temp += "&sourceName=" + attributes.get(ATTR_INPUT_SOURCE, "")
            temp += "&sourceUniqueId=" + attributes.get(ATTR_INPUT_SOURCE, "")
            if( self.product_id):
                temp += ":"+self.product_id
            m_p_state = ""
            if state.state == STATE_PLAYING:
                m_p_state = "Play"
            temp += "&state=" + m_p_state
            temp += "&volume=" + str(int(attributes.get(ATTR_MEDIA_VOLUME_LEVEL, 0)*100))
            states.append( temp )

        return states


class HIPServer(asyncio.Protocol):
    """Server handling the HIP protocol."""

    state = "awaiting user"

    def __init__(self, include_entities : str, exclude_entities : str, include_exclude_mode : str, hass: core.HomeAssistant) -> None:
        """Init HIPServer."""

        self.include_entities = include_entities
        self.exclude_entities = exclude_entities
        self.include_exclude_mode = include_exclude_mode
        self.hass = hass
        self.providers = self.hass.auth.auth_providers
        self.user = ""
        self.transport = None
        self.buffer = ""
        self._subscriptions: list[CALLBACK_TYPE] = []
        self.hip_ressources_by_entity_id = {}
        self.hip_ressources_by_entity_name = {}

    def handle_resource_state_data(self, entity_id, state, data):
        """Handle states data to HIP events."""
        state_updates = self.hip_ressources_by_entity_id[entity_id].state_updates(
            state, data
        )
        for state in state_updates:
            self.send_state_line(state)

    @callback
    def _async_update_event_state_callback(
        self, event: EventType[EventStateChangedData]
    ) -> None:
        """Receives event changes from HA."""
        new_state = event.data["new_state"]
        self.handle_resource_state_data(
            event.data["entity_id"], new_state, new_state.attributes
        )

    def connection_made(self, transport):
        """Client connnected."""
        self.transport = transport
        self.send(b"login: ")

    def connection_lost(self, exc):
        """Unsubscribe listeners when clients disconnects."""
        while len(self._subscriptions) > 0:
            self._subscriptions.pop()()

    async def check_login(self, username, password):
        """Check ip / credentials against Home Assistant."""
        for provider in self.providers:
            if isinstance (provider, TrustedNetworksAuthProvider):
                ip = ipaddress.ip_address(self.transport.get_extra_info('peername')[0])
                try:
                    provider.async_validate_access(ip)
                except InvalidAuthError:
                    return False
                self.state = "authenticated"
                self.send(b"\r\n")
                return True
            elif isinstance (provider, HassAuthProvider):
                try:
                    await provider.async_validate_login(username, password)
                except InvalidAuth:
                    return False
                self.state = "authenticated"
                self.send(b"\r\n")
                return True
        return False

    def data_received(self, data):
        """Received data from BeoLiving app."""
        self.buffer += data.decode()
        lines = self.buffer.splitlines(True)
        for line in lines:
            if not line.endswith("\r\n"):
                self.buffer = line
                continue
            self.buffer = self.buffer.removeprefix(line)
            _LOGGER.debug("Received: %s", line)
            line = line.removesuffix("\r\n")
            if self.state == "awaiting user":
                self.user = line
                self.state = "awaiting password"
                self.send(b"\r\npassword: ")
            elif self.state == "awaiting password":
                self.hass.loop.create_task(self.check_login(self.user, line))
            else:
                if line == "f":
                    self.send_ok_line("f")
                if line in ("q */*/*/*", "q"):
                    self.send_ok_line("q */*/*/*")
                    states = self.hass.states.async_all()

                    dr_reg = dr.async_get(self.hass)
                    area_reg = ar.async_get(self.hass)
                    for state in states:
                        if state.domain in {
                            COVER_DOMAIN,
                            LIGHT_DOMAIN,
                            CLIMATE_DOMAIN,
                            ALARM_DOMAIN,
                            MEDIA_PLAYER_DOMAIN,
                        }:
                            if( self.include_exclude_mode == MODE_INCLUDE and state.entity_id not in self.include_entities ):
                                continue
                            if( self.include_exclude_mode == MODE_EXCLUDE and state.entity_id in self.exclude_entities ):
                                continue
                            if "?" in state.name or "/" in state.name:
                                message = f"Entity {state.name} contains illegal character (? or /) for BeoLink usage"
                                _LOGGER.info( message )
                                continue
                            domain = self.hass.data.get(state.domain)
                            if( domain is None):
                                continue
                            entity = domain.get_entity(
                                state.entity_id
                            )
                            if entity is None or entity.registry_entry is None:
                                continue
                            area_id = entity.registry_entry.area_id
                            if area_id is None:
                                device = dr_reg.async_get(
                                    entity.registry_entry.device_id
                                )
                                if device is None:
                                    continue
                                area_id = device.area_id
                                if area_id is None:
                                    continue
                            area = area_reg.async_get_area(area_id)
                            if area is None:
                                continue
                            ressource = HIPRessource(
                                state.domain,
                                entity,
                                state.name,
                                area.name,
                                state.attributes.get(ATTR_SUPPORTED_FEATURES, 0),
                            )
                            self.hip_ressources_by_entity_id[
                                state.entity_id
                            ] = ressource
                            self.hip_ressources_by_entity_name[state.name] = ressource
                            self._subscriptions.append(
                                async_track_state_change_event(
                                    self.hass,
                                    [state.entity_id],
                                    self._async_update_event_state_callback,
                                )
                            )
                            self.handle_resource_state_data(
                                state.entity_id, state, state.attributes
                            )

                if line == "f */*/*/*":
                    self.send_ok_line("f */*/*/*")
                if line == "c Main/global/SYSTEM/BLI/CHECK%20FIRMWARE":
                    self.send_ok_line("c Main/global/SYSTEM/BLI/CHECK FIRMWARE")
                    self.send_response_line(
                        "Main/global/SYSTEM/BLGW/STATE_UPDATE?CURRENT%20FIRMWARE=1.5.4.557&LATEST%20FIRMWARE=&ROLLBACK%20AVAILABLE=1.5.4.533_2023.01.31-22.01.55&SYSTEM%20INFO=READY&revision=39"
                    )
                elif line.startswith("c "):
                    command = unquote(line).split("/")
                    action = command[4]
                    entity_name = command[3]
                    ressource_type = command[2]
                    hip_ressource = self.hip_ressources_by_entity_name[entity_name]
                    params = {ATTR_ENTITY_ID: hip_ressource.entity_id}
                    if ressource_type == "SHADE":
                        if action == "RAISE":
                            service = SERVICE_OPEN_COVER
                        elif action == "LOWER":
                            service = SERVICE_CLOSE_COVER
                        elif action == "STOP":
                            service = SERVICE_STOP_COVER
                        elif action.startswith("SET"):
                            service = SERVICE_SET_COVER_POSITION
                            qs = str(action).split("?")[1]
                            parameters = parse_qs(qs)
                            params[ATTR_POSITION] = parameters["LEVEL"][0]
                        self.async_call_service(
                            hip_ressource.entity_id,
                            hip_ressource.entity_name,
                            COVER_DOMAIN,
                            service,
                            params,
                        )
                    elif ressource_type == "DIMMER":
                        parameters = str(action).split("?")
                        parameter = parameters[0]
                        value = parameters[1].split("=")[1]
                        if parameter == "SET":
                            params[ATTR_BRIGHTNESS_PCT] = value
                        if parameter == "SET COLOR":
                            hsv = value.split(",")
                            hue = hsv[0][4:]
                            saturation = hsv[1]
                            hue_sat = (
                                hue,
                                saturation,
                            )
                            params[ATTR_HS_COLOR] = hue_sat
                            if hsv[2][:-1] == "":
                                params[ATTR_BRIGHTNESS_PCT] = 0
                            else:
                                params[ATTR_BRIGHTNESS_PCT] = hsv[2][:-1]
                        self.async_call_service(
                            hip_ressource.entity_id,
                            hip_ressource.entity_name,
                            LIGHT_DOMAIN,
                            SERVICE_TURN_ON,
                            params,
                        )
                    elif ressource_type == "THERMOSTAT_1SP":
                        qs = str(action).split("?")[1]
                        parameters = parse_qs(qs)
                        params[ATTR_TEMPERATURE] = parameters["VALUE"][0]
                        if parameter == "SET SETPOINT":
                            self.async_call_service(
                                hip_ressource.entity_id,
                                hip_ressource.entity_name,
                                CLIMATE_DOMAIN,
                                SERVICE_SET_TEMPERATURE,
                                params,
                            )
                    elif ressource_type == "ALARM":
                        qs = str(action).split("?")[1]
                        parameters = parse_qs(qs)
                        if action.startswith("DISARM"):
                            service = SERVICE_ALARM_DISARM
                            params[ATTR_CODE] = parameters["CODE"][0]
                        elif action.startswith("ARM"):
                            mode = parameters["MODE"][0]
                            if mode == "HOME":
                                service = SERVICE_ALARM_ARM_HOME
                            elif mode == "AWAY":
                                service = SERVICE_ALARM_ARM_AWAY
                        self.async_call_service(
                            hip_ressource.entity_id,
                            hip_ressource.entity_name,
                            ALARM_DOMAIN,
                            service,
                            params,
                        )
                    elif ressource_type == "AV renderer":
                        if( "?" in str(action)):
                            qs = str(action).split("?")[1]
                            parameters = parse_qs(qs)
                        entity = self.hass.data[MEDIA_PLAYER_DOMAIN].get_entity(hip_ressource.entity_id)
                        service = None
                        if action == "Standby":
                            service = SERVICE_TURN_OFF
                        if action.startswith("Select source by id"):
                            entity.select_source(parameters["sourceUniqueId"][0])
                        if action.startswith("Volume level"):
                            service = SERVICE_VOLUME_SET
                            params[ATTR_MEDIA_VOLUME_LEVEL] = float(parameters["Level"][0])/100
                        if action.startswith("Volume adjust"):
                            if(parameters["Command"][0] == "Mute"):
                                service = SERVICE_VOLUME_MUTE
                                params[ATTR_MEDIA_VOLUME_MUTED] = not entity.is_volume_muted
                        if service is not None:
                            self.async_call_service(
                                hip_ressource.entity_id,
                                hip_ressource.entity_name,
                                MEDIA_PLAYER_DOMAIN,
                                service,
                                params,
                            )
                        if action.startswith("Send command") or action.startswith("Beo4 advanced command"):
                            service = SERVICE_SEND_COMMAND
                            params = {ATTR_ENTITY_ID: "remote.beovision_eclipse"}
                            params["command"] = REMOTE_MAPPING[parameters["Command"][0]]
                            self.async_call_service(
                                "remote.beovision_eclipse",
                                "Beovision Eclipse",
                                REMOTE_DOMAIN,
                                service,
                                params,
                            )
                    self.send_ok_line("c ")

    def send(self, data):
        """Low level send method."""
        self.transport.write(data)

    def send_ok_line(self, string: str):
        """Send OK response."""
        _LOGGER.debug("Sending OK: %s", string)
        self.send(("e OK " + quote(string) + "\r\n").encode(encoding="ascii"))

    def send_response_line(self, string: str):
        """Send state response."""
        _LOGGER.debug("Sending Response: %s", string)
        self.send(("r " + quote(string) + "\r\n").encode(encoding="ascii")
        )

    def send_state_line(self, string: str):
        """Send state update."""
        _LOGGER.debug("Sending State: %s", string)
        self.send(("s " + string + "\r\n").encode(encoding="ascii"))

    def async_call_service(
        self,
        entity_id,
        display_name,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None,
        value: Any | None = None,
    ) -> None:
        """Fire event and call service for changes from BeoLink App."""
        event_data = {
            ATTR_ENTITY_ID: entity_id,
            display_name: display_name,
            ATTR_SERVICE: service,
            value: value,
        }
        context = Context()

        self.hass.bus.async_fire("beolink_state_change", event_data, context=context)
        self.hass.async_create_task(
            self.hass.services.async_call(
                domain, service, service_data, context=context
            )
        )

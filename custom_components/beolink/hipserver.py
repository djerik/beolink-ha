"""Module for handling the tcp communication."""
import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs, quote, unquote

from homeassistant import core
from homeassistant.auth.providers.homeassistant import HassAuthProvider, InvalidAuth
from homeassistant.components.alarm_control_panel import (
    DOMAIN as ALARM_DOMAIN,
    SERVICE_ALARM_ARM_AWAY,
    SERVICE_ALARM_ARM_HOME,
    SERVICE_ALARM_DISARM,
    AlarmControlPanelState,
)
from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN
from homeassistant.components.climate import (
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
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
    brightness_supported,
    color_supported,
)
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_SELECT_SOURCE,
)
from homeassistant.components.remote import (
    DOMAIN as REMOTE_DOMAIN,
    SERVICE_SEND_COMMAND,
)
from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
from homeassistant.const import (
    ATTR_CODE,
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    STATE_PLAYING,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    State,
    callback,
)
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.color import color_temperature_to_hs

from .helpers import (
    EntityFilterMixin,
    find_scene_by_name,
    get_current_temperature,
    get_entity_area_id,
    get_entity_from_state,
    get_scene_entities,
    get_target_temperature,
    is_entity_name_valid,
)
from .helpers.entity_helpers import SUPPORTED_RESOURCE_DOMAINS

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

    def __init__(self, domain: str, entity: Any, entity_name: str, area_name: str, features: int) -> None:
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

    def state_updates(self, state: State, attributes: dict[str, Any]) -> list[str]:
        """Generate state update."""
        states = []
        if self.domain == COVER_DOMAIN:
            if self.features & CoverEntityFeature.SET_POSITION:
                current_position = attributes.get(ATTR_CURRENT_POSITION)
                if current_position is not None:
                    states.append(
                        self.state_path + "LEVEL=" + str(current_position)
                    )
        elif self.domain == CLIMATE_DOMAIN:

            current_temp = get_current_temperature(state)
            if current_temp is not None:
                states.append( self.state_path + "TEMPERATURE=" + str(current_temp))
            target_temp = get_target_temperature(state)
            if target_temp is not None:
                states.append( self.state_path + "SETPOINT=" + str(target_temp))

            states.append(self.state_path + "MODE=Auto")
            states.append(self.state_path + "FAN AUTO=true")
        elif self.domain == LIGHT_DOMAIN:
            try:
                color_modes = (state.attributes.get(ATTR_SUPPORTED_COLOR_MODES) or [])

                if( brightness_supported(color_modes)
                    and (brightness := attributes.get(ATTR_BRIGHTNESS)) is not None
                    and isinstance(brightness, (int, float))):
                    states.append( self.state_path + "LEVEL=" + str(round(brightness / 255 * 100, 0) ) )
                color_modes = (attributes.get(ATTR_SUPPORTED_COLOR_MODES) or [] )

                if color_supported(color_modes):
                    color_mode = attributes.get(ATTR_COLOR_MODE)
                    if color_temp := attributes.get(ATTR_COLOR_TEMP_KELVIN):
                        hue, saturation = color_temperature_to_hs(color_temp)
                    elif color_mode == ColorMode.WHITE:
                        hue, saturation = 0, 0
                    elif hue_sat := attributes.get(ATTR_HS_COLOR):
                        hue, saturation = hue_sat
                    else:
                        hue = None
                        saturation = None
                    if isinstance(hue, (int, float)) and isinstance(saturation, (int, float)):
                        states[0] = (
                            states[0]
                            + "&COLOR=hsv("
                            + str(hue)
                            + ","
                            + str(saturation)
                            + ","
                            + str(round(brightness / 255 * 100, 0) if brightness is not None else 0)
                            + ")"
                        )
            except (KeyError, ValueError, TypeError, IndexError):
                    _LOGGER.exception("Problems handling color for state %s", state.name)
        elif self.domain == ALARM_DOMAIN:
            if state.state in (AlarmControlPanelState.ARMED_HOME, AlarmControlPanelState.ARMED_AWAY):
                states.append(self.state_path + "ALARM=0&READY=1&MODE=ARM")
            elif state.state == AlarmControlPanelState.TRIGGERED:
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
            states.append( self.state_path +temp )

        return states

class HIPServer(asyncio.Protocol, EntityFilterMixin):
    """Server handling the HIP protocol."""

    state = "awaiting user"

    def __init__(self, include_entities: list[str], exclude_entities: list[str], include_exclude_mode: str, hass: core.HomeAssistant) -> None:
        """Init HIPServer."""
        self.include_entities = include_entities
        self.exclude_entities = exclude_entities
        self.include_exclude_mode = include_exclude_mode
        self.hass = hass
        self.providers = self.hass.auth.auth_providers
        self.user = ""
        self.transport: asyncio.Transport | None = None
        self.buffer = ""
        self._subscriptions: list[CALLBACK_TYPE] = []
        self.hip_ressources_by_entity_id = {}
        self.hip_ressources_by_entity_name = {}

    def handle_resource_state_data(self, entity_id: str, state: State, data: dict[str, Any]) -> None:
        """Handle states data to HIP events."""
        state_updates = self.hip_ressources_by_entity_id[entity_id].state_updates(
            state, data
        )
        for state_update in state_updates:
            self.send_state_line(state_update)

    def _handle_query_all_resources(self) -> None:
        """Handle query for all resources."""
        self.send_ok_line("q */*/*/*")

        dr_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)

        # Process regular resources (cameras are handled separately via MJPEG/snapshot)
        for state in self.hass.states.async_all():
            if state.domain not in SUPPORTED_RESOURCE_DOMAINS:
                continue
            if state.domain == CAMERA_DOMAIN:
                continue
            if not self.should_include_entity(state.entity_id):
                continue
            if not is_entity_name_valid(state.name):
                _LOGGER.info("Entity %s has invalid name for BeoLink usage", state.name)
                continue

            entity = get_entity_from_state(self.hass, state)
            if entity is None:
                continue

            area_id = get_entity_area_id(self.hass, entity, dr_reg)
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
            self.hip_ressources_by_entity_id[state.entity_id] = ressource
            self.hip_ressources_by_entity_name[state.name] = ressource
            self._subscriptions.append(
                async_track_state_change_event(
                    self.hass,
                    [state.entity_id],
                    self._async_update_event_state_callback,
                )
            )
            self.handle_resource_state_data(state.entity_id, state, state.attributes)

        # List scenes as MACRO resources
        for scene_info in get_scene_entities(self.hass):
            area = area_reg.async_get_area(scene_info["area_id"])
            if area is None:
                continue
            macro_path = f"House/{quote(area.name, safe='')}/MACRO/{quote(scene_info['name'], safe='')}/"
            self.send_response_line(macro_path)

    def _handle_command(self, line: str) -> None:
        """Handle command from client."""
        try:
            command = unquote(line).split("/")
            if len(command) < 5:
                _LOGGER.warning("Invalid command format, expected at least 5 parts: %s", line)
                return
            action = command[4]
            entity_name = command[3]
            ressource_type = command[2]

            # Handle MACRO type separately (scenes are not registered as HIP resources)
            if ressource_type == "MACRO":
                self._handle_macro_command(action, entity_name)
                self.send_ok_line("c ")
                return

            if entity_name not in self.hip_ressources_by_entity_name:
                _LOGGER.warning("Entity '%s' not found in registered HIP resources", entity_name)
                return

            hip_ressource = self.hip_ressources_by_entity_name[entity_name]
            params = {ATTR_ENTITY_ID: hip_ressource.entity_id}
        except Exception:
            _LOGGER.exception("Error parsing command '%s'", line)
            return

        try:
            if ressource_type == "SHADE":
                self._handle_shade_command(action, hip_ressource, params)
            elif ressource_type == "DIMMER":
                self._handle_dimmer_command(action, hip_ressource, params)
            elif ressource_type == "THERMOSTAT_1SP":
                self._handle_thermostat_command(action, hip_ressource, params)
            elif ressource_type == "ALARM":
                self._handle_alarm_command(action, hip_ressource, params)
            elif ressource_type == "AV renderer":
                self._handle_av_renderer_command(action, hip_ressource, params)
            self.send_ok_line("c ")
        except Exception:
            _LOGGER.exception(
                "Error processing resource command for entity '%s', resource type '%s'",
                entity_name,
                ressource_type,
            )

    def _handle_shade_command(self, action: str, hip_ressource: HIPRessource, params: dict[str, Any]) -> None:
        """Handle shade commands."""
        service = None
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
            level = parameters.get("LEVEL")
            if level:
                params[ATTR_POSITION] = level[0]
            else:
                _LOGGER.warning("Missing LEVEL parameter in shade SET command")
                return
        if service is not None:
            self.async_call_service(
                hip_ressource.entity_id,
                hip_ressource.entity_name,
                COVER_DOMAIN,
                service,
                params,
            )

    def _handle_dimmer_command(self, action: str, hip_ressource: HIPRessource, params: dict[str, Any]) -> None:
        """Handle dimmer commands."""
        parameters = str(action).split("?")
        if len(parameters) < 2:
            _LOGGER.warning("Invalid dimmer command format: %s", action)
            return
        parameter = parameters[0]
        value_parts = parameters[1].split("=")
        if len(value_parts) < 2:
            _LOGGER.warning("Invalid dimmer command value format: %s", action)
            return
        value = value_parts[1]
        if parameter == "SET":
            params[ATTR_BRIGHTNESS_PCT] = value
        if parameter == "SET COLOR":
            hsv = value.split(",")
            if len(hsv) < 3:
                _LOGGER.warning("Invalid color format in dimmer command: %s", value)
                return
            hue = hsv[0][4:]
            saturation = hsv[1]
            params[ATTR_HS_COLOR] = (hue, saturation)
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

    def _handle_thermostat_command(self, action: str, hip_ressource: HIPRessource, params: dict[str, Any]) -> None:
        """Handle thermostat commands."""
        if action.startswith("SET SETPOINT"):
            qs = str(action).split("?")[1]
            parameters = parse_qs(qs)
            params[ATTR_TEMPERATURE] = parameters["VALUE"][0]
            self.async_call_service(
                hip_ressource.entity_id,
                hip_ressource.entity_name,
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                params,
            )

    def _handle_alarm_command(self, action: str, hip_ressource: HIPRessource, params: dict[str, Any]) -> None:
        """Handle alarm commands."""
        qs = str(action).split("?")[1]
        parameters = parse_qs(qs)
        service = None
        if action.startswith("DISARM"):
            service = SERVICE_ALARM_DISARM
            params[ATTR_CODE] = parameters["CODE"][0]
        elif action.startswith("ARM"):
            mode = parameters["MODE"][0]
            if mode == "HOME":
                service = SERVICE_ALARM_ARM_HOME
            elif mode == "AWAY":
                service = SERVICE_ALARM_ARM_AWAY
        if service is not None:
            self.async_call_service(
                hip_ressource.entity_id,
                hip_ressource.entity_name,
                ALARM_DOMAIN,
                service,
                params,
            )

    def _handle_av_renderer_command(self, action: str, hip_ressource: HIPRessource, params: dict[str, Any]) -> None:
        """Handle AV renderer commands."""
        parameters = {}
        if "?" in str(action):
            qs = str(action).split("?")[1]
            parameters = parse_qs(qs)
        service = None
        if action == "Standby":
            service = SERVICE_TURN_OFF
        if action.startswith("Select source by id") and "sourceUniqueId" in parameters:
            service = SERVICE_SELECT_SOURCE
            source_id = parameters["sourceUniqueId"][0]

            # Use state attributes to get source list (proper HA API)
            state = self.hass.states.get(hip_ressource.entity_id)
            if state:
                source_list = state.attributes.get(ATTR_INPUT_SOURCE_LIST, [])

                # Try exact match first
                if source_id in source_list:
                    params[ATTR_INPUT_SOURCE] = source_id
                else:
                    # Use the entity object already stored in HIPRessource
                    entity = hip_ressource.entity
                    if entity and hasattr(entity, "_speaker"):
                        try:
                            index = entity._speaker.sourcesID.index(source_id)
                            params[ATTR_INPUT_SOURCE] = entity._speaker.sources[index]
                        except (ValueError, AttributeError, IndexError):
                            _LOGGER.warning(
                                "Could not find source for sourceUniqueId '%s' on entity '%s'",
                                source_id,
                                hip_ressource.entity_id,
                            )
                            service = None
                    else:
                        _LOGGER.warning(
                            "Source '%s' not in source_list and entity does not support source mapping",
                            source_id,
                        )
                        service = None
            else:
                _LOGGER.warning("Entity '%s' not found", hip_ressource.entity_id)
                service = None
        if action.startswith("Volume level") and "Level" in parameters:
            service = SERVICE_VOLUME_SET
            params[ATTR_MEDIA_VOLUME_LEVEL] = float(parameters["Level"][0]) / 100
        if action.startswith("Volume adjust") and "Command" in parameters:
            if parameters["Command"][0] == "Mute":
                service = SERVICE_VOLUME_MUTE
                # Use state to get current mute status
                state = self.hass.states.get(hip_ressource.entity_id)
                if state:
                    is_muted = state.attributes.get(ATTR_MEDIA_VOLUME_MUTED, False)
                    params[ATTR_MEDIA_VOLUME_MUTED] = not is_muted
                else:
                    # Default to toggling to muted if state not available
                    params[ATTR_MEDIA_VOLUME_MUTED] = True
        if service is not None:
            self.async_call_service(
                hip_ressource.entity_id,
                hip_ressource.entity_name,
                MEDIA_PLAYER_DOMAIN,
                service,
                params,
            )
        if action.startswith(("Send command", "Beo4 advanced command")):
            # Find the remote entity corresponding to this media player
            # e.g., media_player.beovision_eclipse -> remote.beovision_eclipse
            remote_entity = None
            if hip_ressource.entity_id:
                remote_entity_id = hip_ressource.entity_id.replace(
                    f"{MEDIA_PLAYER_DOMAIN}.", f"{REMOTE_DOMAIN}."
                )
                remote_entity = self.hass.states.get(remote_entity_id)

            if remote_entity and "Command" in parameters:
                service = SERVICE_SEND_COMMAND
                params = {ATTR_ENTITY_ID: remote_entity.entity_id}
                command_key = parameters["Command"][0]
                if command_key in REMOTE_MAPPING:
                    params["command"] = REMOTE_MAPPING[command_key]
                    self.async_call_service(
                        remote_entity.entity_id,
                        remote_entity.attributes.get("friendly_name", "Remote"),
                        REMOTE_DOMAIN,
                        service,
                        params,
                    )
                else:
                    _LOGGER.warning("Unknown remote command: %s", command_key)
            else:
                _LOGGER.warning("No remote entity found to send command")

    def _handle_macro_command(self, action: str, macro_name: str) -> None:
        """Handle macro (HA scene) commands.

        Macros in BeoLink map to Home Assistant scenes. When the user taps
        a scene in the BeoLiving app, it sends a FIRE command.
        """
        if action != "FIRE":
            _LOGGER.warning("Unsupported macro command: %s", action)
            return

        # Find the scene by its friendly name
        scene_state = find_scene_by_name(self.hass, macro_name)
        if scene_state:
            _LOGGER.debug("Firing scene %s (entity: %s)", macro_name, scene_state.entity_id)
            self.hass.async_create_task(
                self.hass.services.async_call(
                    SCENE_DOMAIN,
                    "turn_on",
                    {ATTR_ENTITY_ID: scene_state.entity_id},
                )
            )
        else:
            _LOGGER.warning("Scene not found for macro: %s", macro_name)

    @callback
    def _async_update_event_state_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Receives event changes from HA."""
        new_state = event.data["new_state"]
        if new_state is None:
            return
        self.handle_resource_state_data(
            event.data["entity_id"], new_state, new_state.attributes
        )

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Client connnected."""
        self.transport = transport # type: ignore[assignment]
        self.send(b"login: ")

    def connection_lost(self, exc: Exception | None) -> None:
        """Unsubscribe listeners when clients disconnects."""
        while len(self._subscriptions) > 0:
            self._subscriptions.pop()()

    async def check_login(self, username: str, password: str) -> bool:
        """Check ip / credentials against Home Assistant."""
        for provider in self.providers:
            if isinstance(provider, HassAuthProvider):
                try:
                    await provider.async_validate_login(username, password)  # type: ignore[attr-defined]
                except InvalidAuth:
                    return False
                self.state = "authenticated"
                self.send(b"\r\n")
                return True
        return False

    def data_received(self, data: bytes) -> None:
        """Received data from BeoLiving app."""
        try:
            self.buffer += data.decode()
            lines = self.buffer.splitlines(True)
            for line in lines:
                if not line.endswith("\r\n"):
                    self.buffer = line
                    continue
                self.buffer = self.buffer.removeprefix(line)
                _LOGGER.debug("Received: %s", line)
                line = line.removesuffix("\r\n")
                self._handle_line(line)
        except Exception:
            _LOGGER.exception("Error processing received data")

    def _handle_line(self, line: str) -> None:
        """Handle a single line of data."""
        if self.state == "awaiting user":
            self.user = line
            self.state = "awaiting password"
            self.send(b"\r\npassword: ")
        elif self.state == "awaiting password":
            self.hass.loop.create_task(self.check_login(self.user, line))
        else:
            self._handle_authenticated_line(line)

    def _handle_authenticated_line(self, line: str) -> None:
        """Handle line after authentication."""
        if line == "f":
            self.send_ok_line("f")
        elif line == "q */*/SYSTEM/*":
            self.send_response_line(
                "Main/global/SYSTEM/BLGW/STATE_UPDATE?CURRENT%20FIRMWARE=1.5.4.557&LATEST%20FIRMWARE=&ROLLBACK%20AVAILABLE=1.5.4.533_2023.01.31-22.01.55&SYSTEM%20INFO=READY&revision=39"
            )
        elif line in ("q */*/*/*", "q"):
            self._handle_query_all_resources()
        elif line == "f */*/*/*":
            self.send_ok_line("f */*/*/*")
        elif line == "c Main/global/SYSTEM/BLI/CHECK%20FIRMWARE":
            self.send_ok_line("c Main/global/SYSTEM/BLI/CHECK FIRMWARE")
            self.send_response_line(
                "Main/global/SYSTEM/BLGW/STATE_UPDATE?CURRENT%20FIRMWARE=1.5.4.557&LATEST%20FIRMWARE=&ROLLBACK%20AVAILABLE=1.5.4.533_2023.01.31-22.01.55&SYSTEM%20INFO=READY&revision=39"
            )
        elif line.startswith("c Main/global/SYSTEM/BLI/UPDATE%20NOTIFICATION%20TOKEN"):
            self.send_ok_line(line + " 0")
        elif line.startswith("c "):
            self._handle_command(line)

    def send(self, data: bytes) -> None:
        """Low level send method."""
        if self.transport is not None:
            self.transport.write(data)

    def send_ok_line(self, string: str) -> None:
        """Send OK response."""
        _LOGGER.debug("Sending OK: %s", string)
        self.send(("e OK " + quote(string) + "\r\n").encode(encoding="ascii"))

    def send_response_line(self, string: str) -> None:
        """Send state response."""
        _LOGGER.debug("Sending Response: %s", string)
        self.send(("r " + quote(string) + "\r\n").encode(encoding="ascii")
        )

    def send_state_line(self, string: str) -> None:
        """Send state update."""
        _LOGGER.debug("Sending State: %s", string)
        self.send(("s " + string + "\r\n").encode(encoding="ascii"))

    def async_call_service(
        self,
        entity_id: str,
        display_name: str,
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

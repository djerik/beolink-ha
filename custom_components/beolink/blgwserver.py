"""Module for returning data formatted in json."""

import base64
import binascii
import json
import logging
import mimetypes
from pathlib import Path
import secrets
import time
from typing import TypedDict
from urllib.parse import unquote, urlparse

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
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    CoverEntityFeature,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS_PCT,
    ATTR_HS_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    DOMAIN as LIGHT_DOMAIN,
    color_supported,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_TURN_ON,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar, device_registry as dr

from .helpers import (
    EntityFilterMixin,
    find_scene_by_name,
    get_brightness_level,
    get_cover_position,
    get_entity_area_id,
    get_entity_from_state,
    get_scene_entities,
    is_beoplay_media_player,
    is_entity_name_valid,
    map_beolink_mode_to_hvac,
    map_hvac_mode_to_beolink,
)
from .helpers.entity_helpers import SUPPORTED_RESOURCE_DOMAINS
from .model.blgwpwebservices import Area, Zone, blgwpwebservices

_LOGGER = logging.getLogger(__name__)

# Timing threshold in seconds - log warning if request exceeds this
_TIMING_THRESHOLD = 0.1


class TimingContext:
    """Context manager for timing code blocks."""

    def __init__(self, name: str, log_always: bool = False) -> None:
        """Initialize timing context."""
        self.name = name
        self.log_always = log_always
        self.start_time = 0.0
        self.checkpoints: list[tuple[str, float]] = []

    def __enter__(self) -> "TimingContext":
        """Start timing."""
        self.start_time = time.perf_counter()
        self.checkpoints = []
        return self

    def checkpoint(self, label: str) -> None:
        """Record a checkpoint with elapsed time since start."""
        elapsed = time.perf_counter() - self.start_time
        self.checkpoints.append((label, elapsed))

    def __exit__(self, *args) -> None:
        """Stop timing and log if threshold exceeded."""
        total_time = time.perf_counter() - self.start_time
        if self.log_always or total_time > _TIMING_THRESHOLD:
            msg = f"{self.name} took {total_time*1000:.1f}ms"
            if self.checkpoints:
                details = ", ".join(
                    f"{label}: {elapsed*1000:.1f}ms"
                    for label, elapsed in self.checkpoints
                )
                msg += f" [{details}]"
            if total_time > _TIMING_THRESHOLD:
                _LOGGER.warning(msg)
            else:
                _LOGGER.debug(msg)

class _SessionData(TypedDict):
    """Session data structure."""

    username: str
    created: float


# Module-level session storage: maps session_id -> session data
_SESSION_STORE: dict[str, _SessionData] = {}


def create_session(username: str) -> str:
    """Create a new session for the authenticated user."""
    session_id = secrets.token_urlsafe(32)
    _SESSION_STORE[session_id] = {
        "username": username,
        "created": time.time(),
    }
    return session_id


def get_session_user(session_id: str) -> str | None:
    """Get the username associated with a session."""
    session = _SESSION_STORE.get(session_id)
    if session:
        return session.get("username")
    return None

class CustomBasicAuth(BasicAuthMiddleware):
    """Class for handlig authentication against Home Assistant users."""

    # Paths that do not require authentication
    UNPROTECTED_PATHS = ['/webpanel/', '/common/']

    def __init__(self, providers: list[AuthProvider]) -> None:
        """Init CustomBasicAuth."""
        self.providers = providers
        super().__init__()

    def challenge(self):
        """Return 401 with WWW-Authenticate header to trigger browser login prompt."""
        return web.Response(
            status=401,
            reason='UNAUTHORIZED',
            text='Unauthorized',
            content_type='text/plain',
            headers={'WWW-Authenticate': 'Basic realm="BeoLink Gateway"'},
        )

    async def __call__(self, request: web.Request, handler):
        """Override __call__ to skip auth for certain paths and handle X-Basic auth."""
        # Skip authentication for unprotected paths
        for path in self.UNPROTECTED_PATHS:
            if request.path.startswith(path):
                return await handler(request)

        # Check for cookie-based session authentication (set by /a/model/subscriptions)
        session_cookie = request.cookies.get('session')
        if session_cookie:
            # Validate session exists in our store
            username = get_session_user(session_cookie)
            if username:
                # Store username in request for use by handlers
                request['authenticated_user'] = username
                return await handler(request)

        # Check for custom X-Basic authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('X-Basic '):
            # Extract base64 credentials
            try:
                credentials_b64 = auth_header[8:]  # Remove 'X-Basic ' prefix
                credentials = base64.b64decode(credentials_b64).decode('utf-8')
                username, password = credentials.split(':', 1)

                # Validate credentials
                if await self.check_credentials(username, password, request):
                    # Store username in request for use by handlers
                    request['authenticated_user'] = username
                    return await handler(request)
                return self.challenge()
            except (ValueError, UnicodeDecodeError, binascii.Error):
                return self.challenge()

        # Check for standard Basic authorization header
        if auth_header.startswith('Basic '):
            # Extract and validate Basic auth credentials
            try:
                credentials_b64 = auth_header[6:]  # Remove 'Basic ' prefix
                credentials = base64.b64decode(credentials_b64).decode('utf-8')
                username, password = credentials.split(':', 1)
                if await self.check_credentials(username, password, request):
                    # Store username in request for use by handlers
                    request['authenticated_user'] = username
                    return await handler(request)
                return self.challenge()
            except (ValueError, UnicodeDecodeError, binascii.Error):
                return self.challenge()

        # No authorization header provided
        return self.challenge()

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


class BLGWServer(EntityFilterMixin):
    """Handles BLGW HTTP requests."""

    def __init__(self, name: str, serial_number: str, include_entities: list[str], exclude_entities: list[str], include_exclude_mode: str, hass: core.HomeAssistant) -> None:
        """Init BLGWServer."""
        self.name = name
        self.serial_number = serial_number
        self.include_entities = include_entities
        self.exclude_entities = exclude_entities
        self.include_exclude_mode = include_exclude_mode
        self.hass = hass
        # Cache for B&O device sources (keyed by entity_id)
        # This avoids ~200ms network calls on every blgwpservices request
        # TODO: Remove when pybeoplay exposes cached source data with sourceType
        self._source_cache: dict[str, list[dict]] = {}


    def _get_resource_entities(self) -> list[dict]:
        """Get all resource entities with their area information.

        Returns a list of dicts with keys: state, entity, area_id, name
        Filters by supported domains, include/exclude rules, and valid names.
        """
        dr_reg = dr.async_get(self.hass)
        result = []

        for state in self.hass.states.async_all():
            # Only include supported resource domains
            if state.domain not in SUPPORTED_RESOURCE_DOMAINS:
                continue

            # Apply include/exclude filters
            if not self.should_include_entity(state.entity_id):
                continue

            # Get entity from domain using helper
            entity = get_entity_from_state(self.hass, state)
            if entity is None:
                continue

            # Validate entity name using helper
            if not is_entity_name_valid(state.name):
                _LOGGER.debug(
                    "Entity %s has invalid name for BeoLink usage",
                    state.entity_id,
                )
                continue

            # Get area_id using helper
            area_id = get_entity_area_id(self.hass, entity, dr_reg)
            if area_id is None:
                continue

            # For media players, only include beoplay platform
            if state.domain == MEDIA_PLAYER_DOMAIN and not is_beoplay_media_player(entity):
                continue

            result.append({
                "state": state,
                "entity": entity,
                "area_id": area_id,
                "name": state.name,
                "domain": state.domain,
            })

        return result

    def _get_scene_entities(self) -> list[dict]:
        """Get all scene entities with their area information.

        Delegates to the shared helper function.
        Returns a list of dicts with keys: state, entity_entry, area_id, name, entity_id
        """
        return get_scene_entities(self.hass)

    def _create_scene_resource(self, scene_name: str, entity_id: str) -> dict[str, object]:
        """Create a scene/macro resource for blgwpservices format."""
        return {
            "type": "MACRO",
            "name": scene_name,
            "timer": False,
            "hide": False,
            "commands": ["FIRE", "COLLAPSE", "CANCEL"],
        }

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

    async def _get_cached_sources(self, entity) -> list[dict]:
        """Get sources for a B&O device, using cache to avoid repeated network calls.

        Sources are fetched once per device and cached for the integration's lifetime.
        This eliminates ~200ms latency per device on subsequent blgwpservices requests.

        TODO: Remove this cache when pybeoplay exposes sourceType in its cached data.
        """
        entity_id = entity.entity_id

        # Return cached data if available
        if entity_id in self._source_cache:
            return self._source_cache[entity_id]

        # Fetch from device and cache
        bl_sources: list[dict] = []
        if hasattr(entity, '_speaker') and hasattr(entity._speaker, 'async_getReq'):
            try:
                sources = await entity._speaker.async_getReq("BeoZone/Zone/Sources")
                if sources:
                    for source in sources.get('sources', []):
                        if len(source) > 1:
                            source_data = source[1]
                            if "friendlyName" in source_data and "sourceType" in source_data:
                                if "type" in source_data["sourceType"]:
                                    bl_source = {
                                        "name": source_data["friendlyName"],
                                        "uiType": "0.2",
                                        "code": "HDMI",
                                        "format": "F0",
                                        "networkBit": False,
                                        "select": {
                                            "cmds": [
                                                f"Select source by id?sourceUniqueId={source_data['id']}"
                                            ]
                                        },
                                        "sourceId": source_data["id"],
                                        "sourceType": source_data["sourceType"]["type"],
                                        "profiles": "",
                                    }
                                    bl_sources.append(bl_source)
            except Exception as err:
                _LOGGER.exception(
                    "Error fetching sources for %s: %s", entity.name, err
                )

        # Cache the result (even if empty, to avoid repeated failed fetches)
        self._source_cache[entity_id] = bl_sources
        _LOGGER.debug(
            "Cached %d sources for %s", len(bl_sources), entity.name
        )
        return bl_sources

    async def _create_media_player_resource(self, state, entity) -> dict[str, object]:
        """Create a media player resource."""
        # Extract serial number from unique_id (format: "beoplay-{serial}-media_player")
        serial_number = "unknown"
        if hasattr(entity, 'unique_id') and entity.unique_id:
            parts = entity.unique_id.split('-')
            if len(parts) >= 2:
                serial_number = parts[1]

        # Get sources from cache or fetch from device
        bl_sources = await self._get_cached_sources(entity)

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

    async def camera_snapshot(self, request: web.Request) -> web.Response:
        """Handle a camera snapshot request.

        URL format: /a/webview/{area}/{zone}/CAMERA/{camera_name}/snapshot
        The camera_name may have underscores replacing dots (e.g., 192_168_1_61 for 192.168.1.61).
        """
        camera_name = request.match_info.get("camera_name", "")

        states = self.hass.states.async_all()
        camera_state = None

        for state in states:
            if state.domain != CAMERA_DOMAIN:
                continue
            friendly_name = state.attributes.get("friendly_name", state.name)
            # Match by original name, dots-replaced name, or spaces-replaced name
            if friendly_name == camera_name:
                camera_state = state
                break

        if camera_state is None:
            _LOGGER.warning("Camera not found: %s", camera_name)
            return web.Response(status=404, text="Camera not found")

        try:
            image = await async_get_image(self.hass, camera_state.entity_id)
            return web.Response(
                body=image.content,
                content_type=image.content_type,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        except HomeAssistantError as err:
            _LOGGER.error("Error fetching camera image for %s: %s", camera_state.entity_id, err)
            return web.Response(status=500, text=f"Error fetching camera image: {err}")

    async def blgwpservices(self, request: web.Request) -> web.Response:
        """Handle the blgwpservices.json request."""
        with TimingContext("blgwpservices") as timing:
            area_reg = ar.async_get(self.hass)
            bl_areas: dict[str, Area] = {}
            bl_zones: dict[str, Zone] = {}
            bl_ressources: dict[str, dict[str, dict[str, object]]] = {}

            # Process resource entities using consolidated helper
            resource_entities = self._get_resource_entities()
            timing.checkpoint(f"get_entities({len(resource_entities)})")

            for entity_info in resource_entities:
                state = entity_info["state"]
                entity = entity_info["entity"]
                area_id = entity_info["area_id"]

                # Ensure zone exists for this area
                if area_id not in bl_zones:
                    area = area_reg.async_get_area(area_id)
                    if area is None:
                        continue
                    bl_zones[area_id] = Zone(area.name, "house", False, False, [])
                    bl_ressources[area_id] = {}

                # Create resource based on domain
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
                elif state.domain == MEDIA_PLAYER_DOMAIN:
                    mp_start = time.perf_counter()
                    resource = await self._create_media_player_resource(state, entity)
                    mp_time = time.perf_counter() - mp_start
                    if mp_time > 0.05:  # Log if media player takes > 50ms
                        timing.checkpoint(f"media_player({state.name})={mp_time*1000:.0f}ms")

                if resource:
                    bl_ressources[area_id][state.entity_id] = resource

            timing.checkpoint("resources_done")

            # Process scene entities using consolidated helper
            for scene_info in self._get_scene_entities():
                area_id = scene_info["area_id"]
                scene_name = scene_info["name"]
                entity_id = scene_info["entity_id"]

                # Ensure zone exists for this area
                if area_id not in bl_zones:
                    area = area_reg.async_get_area(area_id)
                    if area is None:
                        continue
                    bl_zones[area_id] = Zone(area.name, "house", False, False, [])
                    bl_ressources[area_id] = {}

                # Create scene resource
                resource = self._create_scene_resource(scene_name, entity_id)
                bl_ressources[area_id][entity_id] = resource

            timing.checkpoint("scenes_done")

            # Sort resources within each zone
            for bl_zone_key, bl_zone in bl_zones.items():
                sorted_resources = list(bl_ressources[bl_zone_key].values())
                sorted_resources.sort(key=lambda x: str(x.get("name", "")))
                bl_zone.resources = sorted_resources

            # Build area structure
            sorted_zones = list(bl_zones.values())
            sorted_zones.sort(key=lambda x: x.name)
            house_area = Area("House", sorted_zones)
            house_area.zones = sorted_zones
            bl_areas["House"] = house_area

            main_zone = Zone("global", "house", True, False, [])
            main_area = Area("Main", [main_zone])
            bl_areas["main"] = main_area

            data = blgwpwebservices(self.name, self.serial_number, list(bl_areas.values()))
            response_body = jsonpickle.encode(data, unpicklable=False)
            timing.checkpoint("encoded")

            return web.Response(body=response_body)

    async def webpanel_index_html(self, request: web.Request) -> web.Response:
        """Serve the webpanel index.html page."""
        webpanel_dir = Path(__file__).parent / "webpanel"
        index_file = webpanel_dir / "index.html"

        if index_file.exists():
            content = await self.hass.async_add_executor_job(index_file.read_text)
            return web.Response(
                body=content,
                content_type="text/html",
                charset="UTF-8",
                )

        # Return a placeholder if the file doesn't exist yet
        return web.Response(
            text="<html><body><h1>BLGW Web Panel</h1><p>index.html not found</p></body></html>",
            content_type="text/html",
        )

    async def webpanel_index(self, request: web.Request) -> web.Response:
        """Serve the webpanel index.xhtml page."""
        webpanel_dir = Path(__file__).parent / "webpanel"
        index_file = webpanel_dir / "index.xhtml"

        if index_file.exists():
            content = await self.hass.async_add_executor_job(index_file.read_text)
            return web.Response(
                body=content,
                content_type="application/xhtml+xml",
                )

        # Return a placeholder if the file doesn't exist yet
        html_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>BLGW Web Panel</title>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <link rel="stylesheet" type="text/css" href="/webpanel/css/style.css" />
    <script type="text/javascript" src="/webpanel/js/main.js"></script>
</head>
<body>
    <div id="header">
        <h1>BLGW Web Panel</h1>
        <p>BeoLink Gateway - Home Assistant Integration</p>
    </div>
    <div id="content">
        <div class="info-box">
            <h2>System Information</h2>
            <p><strong>Name:</strong> """ + self.name + """</p>
            <p><strong>Serial Number:</strong> """ + self.serial_number + """</p>
            <p><strong>Status:</strong> Online</p>
        </div>
        <div class="info-box">
            <h2>Quick Links</h2>
            <ul>
                <li><a href="/blgwpservices.json">View Services JSON</a></li>
            </ul>
        </div>
        <div class="info-box">
            <h2>Note</h2>
            <p>To customize this page, place your webpanel files in:</p>
            <code>custom_components/beolink/webpanel/</code>
            <p>The integration will automatically serve files from that directory.</p>
        </div>
    </div>
</body>
</html>"""
        return web.Response(text=html_content, content_type="application/xhtml+xml")

    async def webpanel_static(self, request: web.Request) -> web.Response:
        """Serve static webpanel resources (CSS, JS, images)."""
        resource_path = request.match_info.get("resource", "")
        webpanel_dir = Path(__file__).parent / "webpanel"
        file_path = webpanel_dir / resource_path

        # Security: ensure the path is within webpanel directory
        try:
            file_path = file_path.resolve()
            webpanel_dir = webpanel_dir.resolve()
            if not str(file_path).startswith(str(webpanel_dir)):
                return web.Response(status=403, text="Forbidden")
        except (ValueError, OSError):
            return web.Response(status=400, text="Bad Request")

        if file_path.exists() and file_path.is_file():
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            content = await self.hass.async_add_executor_job(file_path.read_bytes)
            return web.Response(
                body=content,
                content_type=content_type,
                headers={
                    "Cache-Control": "max-age=300",
                    "Accept-Ranges": "bytes",
                },
            )

        # Return appropriate placeholder based on file type
        if resource_path.endswith(".css"):
            css_content = """/* BLGW Web Panel Styles */
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 0;
    background-color: #f5f5f5;
}

#header {
    background-color: #2c3e50;
    color: white;
    padding: 20px;
    text-align: center;
}

#header h1 {
    margin: 0;
    font-size: 2em;
}

#header p {
    margin: 10px 0 0 0;
    font-size: 1.2em;
    opacity: 0.8;
}

#content {
    max-width: 1200px;
    margin: 20px auto;
    padding: 20px;
}

.info-box {
    background: white;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.info-box h2 {
    margin-top: 0;
    color: #2c3e50;
    border-bottom: 2px solid #3498db;
    padding-bottom: 10px;
}

.info-box ul {
    list-style: none;
    padding: 0;
}

.info-box li {
    padding: 8px 0;
}

.info-box a {
    color: #3498db;
    text-decoration: none;
}

.info-box a:hover {
    text-decoration: underline;
}

.info-box code {
    background: #f8f9fa;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
}"""
            return web.Response(text=css_content, content_type="text/css")

        if resource_path.endswith(".js"):
            js_content = """// BLGW Web Panel JavaScript
console.log('BLGW Web Panel loaded');

// Add your custom JavaScript here
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded');
});"""
            return web.Response(text=js_content, content_type="application/javascript")

        _LOGGER.error("Unknown webpanel static file requested: /webpanel/%s", resource_path)
        return web.Response(status=404, text="Not Found")

    async def common_static(self, request: web.Request) -> web.Response:
        """Serve common static resources (sprites, CSS, images from /common path)."""
        resource_path = request.match_info.get("resource", "")
        webpanel_dir = Path(__file__).parent / "webpanel"
        file_path = webpanel_dir / "common" / resource_path

        # Security: ensure the path is within webpanel/common directory
        try:
            file_path = file_path.resolve()
            common_dir = (webpanel_dir / "common").resolve()
            if not str(file_path).startswith(str(common_dir)):
                return web.Response(status=403, text="Forbidden")
        except (ValueError, OSError):
            return web.Response(status=400, text="Bad Request")

        if file_path.exists() and file_path.is_file():
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            content = await self.hass.async_add_executor_job(file_path.read_bytes)
            return web.Response(
                body=content,
                content_type=content_type,
                headers={
                    "Cache-Control": "max-age=300",
                    "Accept-Ranges": "bytes",
                },
            )

        _LOGGER.error("Unknown common static file requested: /common/%s", resource_path)
        return web.Response(status=404, text="Not Found")

    async def _generate_zones_and_areas(self) -> tuple[dict, dict]:
        """Generate zones.json and areas.json dynamically from Home Assistant areas.

        Returns:
            Tuple of (zones_data, areas_data)
        """
        area_reg = ar.async_get(self.hass)
        zones_list = []
        areas_list = []

        # Start IDs from 1401 for zones, 1301 for areas
        zone_id = 1401
        area_id = 1301

        # Main area (global) - ID 1301
        main_area_id = area_id
        area_id += 1

        # Create the global zone in Main area (always first, always present)
        global_zone_id = zone_id
        global_zone = {
            "id": global_zone_id,
            "global": True,
            "group": "",
            "icon": "house",
            "name": "global",
            "number": 240,
            "address": "Main/global",
            "links": {
                "addressables": [],
                "area": main_area_id,
            },
        }
        zones_list.append(global_zone)
        zone_id += 1

        # Main area contains only the global zone
        main_area = {
            "id": main_area_id,
            "global": True,
            "name": "Main",
            "links": {
                "zones": [global_zone_id],
            },
        }
        areas_list.append(main_area)

        # House area - ID 1302
        house_area_id = area_id
        house_zone_ids = []
        area_id += 1

        # Get all HA areas and create zones for each
        ha_areas = area_reg.async_list_areas()
        zone_number = 1

        # Map area IDs to zone IDs for populating addressables later
        zone_id_offset = 1402  # First actual zone (not global)
        area_to_zone_id = {}

        for idx, ha_area in enumerate(sorted(ha_areas, key=lambda x: x.name)):
            current_zone_id = zone_id_offset + idx
            area_to_zone_id[ha_area.id] = current_zone_id

            zone = {
                "id": current_zone_id,
                "global": False,
                "group": "",
                "icon": self._get_zone_icon(ha_area.name),
                "name": ha_area.name,
                "number": zone_number,
                "address": f"House/{ha_area.name}",
                "links": {
                    "addressables": [],
                    "area": house_area_id,
                },
            }
            zones_list.append(zone)
            house_zone_ids.append(current_zone_id)
            zone_id = current_zone_id + 1
            zone_number += 1

        # Populate addressables for each zone using consolidated helpers
        zone_addressables = {zone["id"]: [] for zone in zones_list}
        addressable_id = 3001  # Start addressable IDs from 3001

        # Domain priority for sorting (lower number = higher priority)
        DOMAIN_PRIORITY = {
            MEDIA_PLAYER_DOMAIN: 0,
            LIGHT_DOMAIN: 1,
            COVER_DOMAIN: 2,
            CLIMATE_DOMAIN: 3,
            CAMERA_DOMAIN: 4,
            ALARM_DOMAIN: 5,
        }

        # Use consolidated helper to collect resource entities with zone info
        entity_data = []
        for entity_info in self._get_resource_entities():
            target_zone_id = area_to_zone_id.get(entity_info["area_id"])
            if target_zone_id:
                entity_data.append({
                    "zone_id": target_zone_id,
                    "domain": entity_info["domain"],
                    "name": entity_info["name"],
                    "priority": DOMAIN_PRIORITY.get(entity_info["domain"], 99),
                })

        # Sort entities by domain priority and then by name
        entity_data.sort(key=lambda x: (x["priority"], x["name"].lower()))

        # Assign addressable IDs in sorted order and populate zones
        for entity_info in entity_data:
            zone_id = entity_info["zone_id"]
            if zone_id in zone_addressables:
                zone_addressables[zone_id].append(addressable_id)
            addressable_id += 1

        # Use consolidated helper to include macros (scenes) in zone addressables
        macro_id = 1601  # Macros start at ID 1601
        for scene_info in self._get_scene_entities():
            target_zone_id = area_to_zone_id.get(scene_info["area_id"])
            if target_zone_id and target_zone_id in zone_addressables:
                zone_addressables[target_zone_id].append(macro_id)
            macro_id += 1

        # Update zones with their addressables
        for zone in zones_list:
            zone["links"]["addressables"] = zone_addressables.get(zone["id"], [])

        # House area contains all HA area zones
        house_area = {
            "id": house_area_id,
            "global": False,
            "name": "House",
            "links": {
                "zones": house_zone_ids,
            },
        }
        areas_list.append(house_area)

        return {"zones": zones_list}, {"areas": areas_list}

    def _get_zone_icon(self, area_name: str) -> str:
        """Map area names to zone icons."""
        name_lower = area_name.lower()
        icon_map = {
            "living": "hometheater",
            "kitchen": "kitchen",
            "bedroom": "bedroom",
            "bathroom": "bath",
            "garage": "garage",
            "office": "office",
            "dining": "dining",
            "garden": "bbq",
            "outdoor": "bbq",
            "front": "bbq",
            "back": "bbq",
        }

        for keyword, icon in icon_map.items():
            if keyword in name_lower:
                return icon

        return "house"

    async def _generate_cameras(self) -> dict:
        """Generate cameras.json dynamically from Home Assistant camera entities.

        Returns:
            Dictionary with cameras list
        """
        dr_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        cameras_list = []
        camera_id = 3701  # Start camera IDs from 3701

        # Map area IDs to zone IDs (zones start at 1401, first zone is global at 1401)
        zone_id_offset = 1402  # First actual zone (not global)
        area_to_zone = {}
        ha_areas = sorted(area_reg.async_list_areas(), key=lambda x: x.name)
        for idx, ha_area in enumerate(ha_areas):
            area_to_zone[ha_area.id] = zone_id_offset + idx

        states = self.hass.states.async_all()
        for state in states:
            if state.domain != CAMERA_DOMAIN:
                continue

            if not self.should_include_entity(state.entity_id):
                continue

            domain = self.hass.data.get(state.domain)
            if domain is None:
                continue
            entity = domain.get_entity(state.entity_id)
            if entity is None or entity.registry_entry is None:
                continue

            # Get area for the camera
            area_id = entity.registry_entry.area_id
            if area_id is None:
                device = dr_reg.async_get(entity.registry_entry.device_id)
                if device is not None:
                    area_id = device.area_id

            # Get zone ID for the area (default to first zone if no area)
            zone_id = area_to_zone.get(area_id, 1402) if area_id else 1402

            # Extract stream URL from entity attributes if available
            stream_source = state.attributes.get("stream_source", "")
            entity_picture = state.attributes.get("entity_picture", "")

            # Parse RTSP URL if available
            rtsp_url = ""
            base_url = ""
            if stream_source and stream_source.startswith("rtsp://"):
                rtsp_url = stream_source
                # Extract base URL from RTSP (e.g., rtsp://user:pass@host:port/path -> http://host)
                try:
                    parsed = urlparse(stream_source)
                    if parsed.hostname:
                        base_url = f"http://{parsed.hostname}"
                except (ValueError, AttributeError):
                    base_url = ""

            camera = {
                "id": camera_id,
                "availablePresets": 0,
                "baseUrl": base_url,
                "highResolutionPath": entity_picture or "/snapshot",
                "homePath": "",
                "lowResolutionPath": entity_picture or "/snapshot",
                "mjpegHighResolutionPath": f"/api/beolink/camera_mjpeg/{state.name}",
                "mjpegLowResolutionPath": f"/api/beolink/camera_mjpeg/{state.name}",
                "name": state.name or "Camera",
                "panLeftPath": "",
                "panRightPath": "",
                "panStopPath": "",
                "password": "",
                "presetPath": "",
                "rtspPath": "",
                "rtspUrl": rtsp_url,
                "streamingPath": "",
                "tiltDownPath": "",
                "tiltStopPath": "",
                "tiltUpPath": "",
                "type": "",
                "user": "",
                "zoomInPath": "",
                "zoomOutPath": "",
                "zoomStopPath": "",
                "links": {
                    "zone": zone_id,
                },
            }
            cameras_list.append(camera)
            camera_id += 1

        return {"cameras": cameras_list}

    async def _generate_addressables(self) -> dict:
        """Generate addressables.json dynamically from Home Assistant entities.

        Returns:
            Dictionary with addressables list
        """
        area_reg = ar.async_get(self.hass)
        addressables_list = []

        # Load static addressables from file (macros, systems, etc.)
        model_dir = Path(__file__).parent / "webpanel/model"
        static_addressables_file = model_dir / "addressables.json"

        if static_addressables_file.exists():
            try:
                content = await self.hass.async_add_executor_job(
                    static_addressables_file.read_text
                )
                static_data = json.loads(content)
                # Only keep non-resource entries (macros, systems, etc.)
                # Resources will be generated dynamically from Home Assistant
                addressables_list.extend(
                    item for item in static_data.get("addressables", [])
                    if item.get("backend") != "resources"
                )
            except (json.JSONDecodeError, OSError) as err:
                _LOGGER.warning("Failed to load static addressables: %s", err)

        # Map area IDs to zone info (zones start at 1401, first zone is global at 1401)
        zone_id_offset = 1402  # First actual zone (not global)
        area_to_zone_info = {}  # Maps area_id -> {"zone_id": id, "zone_name": name}
        ha_areas = sorted(area_reg.async_list_areas(), key=lambda x: x.name)
        for idx, ha_area in enumerate(ha_areas):
            area_to_zone_info[ha_area.id] = {
                "zone_id": zone_id_offset + idx,
                "zone_name": ha_area.name,
            }

        # Generate addressables from Home Assistant entities using consolidated helper
        addressable_id = 3001  # Start addressable IDs from 3001
        state_id = 1201  # Start state IDs from 1201

        # Spec definitions for different entity types
        SPEC_SHADE = {
            "id": 21060,
            "type": "SHADE",
            "label": "Shade",
            "commandSpecs": [
                {"id": 230174, "name": "STOP"},
                {"id": 230175, "name": "RAISE"},
                {"id": 230176, "name": "LOWER"},
                {"id": 230177, "name": "SET"},
            ],
        }
        SPEC_DIMMER = {
            "id": 21047,
            "type": "DIMMER",
            "label": "Virtual Dimmer",
            "commandSpecs": [
                {"id": 230140, "name": "SET"},
                {"id": 230141, "name": "SET COLOR"},
            ],
        }
        SPEC_THERMOSTAT = {
            "id": 21093,
            "type": "THERMOSTAT_1SP",
            "label": "Thermostat 1SP",
            "commandSpecs": [
                {
                    "id": 230200,
                    "name": "SET SETPOINT",
                    "arguments": {
                        "VALUE": {"type": "temperature", "units": "C", "value": 22},
                    },
                },
                {
                    "id": 230201,
                    "name": "SET MODE",
                    "arguments": {
                        "VALUE": {
                            "type": "enum",
                            "value": "Off",
                            "values": ["Off", "Heat", "Cool", "Auto", "Eco"],
                        },
                    },
                },
                {
                    "id": 230202,
                    "name": "SET FAN AUTO",
                    "arguments": {"VALUE": {"type": "boolean", "value": True}},
                },
            ],
        }

        # Domain priority for sorting (lower number = higher priority)
        DOMAIN_PRIORITY = {
            MEDIA_PLAYER_DOMAIN: 0,
            LIGHT_DOMAIN: 1,
            COVER_DOMAIN: 2,
            CLIMATE_DOMAIN: 3,
            CAMERA_DOMAIN: 4,
            ALARM_DOMAIN: 5,
        }

        # Use consolidated helper to get resource entities with zone info
        entity_data = []
        for entity_info in self._get_resource_entities():
            zone_info = area_to_zone_info.get(entity_info["area_id"])
            if zone_info is None:
                continue
            entity_data.append({
                "state": entity_info["state"],
                "domain": entity_info["domain"],
                "name": entity_info["name"],
                "zone_id": zone_info["zone_id"],
                "zone_name": zone_info["zone_name"],
                "priority": DOMAIN_PRIORITY.get(entity_info["domain"], 99),
            })

        # Sort entities by domain priority and then by name
        entity_data.sort(key=lambda x: (x["priority"], x["name"].lower()))

        # Create addressables in sorted order
        for entity_info in entity_data:
            state = entity_info["state"]
            zone_id = entity_info["zone_id"]
            zone_name = entity_info["zone_name"]

            # Build zone object with area info for command URL building
            zone_obj = {
                "id": zone_id,
                "name": zone_name,
                "area": {"id": 1302, "name": "House"},
            }

            # Create addressable based on entity type
            addressable = None
            if state.domain == COVER_DOMAIN:
                addressable = {
                    "id": addressable_id,
                    "backend": "resources",
                    "hints": [],
                    "name": state.name,
                    "publish": True,
                    "spec": SPEC_SHADE,
                    "zone": zone_obj,
                    "links": {
                        "spec": SPEC_SHADE["id"],
                        "state": state_id,
                        "zone": zone_id,
                    },
                }
                state_id += 1
            elif state.domain == LIGHT_DOMAIN:
                addressable = {
                    "id": addressable_id,
                    "backend": "resources",
                    "hints": [],
                    "name": state.name,
                    "publish": True,
                    "spec": SPEC_DIMMER,
                    "zone": zone_obj,
                    "links": {
                        "spec": SPEC_DIMMER["id"],
                        "state": state_id,
                        "zone": zone_id,
                    },
                }
                state_id += 1
            elif state.domain == CLIMATE_DOMAIN:
                addressable = {
                    "id": addressable_id,
                    "backend": "resources",
                    "hints": [],
                    "name": state.name,
                    "publish": True,
                    "spec": SPEC_THERMOSTAT,
                    "zone": zone_obj,
                    "links": {
                        "spec": SPEC_THERMOSTAT["id"],
                        "state": state_id,
                        "zone": zone_id,
                    },
                }
                state_id += 1

            if addressable:
                addressables_list.append(addressable)

            addressable_id += 1

        # Generate macros from Home Assistant scenes using consolidated helper
        macro_id = 1601  # Start macro IDs from 1601
        macro_number = 1  # Sequential number for macros
        current_timestamp = int(time.time())

        for scene_info in self._get_scene_entities():
            zone_info = area_to_zone_info.get(scene_info["area_id"])
            if zone_info is None:
                continue

            # Create macro matching the working format exactly
            macro = {
                "id": macro_id,
                "backend": "macros",
                "enabled": True,
                "executionCode": "",
                "hints": [],
                "name": scene_info["name"],
                "number": macro_number,
                "publish": True,
                "updated": current_timestamp,
                "user_generated": True,
                "orphan": False,
                "generic": False,
                "affectedZones": [],
                "entity_id": scene_info["entity_id"],  # Store for execution lookup
                "links": {
                    "actionSchedules": [],
                    "modes": [],
                    "updatedBy": 301,
                    "user": 301,
                    "zone": zone_info["zone_id"],
                },
            }
            addressables_list.append(macro)
            macro_id += 1
            macro_number += 1

        return {"addressables": addressables_list}

    async def _generate_states(self) -> dict:
        """Generate states.json dynamically from Home Assistant entities.

        Returns:
            Dictionary with states list
        """
        dr_reg = dr.async_get(self.hass)
        states_list = []

        # Load static states from file
        model_dir = Path(__file__).parent / "webpanel/model"
        static_states_file = model_dir / "states.json"

        if static_states_file.exists():
            try:
                content = await self.hass.async_add_executor_job(
                    static_states_file.read_text
                )
                static_data = json.loads(content)
                # Filter out dynamic states (owner >= 3001) as we'll generate those from Home Assistant
                for item in static_data.get("states", []):
                    owner_id = item.get("links", {}).get("owner", 0)
                    if owner_id < 3001:
                        states_list.append(item)
            except (json.JSONDecodeError, OSError) as err:
                _LOGGER.warning("Failed to load static states: %s", err)

        # Domain priority for sorting (must match _generate_addressables sorting)
        DOMAIN_PRIORITY = {
            MEDIA_PLAYER_DOMAIN: 0,
            LIGHT_DOMAIN: 1,
            COVER_DOMAIN: 2,
            CLIMATE_DOMAIN: 3,
            CAMERA_DOMAIN: 4,
            ALARM_DOMAIN: 5,
        }

        # Collect all entities with their metadata for sorting (same as _generate_addressables)
        entity_data = []
        states = self.hass.states.async_all()
        for state in states:
            # Only include supported domains
            if state.domain not in {
                COVER_DOMAIN,
                LIGHT_DOMAIN,
                CAMERA_DOMAIN,
                CLIMATE_DOMAIN,
                ALARM_DOMAIN,
                MEDIA_PLAYER_DOMAIN,
            }:
                continue

            # Apply include/exclude filters
            if not self.should_include_entity(state.entity_id):
                continue

            domain = self.hass.data.get(state.domain)
            if domain is None:
                continue
            entity = domain.get_entity(state.entity_id)
            if entity is None or entity.registry_entry is None:
                continue

            # Skip entities without names or with illegal characters
            if state.name is None:
                continue
            if "?" in state.name or "/" in state.name:
                continue

            # Get area for the entity
            area_id = entity.registry_entry.area_id
            if area_id is None:
                device = dr_reg.async_get(entity.registry_entry.device_id)
                if device is None:
                    continue
                area_id = device.area_id

            # Skip if no area assigned
            if area_id is None:
                continue

            # For media players, only include beoplay platform
            if state.domain == MEDIA_PLAYER_DOMAIN and entity.platform.platform_name != "beoplay":
                continue

            entity_data.append({
                "state": state,
                "domain": state.domain,
                "name": state.name,
                "priority": DOMAIN_PRIORITY.get(state.domain, 99),
            })

        # Sort entities by domain priority and then by name (same as _generate_addressables)
        entity_data.sort(key=lambda x: (x["priority"], x["name"].lower()))

        # Generate states in sorted order
        state_id = 1201  # Start state IDs from 1201
        addressable_id = 3001  # Start addressable IDs from 3001

        for entity_info in entity_data:
            state = entity_info["state"]

            # Create state entry based on entity type
            if state.domain == COVER_DOMAIN:
                # Get current position using helper
                position = get_cover_position(state)
                state_entry = {
                    "id": state_id,
                    "LEVEL": position,  # JavaScript uses resource.state.LEVEL for shades
                    "links": {
                        "owner": addressable_id,
                        "spec": None,
                    },
                }
                states_list.append(state_entry)
                state_id += 1

            elif state.domain == LIGHT_DOMAIN:
                # Get brightness using helper (already converted to 0-100)
                level = get_brightness_level(state)
                state_entry = {
                    "id": state_id,
                    "LEVEL": level,  # JavaScript uses resource.state.LEVEL for dimmers
                    "links": {
                        "owner": addressable_id,
                        "spec": None,
                    },
                }
                states_list.append(state_entry)
                state_id += 1

            elif state.domain == CLIMATE_DOMAIN:
                # Get climate state attributes
                current_temp = state.attributes.get("current_temperature")
                target_temp = state.attributes.get("temperature")
                hvac_mode = state.state  # e.g., "heat", "cool", "auto", "off"

                # Map HA hvac_mode to BeoLink mode using helper
                bl_mode = map_hvac_mode_to_beolink(hvac_mode)

                state_entry = {
                    "id": state_id,
                    "TEMPERATURE": current_temp if current_temp is not None else 20,
                    "SETPOINT": target_temp if target_temp is not None else 20,
                    "MODE": bl_mode,
                    "FAN AUTO": state.attributes.get("fan_mode", "auto"),
                    "VALUE": 1 if hvac_mode and hvac_mode != "off" else 0,
                    "links": {
                        "owner": addressable_id,
                        "spec": None,
                    },
                }
                states_list.append(state_entry)
                state_id += 1

            addressable_id += 1

        return {"states": states_list}

    async def model_api(self, request: web.Request) -> web.Response:
        """Handle /a/model/* API requests - serves cached JSON responses.

        This endpoint requires Basic Authentication via the Authorization header.
        The authentication is handled by the CustomBasicAuth middleware.

        Files are stored with .json extension in webpanel/model/ directory.
        For example: /a/model/subscriptions -> webpanel/model/subscriptions.json
                     /a/model/subscriptions/1/notifications -> webpanel/model/subscriptions/1/notifications.json

        Special handling:
        - /a/model/zones -> Dynamically generated from Home Assistant areas
        - /a/model/areas -> Dynamically generated from Home Assistant areas
        - /a/model/cameras -> Dynamically generated from Home Assistant camera entities
        - /a/model/addressables -> Dynamically generated from Home Assistant entities (covers, climate)
        - /a/model/states -> Dynamically generated from Home Assistant entities (covers, climate)
        - PUT /a/model/subscriptions/{id} -> Updates subscription backends
        """
        resource_path = request.match_info.get("resource", "")
        start_time = time.perf_counter()

        # Handle PUT /a/model/subscriptions/1 (or any subscription ID)
        if request.method == "PUT" and resource_path.startswith("subscriptions/"):
            try:
                body = await request.json()
                _LOGGER.debug("PUT %s: %s", resource_path, body)
                # Accept the subscription update and return success
                # In a real implementation, this would store the subscription preferences
                return web.Response(
                    text=json.dumps({"status": "ok"}),
                    content_type="application/json",
                    status=200,
                )
            except json.JSONDecodeError:
                return web.Response(
                    text=json.dumps({"error": "Invalid JSON"}),
                    content_type="application/json",
                    status=400,
                )

        model_dir = Path(__file__).parent / "webpanel/model"
        # Add .json extension to the resource path
        file_path = model_dir / f"{resource_path}.json"

        # Security: ensure the path is within webpanel/model directory
        try:
            file_path = file_path.resolve()
            webpanel_dir = (Path(__file__).parent / "webpanel/model").resolve()
            if not str(file_path).startswith(str(webpanel_dir)):
                return web.Response(status=403, text="Forbidden")
        except (ValueError, OSError):
            return web.Response(status=400, text="Bad Request")

        if file_path.exists() and file_path.is_file():
            # Use executor to avoid blocking the event loop
            content = await self.hass.async_add_executor_job(file_path.read_text)
            response = web.Response(
                body=content,
                content_type="application/json",
                charset="UTF-8",
            )

            # Set session cookies for /subscriptions endpoint (mimics B&O device behavior)
            if resource_path == "subscriptions":
                # Get the authenticated username from the request (set by auth middleware)
                username = request.get('authenticated_user')
                if username:
                    # Create session if not already present
                    if "session" not in request.cookies:
                        session_id = create_session(username)
                        response.headers.add("Set-Cookie", f"session={session_id}; Path=/; HttpOnly")

                    # Set whoami cookie with format: <user_id>,<usertype>,<username>
                    # usertype must be: admin, manager, or common
                    response.headers.add("Set-Cookie", f"whoami=301,admin,{username}; Path=/")

            elapsed = time.perf_counter() - start_time
            if elapsed > _TIMING_THRESHOLD:
                _LOGGER.warning("model_api(%s) static file took %.1fms", resource_path, elapsed * 1000)
            return response

        # Handle dynamically generated endpoints
        if resource_path == "zones":
            zones_data, _ = await self._generate_zones_and_areas()
            elapsed = time.perf_counter() - start_time
            if elapsed > _TIMING_THRESHOLD:
                _LOGGER.warning("model_api(zones) took %.1fms", elapsed * 1000)
            return web.Response(
                body=jsonpickle.encode(zones_data, unpicklable=False),
                content_type="application/json",
                charset="UTF-8",
            )

        if resource_path == "areas":
            _, areas_data = await self._generate_zones_and_areas()
            elapsed = time.perf_counter() - start_time
            if elapsed > _TIMING_THRESHOLD:
                _LOGGER.warning("model_api(areas) took %.1fms", elapsed * 1000)
            return web.Response(
                body=jsonpickle.encode(areas_data, unpicklable=False),
                content_type="application/json",
                charset="UTF-8",
            )

        if resource_path == "cameras":
            cameras_data = await self._generate_cameras()
            elapsed = time.perf_counter() - start_time
            if elapsed > _TIMING_THRESHOLD:
                _LOGGER.warning("model_api(cameras) took %.1fms", elapsed * 1000)
            return web.Response(
                body=jsonpickle.encode(cameras_data, unpicklable=False),
                content_type="application/json",
                charset="UTF-8",
            )

        if resource_path == "addressables":
            addressables_data = await self._generate_addressables()
            elapsed = time.perf_counter() - start_time
            if elapsed > _TIMING_THRESHOLD:
                _LOGGER.warning("model_api(addressables) took %.1fms", elapsed * 1000)
            return web.Response(
                body=jsonpickle.encode(addressables_data, unpicklable=False),
                content_type="application/json",
                charset="UTF-8",
            )

        if resource_path == "states":
            states_data = await self._generate_states()
            elapsed = time.perf_counter() - start_time
            if elapsed > _TIMING_THRESHOLD:
                _LOGGER.warning("model_api(states) took %.1fms", elapsed * 1000)
            return web.Response(
                body=jsonpickle.encode(states_data, unpicklable=False),
                content_type="application/json",
                charset="UTF-8",
            )

        # If file doesn't exist, return 404
        elapsed = time.perf_counter() - start_time
        if elapsed > _TIMING_THRESHOLD:
            _LOGGER.warning("model_api(%s) 404 took %.1fms", resource_path, elapsed * 1000)
        _LOGGER.debug("Unknown model API path requested: /a/model/%s", resource_path)
        return web.Response(
            text=json.dumps({"error": f"Resource not found: {resource_path}"}),
            content_type="application/json",
            status=404,
        )

    def _find_entity_by_name(self, entity_name: str, resource_type: str) -> tuple[str | None, str | None]:
        """Find entity ID and domain by entity name and resource type.

        Returns:
            Tuple of (entity_id, domain) or (None, None) if not found.
        """
        # Map resource type to Home Assistant domain
        type_to_domain = {
            "SHADE": COVER_DOMAIN,
            "DIMMER": LIGHT_DOMAIN,
            "THERMOSTAT_1SP": CLIMATE_DOMAIN,
            "ALARM": ALARM_DOMAIN,
            "AV renderer": MEDIA_PLAYER_DOMAIN,
        }

        domain = type_to_domain.get(resource_type)
        if domain is None:
            return None, None

        # Search through entities of the matching domain
        states = self.hass.states.async_all()
        for state in states:
            if state.domain == domain and state.name == entity_name:
                return state.entity_id, domain

        return None, None

    async def execute_command(self, request: web.Request) -> web.Response:
        """Handle /a/exe/{area}/{zone}/{type}/{resource}/{command} requests.

        Executes commands on Home Assistant entities via the BeoLink webpanel.
        The frontend sends parameters as URL query params (e.g., ?LEVEL=50).
        """
        area = unquote(request.match_info.get("area", ""))
        zone = unquote(request.match_info.get("zone", ""))
        resource_type = unquote(request.match_info.get("type", ""))
        resource_name = unquote(request.match_info.get("resource", ""))
        command = unquote(request.match_info.get("command", ""))

        _LOGGER.debug(
            "Execute command: area=%s, zone=%s, type=%s, resource=%s, command=%s, query=%s",
            area, zone, resource_type, resource_name, command, dict(request.query)
        )

        # Handle MACRO type separately (scenes don't use _find_entity_by_name)
        if resource_type == "MACRO":
            try:
                await self._execute_macro_command(command, resource_name)
                return web.Response(
                    text=json.dumps({"status": "ok"}),
                    content_type="application/json",
                )
            except Exception as err:
                _LOGGER.exception("Error executing macro %s", resource_name)
                return web.Response(
                    text=json.dumps({"error": str(err)}),
                    content_type="application/json",
                    status=500,
                )

        # Find the entity for non-macro resource types
        entity_id, _domain = self._find_entity_by_name(resource_name, resource_type)
        if entity_id is None:
            _LOGGER.warning("Entity not found: %s (type: %s)", resource_name, resource_type)
            return web.Response(
                text=json.dumps({"error": f"Entity not found: {resource_name}"}),
                content_type="application/json",
                status=404,
            )

        # Get parameters from URL query string (Angular $http sends params as query params)
        params = dict(request.query)

        # Also parse any parameters embedded in the command path (legacy format)
        command_name = command
        if "?" in command:
            command_name, query_string = command.split("?", 1)
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

        service_data = {ATTR_ENTITY_ID: entity_id}

        try:
            if resource_type == "SHADE":
                await self._execute_shade_command(command_name, params, service_data)
            elif resource_type == "DIMMER":
                await self._execute_dimmer_command(command_name, params, service_data)
            elif resource_type == "THERMOSTAT_1SP":
                await self._execute_thermostat_command(command_name, params, service_data)
            else:
                _LOGGER.warning("Unsupported resource type: %s", resource_type)
                return web.Response(
                    text=json.dumps({"error": f"Unsupported resource type: {resource_type}"}),
                    content_type="application/json",
                    status=400,
                )

            return web.Response(
                text=json.dumps({"status": "ok"}),
                content_type="application/json",
            )
        except Exception as err:
            _LOGGER.exception("Error executing command %s on %s", command_name, entity_id)
            return web.Response(
                text=json.dumps({"error": str(err)}),
                content_type="application/json",
                status=500,
            )

    async def _execute_shade_command(
        self,
        command: str,
        params: dict,
        service_data: dict,
    ) -> None:
        """Execute shade (cover) commands."""
        service = None

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
            await self.hass.services.async_call(
                COVER_DOMAIN, service, service_data
            )

    async def _execute_dimmer_command(
        self,
        command: str,
        params: dict,
        service_data: dict,
    ) -> None:
        """Execute dimmer (light) commands."""
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

        await self.hass.services.async_call(
            LIGHT_DOMAIN, SERVICE_TURN_ON, service_data
        )

    async def _execute_thermostat_command(
        self,
        command: str,
        params: dict,
        service_data: dict,
    ) -> None:
        """Execute thermostat (climate) commands."""
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

    async def _execute_macro_command(
        self,
        command: str,
        macro_name: str,
    ) -> None:
        """Execute macro (HA scene) commands.

        Macros in BeoLink map to Home Assistant scenes. When the user taps
        a scene in the BeoLiving app, it sends a FIRE command.
        """
        if command != "FIRE":
            _LOGGER.warning("Unsupported macro command: %s", command)
            return

        # Find the scene by its friendly name using helper
        scene_state = find_scene_by_name(self.hass, macro_name)
        if scene_state:
            _LOGGER.debug("Firing scene %s (entity: %s)", macro_name, scene_state.entity_id)
            await self.hass.services.async_call(
                SCENE_DOMAIN,
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: scene_state.entity_id},
            )
        else:
            _LOGGER.warning("Scene not found for macro: %s", macro_name)

    async def catch_all_handler(self, request: web.Request) -> web.Response:
        """Handle all unmatched routes and log them as errors."""
        _LOGGER.debug(
            "Unknown route requested: %s %s",
            request.method,
            request.path,
        )
        return web.Response(
            text=json.dumps({"error": "Route not found"}),
            content_type="application/json",
            status=404,
        )

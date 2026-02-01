"""BeoLink Gateway integration for Home Assistant."""
import asyncio

from aiohttp import web

from homeassistant import config_entries, core
from homeassistant.components import zeroconf
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.helpers import instance_id
from homeassistant.helpers.entityfilter import (
    CONF_EXCLUDE_ENTITIES,
    CONF_INCLUDE_ENTITIES,
)

from .blgwserver import BLGWServer, CustomBasicAuth
from .const import CONF_INCLUDE_EXCLUDE_MODE, CONF_SERIAL_NUMBER, DOMAIN
from .hipserver import HIPServer
from .zeroconf_services import (
    BeoLinkServiceConfig,
    create_hip_service_info,
    create_tvpanel_service_info,
    get_local_ip,
)

# Default ports
DEFAULT_HTTP_PORT = 80
DEFAULT_HIP_PORT = 9100


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up BeoLink from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    http_port = entry.options.get(CONF_PORT, DEFAULT_HTTP_PORT)

    # Start HIP server
    loop = asyncio.get_running_loop()
    hipserver = await loop.create_server(
        lambda: HIPServer(
            entry.options[CONF_INCLUDE_ENTITIES],
            entry.options[CONF_EXCLUDE_ENTITIES],
            entry.options[CONF_INCLUDE_EXCLUDE_MODE],
            hass,
        ),
        None,
        DEFAULT_HIP_PORT,
    )

    # Start HTTP server
    auth = CustomBasicAuth(hass.auth.auth_providers)
    server = BLGWServer(
        entry.options[CONF_NAME],
        entry.options[CONF_SERIAL_NUMBER],
        entry.options[CONF_INCLUDE_ENTITIES],
        entry.options[CONF_EXCLUDE_ENTITIES],
        entry.options[CONF_INCLUDE_EXCLUDE_MODE],
        hass,
    )
    app = web.Application(middlewares=[auth])
    app.router.add_routes([
        web.get('/blgwpservices.json', server.blgwpservices),
        web.get('/a/view/House/{zone}/CAMERA/{camera_name}/mjpeg', server.camera_mjpeg),
        web.get('/a/webview/{area}/{zone}/CAMERA/{camera_name}/snapshot',
                server.camera_snapshot),
        web.get('/a/exe/{area}/{zone}/{type}/{resource}/{command}',
                server.execute_command),
        web.get('/a/model/{resource:.*}', server.model_api),
        web.post('/a/model/{resource:.*}', server.model_api),
        web.put('/a/model/{resource:.*}', server.model_api),
        web.get('/webpanel/', server.webpanel_index_html),
        web.get('/webpanel/index.html', server.webpanel_index_html),
        web.get('/webpanel/index.xhtml', server.webpanel_index),
        web.get('/webpanel/{resource:.*}', server.webpanel_static),
        web.get('/common/{resource:.*}', server.common_static),
        web.route('*', '/{path:.*}', server.catch_all_handler),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, None, http_port)
    await site.start()

    # Store servers for cleanup
    hass.data[DOMAIN][entry.entry_id] = {
        'BLGWServer': site,
        'HIPServer': hipserver,
        'zeroconf_services': [],
    }

    # Register zeroconf services
    zeroconf_instance = await zeroconf.async_get_instance(hass)
    uuid = await instance_id.async_get(hass)
    local_address = get_local_ip()

    service_config = BeoLinkServiceConfig(
        name=entry.options[CONF_NAME],
        serial_number=str(entry.options[CONF_SERIAL_NUMBER]),
        host=local_address,
        port=http_port,
        hip_port=DEFAULT_HIP_PORT,
        instance_id=uuid,
        register_tvpanel=True,
    )

    # Register HIP service (main BLGW discovery service)
    hip_service = create_hip_service_info(service_config)
    await zeroconf_instance.async_register_service(hip_service, allow_name_change=True)
    hass.data[DOMAIN][entry.entry_id]['zeroconf_services'].append(hip_service)

    # Register TV panel service (for B&O TVs to discover webpanel)
    tvpanel_service = create_tvpanel_service_info(service_config)
    await zeroconf_instance.async_register_service(
        tvpanel_service, allow_name_change=True
    )
    hass.data[DOMAIN][entry.entry_id]['zeroconf_services'].append(tvpanel_service)

    return True


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the BeoLink component."""
    return True


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    # Unregister zeroconf services
    zeroconf_instance = await zeroconf.async_get_instance(hass)
    for service in hass.data[DOMAIN][entry.entry_id].get('zeroconf_services', []):
        await zeroconf_instance.async_unregister_service(service)

    # Stop HTTP server
    site: web.TCPSite = hass.data[DOMAIN][entry.entry_id]['BLGWServer']
    await site.stop()

    # Stop HIP server
    hipserver: asyncio.Server = hass.data[DOMAIN][entry.entry_id]['HIPServer']
    hipserver.close()
    await hipserver.wait_closed()

    # Clean up hass.data
    hass.data[DOMAIN].pop(entry.entry_id)

    return True

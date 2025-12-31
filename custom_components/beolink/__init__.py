"""Module for casting objects."""
import asyncio
import socket
import time

from aiohttp import web
from zeroconf import ServiceInfo

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


async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Set up BeoLink from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    loop = asyncio.get_running_loop()
    hipserver = await loop.create_server(lambda: HIPServer(entry.options[CONF_INCLUDE_ENTITIES],entry.options[CONF_EXCLUDE_ENTITIES],entry.options[CONF_INCLUDE_EXCLUDE_MODE],hass), None, 9100)

    auth = CustomBasicAuth(hass.auth.auth_providers)
    server = BLGWServer(entry.options[CONF_NAME],entry.options[CONF_SERIAL_NUMBER],entry.options[CONF_INCLUDE_ENTITIES],entry.options[CONF_EXCLUDE_ENTITIES],entry.options[CONF_INCLUDE_EXCLUDE_MODE], hass)
    app = web.Application(middlewares=[auth])
    app.router.add_routes( [web.get('/blgwpservices.json', server.blgwpservices),web.get('/a/view/House/{zone}/CAMERA/{camera_name}/mjpeg', server.camera_mjpeg)] )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite( runner, None, entry.options.get( CONF_PORT, 80))
    await site.start()

    hass.data[DOMAIN][entry.entry_id] = {'BLGWServer' : site, 'HIPServer' : hipserver}

    zeroconf_instance = await zeroconf.async_get_instance(hass)

    uuid = await instance_id.async_get(hass)

    desc = {
        "hipport": "9100",
        "path": "/blgwpservices.json",
        "project": entry.options[CONF_NAME],
        "protover": "2",
        "sn": entry.options[CONF_SERIAL_NUMBER],
        "swver": "1.5.4.557",
        "timestamp": int(time.time()),
    }

    local_address = get_local_address()

    info = ServiceInfo(
        "_hipservices._tcp.local.",
        "BLGW (blgw) | "+entry.options[CONF_NAME]+"._hipservices._tcp.local.",
        addresses=[socket.inet_aton(local_address)],
        port=80,
        properties=desc,
        server= uuid+".local.",
    )

    await zeroconf_instance.async_register_service(info, allow_name_change=True)

    # Store service info for cleanup
    hass.data[DOMAIN][entry.entry_id]['zeroconf_info'] = info

    return True


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the BeoLink component."""
    # @TODO: Add setup code.
    return True


async def async_unload_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unregister zeroconf service
    zeroconf_instance = await zeroconf.async_get_instance(hass)
    info = hass.data[DOMAIN][entry.entry_id].get('zeroconf_info')
    if info:
        await zeroconf_instance.async_unregister_service(info)

    site: web.TCPSite = hass.data[DOMAIN][entry.entry_id]['BLGWServer']
    await site.stop()
    hipserver: asyncio.Server = hass.data[DOMAIN][entry.entry_id]['HIPServer']
    hipserver.close()
    await hipserver.wait_closed()

    # Clean up hass.data
    hass.data[DOMAIN].pop(entry.entry_id)

    return True

def get_local_address() -> str:
    """Grabs the local IP address using a socket.

    :return: Local IP Address in IPv4 format.
    :rtype: str
    """
    # TODO: try not to talk 8888 for this
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        addr = s.getsockname()[0]
    finally:
        s.close()
    return str(addr)

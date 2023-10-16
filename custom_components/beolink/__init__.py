"""Module for casting objects"""
from typing import cast
import time

import asyncio

import socket

from zeroconf.asyncio import ServiceInfo

from homeassistant import config_entries, core

from homeassistant.components import zeroconf

from homeassistant.helpers import instance_id

from homeassistant.auth.providers.homeassistant import HassAuthProvider

from .hipserver import HIPServer

from .blgwserver import CustomBasicAuth, BLGWServer

from .const import DOMAIN, CONF_BEOLINK_NAME, CONF_SERIAL_NUMBER, CONF_BLGW_SERVER_PORT

from aiohttp import web

async def async_setup_entry( hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Set up BeoLink from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: HIPServer(hass), None, 9100)

    providers = hass.auth.auth_providers
    auth = CustomBasicAuth(cast(HassAuthProvider, providers[0]))
    server = BLGWServer(entry.data[CONF_BEOLINK_NAME],entry.data[CONF_SERIAL_NUMBER],hass)
    app = web.Application(middlewares=[auth])
    app.router.add_routes( [web.get('/blgwpservices.json', server.blgwpservices),web.get('/a/view/House/{zone}/CAMERA/{camera_name}/mjpeg', server.camera_mjpeg)] )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite( runner, None, entry.data.get( CONF_BLGW_SERVER_PORT, 80))
    await site.start()

    zeroconf_instance = await zeroconf.async_get_instance(hass)

    uuid = await instance_id.async_get(hass)

    desc = {
        "hipport": "9100",
        "path": "/blgwpservices.json",
        "project": entry.data[CONF_BEOLINK_NAME],
        "protover": "2",
        "sn": entry.data[CONF_SERIAL_NUMBER],
        "swver": "1.5.4.557",
        "timestamp": int(time.time()),
    }

    local_address = get_local_address()

    info = ServiceInfo(
        "_hipservices._tcp.local.",
        "BLGW (blgw) | "+entry.data[CONF_BEOLINK_NAME]+"._hipservices._tcp.local.",
        addresses=[socket.inet_aton(local_address)],
        port=80,
        properties=desc,
        server= uuid+".local.",
    )

    await zeroconf_instance.async_register_service(info, allow_name_change=True)

    return True


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the BeoLink component."""
    # @TODO: Add setup code.
    return True

def get_local_address() -> str:
    """
    Grabs the local IP address using a socket.

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
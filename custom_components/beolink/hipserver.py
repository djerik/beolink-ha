"""Module for handling the tcp communication"""
import asyncio
from urllib.parse import unquote
from typing import Any, cast

from homeassistant import core
from homeassistant.core import Context
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er)

from homeassistant.helpers.device_registry import (  DeviceEntry )

from homeassistant.components.cover import ( DOMAIN as COVER_DOMAIN, CoverDeviceClass )

from homeassistant.components.light import ( DOMAIN as LIGHT_DOMAIN, ATTR_BRIGHTNESS_PCT )

from homeassistant.components.climate import ( DOMAIN as CLIMATE_DOMAIN )

from homeassistant.auth.providers.homeassistant import HassAuthProvider, InvalidAuth

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
    SERVICE_TURN_ON
)

class HIPServer(asyncio.Protocol):
    """Server handling the HIP protocol"""
    state = "awaiting user"
    def __init__(self, hass: core.HomeAssistant) -> None:
        self.hass = hass
        self.provider = cast(HassAuthProvider, self.hass.auth.auth_providers[0])
        self.user = ''
        self.transport = None
        ent_reg = er.async_get(self.hass)
        dr_reg = dr.async_get(self.hass)

        self.device_lookup = ent_reg.async_get_device_class_lookup(
            {
                (COVER_DOMAIN,  CoverDeviceClass.BLIND),
                (LIGHT_DOMAIN, None)
            }
        )
        self.devices : dict[ str, DeviceEntry] = {}
        for device_id in self.device_lookup:
            device = dr_reg.async_get(device_id)
            self.devices[device.name] = device

    def connection_made(self, transport):
        self.transport = transport
        self.send(b"login: ")

    async def check_login(self, username, password):
        """Checking login againts Home Assistant"""
        try:
            await self.provider.async_validate_login(username, password)
        except InvalidAuth:
            return False
        self.state = "authenticated"
        self.send(b"\r\n")

    def data_received(self, data):
        if self.state == "awaiting user":
            self.user = data.decode()
            self.state = "awaiting password"
            self.send(b"\r\npassword: ")
        elif self.state == "awaiting password":
            password = data.decode().splitlines()[0]
            self.hass.loop.create_task( self.check_login(self.user, password))
        else:
            lines = data.decode().splitlines()
            for line in lines:
                print(line)
                if line == "f":
                    self.send_ok_line("f")
                if line == "q */*/*/*" or line == "q":
                    self.send_ok_line("q */*/*/*")
                if line == "f */*/*/*":
                    self.send_ok_line("f */*/*/*")
                if line == "c Main/global/SYSTEM/BLI/CHECK%20FIRMWARE":
                    self.send_ok_line("c Main/global/SYSTEM/BLI/CHECK FIRMWARE")
                    self.send_response_line("Main/global/SYSTEM/BLGW/STATE_UPDATE?CURRENT%20FIRMWARE=1.5.4.557&LATEST%20FIRMWARE=&ROLLBACK%20AVAILABLE=1.5.4.533_2023.01.31-22.01.55&SYSTEM%20INFO=READY&revision=39")
                    #self.send_state_line("House/Kitchen/THERMOSTAT_1SP/Room 1/STATE_UPDATE?TEMPERATURE=20")
                    #self.send_state_line("House/Kitchen/THERMOSTAT_1SP/Room 1/STATE_UPDATE?SETPOINT=21")
                    #self.send_state_line("House/Kitchen/THERMOSTAT_1SP/Room 1/STATE_UPDATE?MODE=Auto")
                    #self.send_state_line("House/Kitchen/THERMOSTAT_1SP/Room 1/STATE_UPDATE?FAN AUTO=true")
                elif str(line).startswith("c "):
                    command = line.split('/')
                    action = command[4]
                    device_name = unquote(command[3])
                    device_type = command[2]
                    device = self.devices[device_name]
                    if device_type == "SHADE":
                        entity_id = self.device_lookup[device.id][(COVER_DOMAIN,  CoverDeviceClass.BLIND)]
                        params = {ATTR_ENTITY_ID: entity_id}
                        if action == "RAISE":
                            self.async_call_service(device.id, device.name, COVER_DOMAIN, SERVICE_OPEN_COVER, params)
                        elif action == "LOWER":
                            self.async_call_service(device.id, device.name, COVER_DOMAIN, SERVICE_CLOSE_COVER, params)
                        elif action == "STOP":
                            self.async_call_service(device.id, device.name, COVER_DOMAIN, SERVICE_STOP_COVER, {ATTR_ENTITY_ID: entity_id} )
                    elif device_type == "DIMMER":
                        entity_id = self.device_lookup[device.id][(LIGHT_DOMAIN, None)]
                        parameters = str(action).split('?')
                        parameter = parameters[0]
                        value = parameters[1].split('=')[1]
                        if( parameter == "SET"):
                            params = {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS_PCT:value }
                            self.async_call_service(device.id, device.name, LIGHT_DOMAIN, SERVICE_TURN_ON, params )
                    elif device_type == "THERMOSTAT_1SP":
                        entity_id = self.device_lookup[device.id][(CLIMATE_DOMAIN, None)]
                    self.send_ok_line("c ")

    def send(self, data):
        """Low level send method"""
        self.transport.write(data)

    def send_ok_line(self, string: str):
        """Send OK response"""
        self.send( ("e OK " + self.percent_encoding(string) + "\r\n").encode(encoding="ascii") )

    def send_response_line(self, string: str):
        """Send state response"""
        self.send(("r " + self.percent_encoding(string) + "\r\n").encode(encoding="ascii"))

    def send_state_line(self, string: str):
        """Send state update"""
        print("s " + self.percent_encoding(str) + "\r\n")
        self.send(("s " + self.percent_encoding(string) + "\r\n").encode(encoding="ascii"))

    def percent_encoding(self, string: str):
        """Handles percent encoding"""
        result = ""
        accepted = [
            c
            for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~/?=&".encode(
                encoding="ascii"
            )
        ]
        for char in string.encode(encoding="ascii"):
            result += (
                chr(char) if char in accepted else "%{}".format(hex(char)[2:]).upper()
            )
        return result

    def async_call_service(
        self,
        entity_id,
        display_name,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None,
        value: Any | None = None,
    ) -> None:
        """Fire event and call service for changes from Be."""
        event_data = {
            ATTR_ENTITY_ID: entity_id,
            display_name: display_name,
            ATTR_SERVICE: service,
            value: value,
        }
        context = Context()

        self.hass.bus.async_fire('beolink_state_change', event_data, context=context)
        self.hass.async_create_task(
            self.hass.services.async_call(
                domain, service, service_data, context=context
            )
        )

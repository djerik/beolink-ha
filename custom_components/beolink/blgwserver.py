"""Module for returning data formatted in json"""
import jsonpickle
from .model.blgwpwebservices import Zone, Area, blgwpwebservices

from homeassistant.auth.providers.homeassistant import HassAuthProvider, InvalidAuth

from homeassistant import core

from homeassistant.helpers import (
    device_registry as dr,
    area_registry as ar)

from homeassistant.components.cover import ( DOMAIN as COVER_DOMAIN )
from homeassistant.components.light import ( DOMAIN as LIGHT_DOMAIN )
from homeassistant.components.camera import ( DOMAIN as CAMERA_DOMAIN )

from aiohttp import web, MultipartWriter
from aiohttp_basicauth import BasicAuthMiddleware

class CustomBasicAuth(BasicAuthMiddleware):
    """Class for handlig authentication against Home Assistant users"""

    def __init__(self, provider: HassAuthProvider) -> None:
        self.provider = provider
        super().__init__()

    async def check_credentials(self, username, password, request):
        try:
            await self.provider.async_validate_login(username, password)
            return True
        except InvalidAuth:
            return False

class BLGWServer:
    """Handles BLGW HTTP requests"""
    def __init__(self, name, serial_number, hass: core.HomeAssistant) -> None:
        self.hass = hass
        self.name = name
        self.serial_number = serial_number

    async def camera_mjpeg(self, request ):
        """ Handles a mjpeg stream"""
        boundary = "myboundary"
        response = web.StreamResponse(status=200, reason='OK', headers={
            'Content-Type': 'multipart/x-mixed-replace; '
                            'boundary=%s'% boundary,
        })
        await response.prepare(request)
        states = self.hass.states.async_all()
        camera_state = next(x for x in states if x.attributes["friendly_name"] == request.match_info['camera_name'])
        camera = self.hass.data["camera"].get_entity(camera_state.entity_id)

        while True:
            image_cb = await camera.async_camera_image()
            with MultipartWriter('image/jpeg', boundary=boundary) as mpwriter:
                mpwriter.append(image_cb, {
                    'Content-Type': 'image/jpeg'
                })
                await mpwriter.write(response, close_boundary=False)
            await response.drain()


    async def blgwpservices(self, request):
        """ Handles the blgwpservices.json retult """
        dr_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        bl_areas : dict[str, Area] = {}
        bl_zones : dict[str, Zone] = {}
        bl_ressources : dict[str, dict[str, object]] = {}

        states = self.hass.states.async_all()
        for state in states:
            if state.domain in {"cover","light","camera","climate"}:
                entity = self.hass.data[state.domain].get_entity(state.entity_id)
                if( entity is None):
                    continue
                area_id = entity.registry_entry.area_id
                if area_id is None:
                    device = dr_reg.async_get(entity.registry_entry.device_id)
                    if( device is None ):
                        continue
                    area_id = device.area_id
                    if( area_id is None):
                        continue
                if area_id not in bl_zones:
                    area = area_reg.async_get_area(area_id)
                    if( area is None):
                        continue
                    bl_zones[area_id] = Zone(area.name, "house", False, False, {})
                    bl_ressources[area_id] = {}
                if( state.domain == COVER_DOMAIN ):
                    shade = {   "type" : "SHADE",
                                    "name": state.attributes["friendly_name"],
                                    "id": entity.entity_id,
                                    "systemAddress": "HomeAssistant",
                                    "hide": False,
                                    "commands": ["LOWER", "RAISE", "STOP"],
                                    "events": []
                            }
                    bl_ressources[area_id][state.entity_id] = shade
                if( state.domain == LIGHT_DOMAIN ):
                    dimmer = {   "type" : "DIMMER",
                                    "name": state.attributes["friendly_name"],
                                    "id": entity.entity_id,
                                    "systemAddress": "HomeAssistant",
                                    "hide": False,
                                    "commands": ["SET", "SET COLOR"],
                                    "events": []
                            }
                    bl_ressources[area_id][state.entity_id] = dimmer
                if( state.domain == CAMERA_DOMAIN ):
                    camera = {
                                "type": "CAMERA",
                                "name": state.attributes["friendly_name"],
                                "rtspSupport": False,
                                "commands": []
                             }
                    bl_ressources[area_id][state.entity_id] = camera

        for bl_zone_key, bl_zone in bl_zones.items():
            sorted_resources = list(bl_ressources[bl_zone_key].values())
            sorted_resources.sort(key=lambda x: x.get('name'))
            bl_zone.resources = sorted_resources

        house_area = Area("House")
        sorted_zones = list(bl_zones.values())
        sorted_zones.sort( key=lambda x: x.name)
        house_area.zones = sorted_zones
        bl_areas["House"] = house_area

        main_zone = Zone("global", "house", True, False, [])
        main_area = Area("Main")
        main_area.zones = {main_zone}
        bl_areas["main"] = main_area

        data = blgwpwebservices(self.name, self.serial_number,list(bl_areas.values()))

        return web.Response(body=jsonpickle.encode(data, unpicklable=False))
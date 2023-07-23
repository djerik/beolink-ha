import time

class Installer(object):
    def __init__(self) -> None:
        self.name = ""
        self.contact = ""


class Zone(object):
    def __init__(self, name, icon, special, forbidden, resources) -> None:
        self.name = name
        self.icon = icon
        self.special = special
        self.forbidden = forbidden
        self.resources = resources

class Area(object):
    def __init__(self, name ) -> None:
        self.name = name

class blgwpwebservices(object):
    def __init__(self, name, serial_number, areas) -> None:
        self.timestamp = int(time.time())
        self.port = 9100
        self.sn = serial_number
        self.project = name
        self.installer = Installer()
        self.version = 2
        self.fwversion = "1.5.4.557"
        self.units = {"temperature": "C"}
        self.macroEdition = True
        self.location = {
            "centerlat": 0,
            "centerlon": 0,
            "radius": 0,
            "handler": "Main/global/SYSTEM/BLGW"
            #ToDo
        }
        self.areas = areas

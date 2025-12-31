"""Data models for BLGW web services."""

import time
from typing import Any


class Installer:
    """Installer information."""

    def __init__(self) -> None:
        """Initialize installer."""
        self.name: str = ""
        self.contact: str = ""


class Zone:
    """Zone representation."""

    def __init__(
        self,
        name: str,
        icon: str,
        special: bool,
        forbidden: bool,
        resources: list[dict[str, Any]],
    ) -> None:
        """Initialize zone."""
        self.name: str = name
        self.icon: str = icon
        self.special: bool = special
        self.forbidden: bool = forbidden
        self.resources: list[dict[str, Any]] = resources


class Area:
    """Area representation."""

    def __init__(self, name: str, zones: list[Zone]) -> None:
        """Initialize area."""
        self.name: str = name
        self.zones: list[Zone] = zones


class blgwpwebservices:
    """BLGW web services representation."""

    def __init__(self, name: str, serial_number: str, areas: list[Area]) -> None:
        """Initialize BLGW web services."""
        self.timestamp: int = int(time.time())
        self.port: int = 9100
        self.sn: str = serial_number
        self.project: str = name
        self.installer: Installer = Installer()
        self.version: int = 2
        self.fwversion: str = "1.5.4.557"
        self.units: dict[str, str] = {"temperature": "C"}
        self.macroEdition: bool = True
        self.location: dict[str, Any] = {
            "centerlat": 0,
            "centerlon": 0,
            "radius": 0,
            "handler": "Main/global/SYSTEM/BLGW",
        }
        self.areas: list[Area] = areas

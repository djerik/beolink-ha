"""Zeroconf service definitions for BeoLink integration.

This module provides shared zeroconf service creation logic used by
the Home Assistant integration.

Services:
- _hipservices._tcp.local. - Main BLGW service for HIP protocol
- _hatvpanel._tcp.local. - TV panel webview service
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass

from zeroconf import ServiceInfo

# Service type constants
SERVICE_TYPE_HIP = "_hipservices._tcp.local."
SERVICE_TYPE_TVPANEL = "_hatvpanel._tcp.local."

# Default values
DEFAULT_SWVER = "1.5.4.557"
DEFAULT_TVPANEL_PATH = "/webpanel/index.xhtml"


@dataclass
class BeoLinkServiceConfig:
    """Configuration for BeoLink zeroconf services."""

    name: str
    serial_number: str
    host: str
    port: int
    hip_port: int
    instance_id: str
    register_tvpanel: bool = True
    tvpanel_path: str = DEFAULT_TVPANEL_PATH


def get_local_ip() -> str:
    """Get local IP address by connecting to external server.

    Returns:
        Local IP address as string.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        addr = s.getsockname()[0]
    except OSError:
        addr = "127.0.0.1"
    finally:
        s.close()
    return addr


def create_hip_service_info(config: BeoLinkServiceConfig) -> ServiceInfo:
    """Create ServiceInfo for the HIP services (main BLGW service).

    This is the primary service that Bang & Olufsen devices use to discover
    the BeoLink Gateway.

    Args:
        config: Service configuration.

    Returns:
        ServiceInfo for the HIP service.
    """
    properties = {
        "hipport": str(config.hip_port),
        "path": "/blgwpservices.json",
        "project": config.name,
        "protover": "2",
        "sn": str(config.serial_number),
        "swver": DEFAULT_SWVER,
        "timestamp": str(int(time.time())),
    }

    service_name = f"BLGW (blgw) | {config.name}.{SERVICE_TYPE_HIP}"

    return ServiceInfo(
        SERVICE_TYPE_HIP,
        service_name,
        addresses=[socket.inet_aton(config.host)],
        port=config.port,
        properties=properties,
        server=f"{config.instance_id}.local.",
    )


def create_tvpanel_service_info(config: BeoLinkServiceConfig) -> ServiceInfo:
    """Create ServiceInfo for the TV panel service.

    This service allows Bang & Olufsen TVs to discover and display
    the webpanel interface.

    Args:
        config: Service configuration.

    Returns:
        ServiceInfo for the TV panel service.
    """
    properties = {
        "tv_path": config.tvpanel_path,
    }

    service_name = f"BLGW (blgw) | {config.name}.{SERVICE_TYPE_TVPANEL}"

    return ServiceInfo(
        SERVICE_TYPE_TVPANEL,
        service_name,
        addresses=[socket.inet_aton(config.host)],
        port=config.port,
        properties=properties,
        server=f"{config.instance_id}.local.",
    )

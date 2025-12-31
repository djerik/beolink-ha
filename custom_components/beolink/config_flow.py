"""Config flow."""
from __future__ import annotations

import random
from typing import Any

import voluptuous as vol

from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_DOMAIN
from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.remote import DOMAIN as REMOTE_DOMAIN
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import ATTR_FRIENDLY_NAME, CONF_DOMAINS, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.entityfilter import (
    CONF_EXCLUDE_ENTITIES,
    CONF_INCLUDE_ENTITIES,
)
from homeassistant.loader import async_get_integrations

from .const import (
    CONF_INCLUDE_EXCLUDE_MODE,
    CONF_SERIAL_NUMBER,
    DOMAIN,
    MODE_EXCLUDE,
    MODE_INCLUDE,
)

INCLUDE_EXCLUDE_MODES = [MODE_EXCLUDE, MODE_INCLUDE]

BEOLINK_CREATE_SCHEMA = vol.Schema({vol.Required(CONF_NAME, default="BLGW"): str, vol.Required(CONF_PORT, default=80): int})

SUPPORTED_DOMAINS = [
    ALARM_DOMAIN,
    CAMERA_DOMAIN,
    CLIMATE_DOMAIN,
    COVER_DOMAIN,
    LIGHT_DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    REMOTE_DOMAIN,
]

DEFAULT_DOMAINS = [
    ALARM_DOMAIN,
    CLIMATE_DOMAIN,
    CAMERA_DOMAIN,
    COVER_DOMAIN,
    LIGHT_DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    REMOTE_DOMAIN,
]

class BeoLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""

    data: dict[str, Any] | None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """User initiated a flow via the user interface."""
        if user_input is not None:
            self.data = user_input
            self.data[CONF_SERIAL_NUMBER] = random.randrange(24000000, 25000000)
            self.data[CONF_DOMAINS] = DEFAULT_DOMAINS
            self.data[CONF_INCLUDE_ENTITIES] = {}
            self.data[CONF_EXCLUDE_ENTITIES] = {}
            self.data[CONF_INCLUDE_EXCLUDE_MODE] = MODE_EXCLUDE
            return self.async_create_entry(title="BeoLink", data={}, options=self.data )
        return self.async_show_form(
            step_id="user", data_schema=BEOLINK_CREATE_SCHEMA
        )

    @staticmethod
    @callback
    def async_get_options_flow( config_entry: ConfigEntry) -> BeoLinkOptionsFlowHandler:
        """Get the options flow for this handler."""
        return BeoLinkOptionsFlowHandler(config_entry)


class BeoLinkOptionsFlowHandler(OptionsFlow):
    """Handle BeoLink options."""

    bl_options: dict[str, Any]

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize BeoLink options flow."""
        # config_entry is automatically available via the base class property

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage BeoLink options."""
        # Initialize bl_options from config entry options
        self.bl_options = dict(self.config_entry.options)

        if user_input is not None:
            #return self.async_create_entry(title="BeoLink", data=user_input)
            self.bl_options.update(user_input)
            if user_input[CONF_INCLUDE_EXCLUDE_MODE] == MODE_INCLUDE:
                return await self.async_step_include()
            return await self.async_step_exclude()
        name_to_type_map = await _async_name_to_type_map(self.hass)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=self.bl_options.get(CONF_NAME),
                    ): str,
                    vol.Required(CONF_PORT, default=self.bl_options.get(CONF_PORT)): int,
                    vol.Required(
                        CONF_INCLUDE_EXCLUDE_MODE, default=self.bl_options.get(CONF_INCLUDE_EXCLUDE_MODE)
                    ): vol.In(INCLUDE_EXCLUDE_MODES),
                    vol.Required(
                        CONF_DOMAINS, default=self.bl_options.get(CONF_DOMAINS)
                    ): cv.multi_select(name_to_type_map),
                }
            )
        )

    async def async_step_include(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose entities to include from the domain on the bridge."""
        domains = self.bl_options[CONF_DOMAINS]
        if user_input is not None:
            self.bl_options.update(user_input)
            return self.async_create_entry(title="BeoLink", data=self.bl_options)

        entities = self.bl_options.get(CONF_INCLUDE_ENTITIES, {})

        all_supported_entities = _async_get_matching_entities(
            self.hass, domains, include_entity_category=True, include_hidden=True
        )
        # Strip out entities that no longer exist to prevent error in the UI
        default_value = [
            entity_id for entity_id in entities if entity_id in all_supported_entities
        ]

        return self.async_show_form(
            step_id="include",
            description_placeholders={
                "domains": await _async_domain_names(self.hass, domains)
            },
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_INCLUDE_ENTITIES, default=default_value): cv.multi_select(
                        all_supported_entities
                    )
                }
            ),
        )

    async def async_step_exclude(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose entities to exclude from the domain on the bridge."""
        domains = self.bl_options[CONF_DOMAINS]

        if user_input is not None:
            self.bl_options.update(user_input)
            return self.async_create_entry(title="BeoLink", data=self.bl_options)

        entities = self.bl_options.get(CONF_EXCLUDE_ENTITIES, {})

        all_supported_entities = _async_get_matching_entities(self.hass, domains)

        # Strip out entities that no longer exist to prevent error in the UI
        default_value = [
            entity_id for entity_id in entities if entity_id in all_supported_entities
        ]

        return self.async_show_form(
            step_id="exclude",
            description_placeholders={
                "domains": await _async_domain_names(self.hass, domains)
            },
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_EXCLUDE_ENTITIES, default=default_value): cv.multi_select(
                        all_supported_entities
                    )
                }
            ),
        )


async def _async_domain_names(hass: HomeAssistant, domains: list[str]) -> str:
    """Build a list of integration names from domains."""
    name_to_type_map = await _async_name_to_type_map(hass)
    return ", ".join(
        [name for domain, name in name_to_type_map.items() if domain in domains]
    )


async def _async_name_to_type_map(hass: HomeAssistant) -> dict[str, str]:
    """Create a mapping of types of devices/entities BeoLink can support."""
    integrations = await async_get_integrations(hass, SUPPORTED_DOMAINS)
    return {
        domain: integration_or_exception.name
        if (integration_or_exception := integrations[domain])
        and not isinstance(integration_or_exception, Exception)
        else domain
        for domain in SUPPORTED_DOMAINS
    }

def _async_get_matching_entities(
    hass: HomeAssistant,
    domains: list[str] | None = None,
    include_entity_category: bool = False,
    include_hidden: bool = False,
) -> dict[str, str]:
    """Fetch all entities or entities in the given domains."""
    ent_reg = er.async_get(hass)
    return {
        state.entity_id: (
            f"{state.attributes.get(ATTR_FRIENDLY_NAME, state.entity_id)} ({state.entity_id})"
        )
        for state in sorted(
            hass.states.async_all(domains and set(domains)),
            key=lambda item: item.entity_id,
        )
        if not _exclude_by_entity_registry(
            ent_reg, state.entity_id, include_entity_category, include_hidden
        )
    }

def _exclude_by_entity_registry(
    ent_reg: er.EntityRegistry,
    entity_id: str,
    include_entity_category: bool,
    include_hidden: bool,
) -> bool:
    """Filter out hidden entities and ones with entity category (unless specified)."""
    return bool(
        (entry := ent_reg.async_get(entity_id))
        and (
            (not include_hidden and entry.hidden_by is not None)
            or (not include_entity_category and entry.entity_category is not None)
        )
    )

from __future__ import annotations

import random

from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback

import voluptuous as vol

from .const import DOMAIN, CONF_BEOLINK_NAME, CONF_SERIAL_NUMBER, CONF_BLGW_SERVER_PORT

BEOLINK_CREATE_SCHEMA = vol.Schema({vol.Required(CONF_BEOLINK_NAME,default="BLGW"): str, vol.Required(CONF_BLGW_SERVER_PORT,default=80): int})

class BeoLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    data: Optional[dict[str, Any]]

    async def async_step_user(self, user_input: Optional[dict[str, Any]] = None):
        """Invoked when a user initiates a flow via the user interface."""
        if user_input is not None:
            self.data = user_input
            self.data[CONF_SERIAL_NUMBER] = random.randrange(24000000, 25000000)
            return self.async_create_entry(title="BeoLink", data=self.data)
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

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize BeoLink options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage BeoLink options."""

        if user_input is not None:
            user_input[CONF_SERIAL_NUMBER] = self.config_entry.data[CONF_SERIAL_NUMBER]
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input, options=self.config_entry.options
            )
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BEOLINK_NAME,
                        default=self.config_entry.data.get(CONF_BEOLINK_NAME),
                    ): str, vol.Required(CONF_BLGW_SERVER_PORT,default=self.config_entry.data.get(CONF_BLGW_SERVER_PORT)): int
                }
            )
        )
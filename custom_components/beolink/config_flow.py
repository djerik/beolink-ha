import random

from typing import Any, Dict, Optional

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN, CONF_BEOLINK_NAME, CONF_SERIAL_NUMBER

BEOLINK_SCHEMA = vol.Schema({vol.Required(CONF_BEOLINK_NAME,default="BLGW"): cv.string})

class BeoLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    data: Optional[Dict[str, Any]]

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Invoked when a user initiates a flow via the user interface."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            self.data = user_input
            self.data[CONF_SERIAL_NUMBER] = random.randrange(24000000, 25000000)
            return await self.async_create_entry(title="BeoLink", data=self.data)
        return self.async_show_form(
            step_id="user", data_schema=BEOLINK_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, user_input=None):
        return await self.async_step_user()

    async def async_create_entry(self, title: str, data: dict) -> dict:
        """Create an oauth config entry or update existing entry for reauth."""
        # TODO: This example supports only a single config entry. Consider
        # any special handling needed for multiple config entries.
        existing_entry = await self.async_set_unique_id(data[CONF_SERIAL_NUMBER])
        if existing_entry:
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
        return super().async_create_entry(title=title, data=data)

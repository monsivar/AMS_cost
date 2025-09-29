
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
try:
    from homeassistant.helpers.selector import selector  # modern UI
    HAS_SELECTOR = True
except Exception:
    selector = None
    HAS_SELECTOR = False

from .const import (
    DOMAIN, CONF_TPI_ENTITY, CONF_HOURUSE_ENTITY, CONF_PRICE_ENTITY, CONF_THRESHOLD_ENTITY,
    CONF_T5, CONF_T10, CONF_T15, CONF_T20
)

DEFAULTS = {
    CONF_T5: 160.0,
    CONF_T10: 395.0,
    CONF_T15: 656.0,
    CONF_T20: 923.0,
}

class AmsCostsFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="AMS Costs",
                data=user_input
            )

        if HAS_SELECTOR:
            schema = vol.Schema({
                vol.Required(CONF_TPI_ENTITY): selector({"entity": {"domain": "sensor"}}),
                vol.Required(CONF_HOURUSE_ENTITY): selector({"entity": {"domain": "sensor"}}),
                vol.Required(CONF_PRICE_ENTITY): selector({"entity": {"domain": "sensor"}}),
                vol.Required(CONF_THRESHOLD_ENTITY): selector({"entity": {"domain": "sensor"}}),
                vol.Optional(CONF_T5, default=DEFAULTS[CONF_T5]): vol.Coerce(float),
                vol.Optional(CONF_T10, default=DEFAULTS[CONF_T10]): vol.Coerce(float),
                vol.Optional(CONF_T15, default=DEFAULTS[CONF_T15]): vol.Coerce(float),
                vol.Optional(CONF_T20, default=DEFAULTS[CONF_T20]): vol.Coerce(float),
            })
        else:
            # Fallback for very old HA without selector helper
            schema = vol.Schema({
                vol.Required(CONF_TPI_ENTITY): str,
                vol.Required(CONF_HOURUSE_ENTITY): str,
                vol.Required(CONF_PRICE_ENTITY): str,
                vol.Required(CONF_THRESHOLD_ENTITY): str,
                vol.Optional(CONF_T5, default=DEFAULTS[CONF_T5]): vol.Coerce(float),
                vol.Optional(CONF_T10, default=DEFAULTS[CONF_T10]): vol.Coerce(float),
                vol.Optional(CONF_T15, default=DEFAULTS[CONF_T15]): vol.Coerce(float),
                vol.Optional(CONF_T20, default=DEFAULTS[CONF_T20]): vol.Coerce(float),
            })

        return self.async_show_form(step_id="user", data_schema=schema)

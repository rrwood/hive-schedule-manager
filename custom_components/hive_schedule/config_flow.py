"""Config flow for Hive Schedule Manager integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HiveScheduleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hive Schedule Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Check if Hive integration is installed
        if "hive" not in self.hass.data:
            return self.async_abort(
                reason="hive_not_configured",
                description_placeholders={
                    "message": "Please install and configure the official Hive integration first."
                }
            )
        
        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id("hive_schedule_manager")
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title="Hive Schedule Manager",
                data={}
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "message": "This integration adds schedule management to your Hive heating. It uses the official Hive integration's authentication."
            }
        )
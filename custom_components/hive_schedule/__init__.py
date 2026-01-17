"""
Hive Schedule Manager Integration for Home Assistant
Manages Hive heating schedules with profile support using apyhiveapi.
Version: 1.1.0
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from apyhiveapi import Auth, Hive

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.exceptions import HomeAssistantError, ConfigEntryAuthFailed

from .const import (
    DOMAIN,
    SERVICE_SET_DAY,
    ATTR_NODE_ID,
    ATTR_DAY,
    ATTR_SCHEDULE,
    ATTR_PROFILE,
)
from .schedule_profiles import get_profile, get_available_profiles, validate_custom_schedule

_LOGGER = logging.getLogger(__name__)

# Service schema
SET_DAY_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_DAY): vol.In([
        "monday", "tuesday", "wednesday", "thursday", 
        "friday", "saturday", "sunday"
    ]),
    vol.Optional(ATTR_PROFILE): vol.In(get_available_profiles()),
    vol.Optional(ATTR_SCHEDULE): vol.All(cv.ensure_list, [{
        vol.Required("time"): cv.string,
        vol.Required("temp"): vol.Coerce(float),
    }])
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hive Schedule Manager from a config entry."""
    
    _LOGGER.info("Setting up Hive Schedule Manager v1.1.0")
    
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    
    # Initialize Hive API session
    websession = hass.helpers.aiohttp_client.async_get_clientsession()
    hive = Hive(websession=websession)
    
    # Create auth config
    hive_config = {
        "username": username,
        "password": password,
        "options": {
            "sms_2fa": True  # Enable 2FA support
        }
    }
    
    # Authenticate
    try:
        devices = await hive.session.startSession(hive_config)
        if not devices:
            raise ConfigEntryAuthFailed("Failed to start Hive session")
        _LOGGER.info("Successfully authenticated with Hive using apyhiveapi")
    except Exception as e:
        _LOGGER.error("Authentication error: %s", e)
        raise ConfigEntryAuthFailed(f"Authentication failed: {e}")
    
    # Store in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "hive": hive,
    }
    
    # Helper function to build schedule entry
    def build_schedule_entry(time: str, temp: float) -> dict[str, Any]:
        """Build a single schedule entry in Hive format."""
        hours, minutes = time.split(":")
        start_time = int(hours) * 60 + int(minutes)
        
        return {
            "value": {
                "targetHeatTemperature": temp,
                "temperatureUnit": "C"
            },
            "start": start_time
        }
    
    # Service: Set day schedule
    async def handle_set_day(call: ServiceCall) -> None:
        """Handle set_day_schedule service call - updates only the specified day."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        profile = call.data.get(ATTR_PROFILE)
        custom_schedule = call.data.get(ATTR_SCHEDULE)
        
        # Determine which schedule to use
        if profile and custom_schedule:
            _LOGGER.warning("Both profile and schedule provided, using custom schedule")
            day_schedule = custom_schedule
        elif profile:
            _LOGGER.info("Using profile '%s' for %s", profile, day)
            day_schedule = get_profile(profile)
        elif custom_schedule:
            _LOGGER.info("Using custom schedule for %s", day)
            day_schedule = custom_schedule
        else:
            raise HomeAssistantError(
                "Either 'profile' or 'schedule' must be provided"
            )
        
        # Validate custom schedule if provided
        if custom_schedule:
            try:
                validate_custom_schedule(day_schedule)
            except ValueError as err:
                raise HomeAssistantError(f"Invalid schedule: {err}") from err
        
        _LOGGER.info("Setting schedule for %s on node %s", day, node_id)
        
        # Build schedule with ONLY the selected day
        schedule_entries = [
            build_schedule_entry(entry["time"], entry["temp"])
            for entry in day_schedule
        ]
        
        # Update schedule using apyhiveapi
        try:
            # Use the heating API to update the schedule
            result = await hive.heating.setSchedule(node_id, day, schedule_entries)
            if not result:
                raise HomeAssistantError("Failed to update schedule - API returned False")
            _LOGGER.info("Successfully updated %s schedule", day)
        except Exception as e:
            _LOGGER.error("Error updating schedule: %s", e)
            raise HomeAssistantError(f"Failed to update schedule: {e}")
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DAY,
        handle_set_day,
        schema=SET_DAY_SCHEMA
    )
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id)
    
    # Unregister services if this is the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_DAY)
    
    return True
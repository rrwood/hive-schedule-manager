"""
Hive Schedule Manager Integration for Home Assistant
Enables programmatic control of British Gas Hive heating schedules.

For documentation, visit: https://github.com/YOUR_USERNAME/hive-schedule-manager
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
import requests

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "hive_schedule"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

# Service names
SERVICE_SET_SCHEDULE = "set_heating_schedule"
SERVICE_SET_DAY = "set_day_schedule"
SERVICE_UPDATE_FROM_CALENDAR = "update_from_calendar"

# Attributes
ATTR_NODE_ID = "node_id"
ATTR_DAY = "day"
ATTR_SCHEDULE = "schedule"
ATTR_IS_WORKDAY = "is_workday"
ATTR_WAKE_TIME = "wake_time"

# Configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period,
        })
    },
    extra=vol.ALLOW_EXTRA,
)

# Service schemas
SET_SCHEDULE_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_SCHEDULE): vol.Schema({
        vol.Optional("monday"): cv.ensure_list,
        vol.Optional("tuesday"): cv.ensure_list,
        vol.Optional("wednesday"): cv.ensure_list,
        vol.Optional("thursday"): cv.ensure_list,
        vol.Optional("friday"): cv.ensure_list,
        vol.Optional("saturday"): cv.ensure_list,
        vol.Optional("sunday"): cv.ensure_list,
    })
})

SET_DAY_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_DAY): vol.In(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]),
    vol.Required(ATTR_SCHEDULE): [{
        vol.Required("time"): cv.string,
        vol.Required("temp"): vol.Coerce(float),
    }]
})

CALENDAR_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_IS_WORKDAY): cv.boolean,
    vol.Optional(ATTR_WAKE_TIME): cv.string,
})


class HiveScheduleAPI:
    """API client for Hive Schedule operations."""
    
    BASE_URL = "https://beekeeper-uk.hivehome.com/1.0"
    
    def __init__(self) -> None:
        """Initialize the API client."""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://my.hivehome.com",
            "Referer": "https://my.hivehome.com/"
        })
        self._token: str | None = None
    
    def update_auth(self, token: str) -> None:
        """Update authorization token."""
        self._token = token
        self.session.headers["Authorization"] = token
        _LOGGER.debug("Updated API authorization token")
    
    @property
    def has_auth(self) -> bool:
        """Check if we have a valid auth token."""
        return self._token is not None
    
    @staticmethod
    def time_to_minutes(time_str: str) -> int:
        """Convert time string to minutes from midnight."""
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    
    def build_schedule_entry(self, time_str: str, temp: float) -> dict[str, Any]:
        """Build a single schedule entry."""
        return {
            "value": {"target": float(temp)},
            "start": self.time_to_minutes(time_str)
        }
    
    def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> bool:
        """Send schedule update to Hive."""
        if not self.has_auth:
            _LOGGER.error("Cannot update schedule: No auth token available")
            raise HomeAssistantError(
                "Hive authentication not available. Ensure Hive integration is loaded."
            )
        
        url = f"{self.BASE_URL}/nodes/heating/{node_id}"
        
        try:
            _LOGGER.debug("Sending schedule update to %s", url)
            response = self.session.post(url, json=schedule_data, timeout=30)
            response.raise_for_status()
            _LOGGER.info("Successfully updated Hive schedule for node %s", node_id)
            return True
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 401:
                _LOGGER.error("Authentication failed. Token may have expired.")
                raise HomeAssistantError(
                    "Hive authentication failed. Try reloading the Hive integration."
                ) from err
            if err.response.status_code == 404:
                _LOGGER.error("Node ID not found: %s", node_id)
                raise HomeAssistantError(f"Invalid node ID: {node_id}") from err
            _LOGGER.error("HTTP error updating schedule: %s", err)
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err
        except requests.exceptions.Timeout as err:
            _LOGGER.error("Request to Hive API timed out")
            raise HomeAssistantError("Hive API request timed out") from err
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Request error updating schedule: %s", err)
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Hive Schedule Manager component."""
    
    _LOGGER.info("Setting up Hive Schedule Manager")
    
    # Get scan interval first (before any other variables)
    scan_interval = config.get(DOMAIN, {}).get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    def get_hive_auth_token() -> str | None:
        """Extract auth token from existing Hive integration."""
        if "hive" not in hass.data:
            _LOGGER.warning("Hive integration not yet in hass.data")
            _LOGGER.info("Available keys in hass.data: %s", list(hass.data.keys()))
            return None
        
        try:
            hive_data = hass.data.get("hive")
            _LOGGER.info("=== HIVE DATA STRUCTURE DEBUG ===")
            _LOGGER.info("hive_data type: %s", type(hive_data))
            _LOGGER.info("hive_data is dict: %s", isinstance(hive_data, dict))
            
            if isinstance(hive_data, dict):
                _LOGGER.info("hive_data keys: %s", list(hive_data.keys()))
                
                for key, value in hive_data.items():
                    _LOGGER.info("  Key: %s", key)
                    _LOGGER.info("    Type: %s", type(value))
                    _LOGGER.info("    Has __dict__: %s", hasattr(value, "__dict__"))
                    
                    if hasattr(value, "__dict__"):
                        attrs = [a for a in dir(value) if not a.startswith("_")]
                        _LOGGER.info("    Public attributes: %s", attrs[:10])  # First 10
                    
                    # Check for session
                    if hasattr(value, "session"):
                        _LOGGER.info("    ✓ Has 'session' attribute")
                        session = value.session
                        _LOGGER.info("      session type: %s", type(session))
                        
                        if hasattr(session, "__dict__"):
                            sess_attrs = [a for a in dir(session) if not a.startswith("_")]
                            _LOGGER.info("      session attributes: %s", sess_attrs[:10])
                        
                        # Check for auth
                        if hasattr(session, "auth"):
                            _LOGGER.info("      ✓ Has 'auth' attribute")
                            auth = session.auth
                            _LOGGER.info("        auth type: %s", type(auth))
                            
                            if hasattr(auth, "__dict__"):
                                auth_attrs = [a for a in dir(auth) if not a.startswith("_")]
                                _LOGGER.info("        auth attributes: %s", auth_attrs)
                            
                            # Check all possible token locations
                            if hasattr(auth, "tokenData"):
                                _LOGGER.info("        ✓ Has 'tokenData'")
                                token_data = auth.tokenData
                                if isinstance(token_data, dict):
                                    _LOGGER.info("          tokenData keys: %s", list(token_data.keys()))
                                    if "IdToken" in token_data:
                                        token = token_data["IdToken"]
                                        _LOGGER.info("          ✓✓✓ FOUND TOKEN in tokenData['IdToken'] (length: %d)", len(token))
                                        return token
                            
                            if hasattr(auth, "token"):
                                token = auth.token
                                _LOGGER.info("        ✓ Has 'token' attribute (value type: %s)", type(token))
                                if token:
                                    _LOGGER.info("          ✓✓✓ FOUND TOKEN in auth.token (length: %d)", len(str(token)))
                                    return token
                            
                            if hasattr(auth, "accessToken"):
                                token = auth.accessToken
                                if token:
                                    _LOGGER.info("        ✓✓✓ FOUND TOKEN in auth.accessToken")
                                    return token
            
            _LOGGER.error("=== TOKEN NOT FOUND - Check debug output above ===")
            
        except Exception as err:
            _LOGGER.error("Error accessing Hive auth token: %s", err, exc_info=True)
        
        return None
    
    # Initialize API
    api = HiveScheduleAPI()
    hass.data[DOMAIN] = {"api": api}
    
    async def refresh_auth(now=None) -> None:
        """Refresh authentication token from Hive integration."""
        token = await hass.async_add_executor_job(get_hive_auth_token)
        if token:
            if not api.has_auth:
                _LOGGER.info("Successfully obtained Hive authentication token")
            api.update_auth(token)
        else:
            if now is None:  # Only log on startup, not on every refresh
                _LOGGER.debug("Hive integration not ready yet, will retry every %s", scan_interval)
    
    # Set up periodic refresh first
    async_track_time_interval(hass, refresh_auth, scan_interval)
    
    # Try initial auth
    await refresh_auth()
    
    if not api.has_auth:
        _LOGGER.warning(
            "Hive authentication token not available yet. "
            "Services will be available but may fail until Hive integration is fully loaded. "
            "Token refresh configured every %s.",
            scan_interval
        )
        # Don't fail setup - allow integration to load and get token later
    
    async def handle_set_schedule(call: ServiceCall) -> None:
        """Handle set_heating_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        schedule_config = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info("Setting complete schedule for node %s", node_id)
        
        # Build schedule in Hive format
        schedule_data: dict[str, Any] = {"schedule": {}}
        
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if day in schedule_config:
                day_schedule = []
                for entry in schedule_config[day]:
                    day_schedule.append(
                        api.build_schedule_entry(entry["time"], entry["temp"])
                    )
                schedule_data["schedule"][day] = day_schedule
            else:
                # Default: 16°C all day
                schedule_data["schedule"][day] = [
                    api.build_schedule_entry("00:00", 16.0)
                ]
        
        # Update schedule
        await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)
    
    async def handle_set_day(call: ServiceCall) -> None:
        """Handle set_day_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        day_schedule = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info("Setting schedule for %s on node %s", day, node_id)
        
        # Default schedule for other days
        default_schedule = [
            {"time": "06:30", "temp": 18.0},
            {"time": "08:00", "temp": 16.0},
            {"time": "16:30", "temp": 19.5},
            {"time": "21:30", "temp": 16.0}
        ]
        
        schedule_data: dict[str, Any] = {"schedule": {}}
        
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d == day:
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in day_schedule
                ]
            else:
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in default_schedule
                ]
        
        await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)
    
    async def handle_calendar_update(call: ServiceCall) -> None:
        """Handle update_from_calendar service call."""
        node_id = call.data[ATTR_NODE_ID]
        is_workday = call.data[ATTR_IS_WORKDAY]
        wake_time = call.data.get(ATTR_WAKE_TIME, "06:30" if is_workday else "07:30")
        
        # Determine tomorrow's day
        tomorrow = datetime.now() + timedelta(days=1)
        day = tomorrow.strftime("%A").lower()
        
        _LOGGER.info("Updating %s schedule from calendar (workday=%s)", day, is_workday)
        
        # Build appropriate schedule
        if is_workday:
            day_schedule = [
                {"time": wake_time, "temp": 18.0},
                {"time": "09:15", "temp": 18.5},
                {"time": "09:30", "temp": 18.0},
                {"time": "15:30", "temp": 18.0},
                {"time": "16:30", "temp": 19.5},
                {"time": "21:30", "temp": 16.0}
            ]
        else:
            day_schedule = [
                {"time": wake_time, "temp": 18.0},
                {"time": "09:15", "temp": 18.5},
                {"time": "09:30", "temp": 18.0},
                {"time": "16:30", "temp": 19.5},
                {"time": "21:30", "temp": 16.0}
            ]
        
        # Update just tomorrow's schedule
        await handle_set_day(
            ServiceCall(
                DOMAIN,
                SERVICE_SET_DAY,
                {ATTR_NODE_ID: node_id, ATTR_DAY: day, ATTR_SCHEDULE: day_schedule}
            )
        )
        
        _LOGGER.info(
            "Updated %s schedule for %s",
            day,
            "workday" if is_workday else "weekend"
        )
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, schema=SET_SCHEDULE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DAY, handle_set_day, schema=SET_DAY_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_FROM_CALENDAR, handle_calendar_update, schema=CALENDAR_SCHEMA
    )
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    return True
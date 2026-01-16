"""
Hive Schedule Manager Integration for Home Assistant
Enables programmatic control of British Gas Hive heating schedules.

Artifact Version: v9
Last Updated: 2026-01-16

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

# Try to import ultra diagnostics
try:
    from .ultra_diagnostics import create_ultra_diagnostic_service
    ULTRA_DIAGNOSTICS_AVAILABLE = True
except ImportError:
    ULTRA_DIAGNOSTICS_AVAILABLE = False
    _LOGGER.warning("Ultra diagnostics not available")

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
        _LOGGER.debug("Updated API authorization token (length: %d)", len(token) if token else 0)
    
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
    
    # Get scan interval
    scan_interval = config.get(DOMAIN, {}).get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    def get_hive_auth_token() -> str | None:
        """Extract auth token from Hive integration using config entries."""
        _LOGGER.debug("=== SEARCHING FOR HIVE AUTH TOKEN ===")
        
        try:
            # Method 1: Try to get from config entries runtime_data
            hive_entries = hass.config_entries.async_entries("hive")
            
            if not hive_entries:
                _LOGGER.warning("No Hive config entries found. Is the Hive integration set up?")
                return None
            
            for entry in hive_entries:
                _LOGGER.debug("Checking Hive config entry: %s", entry.entry_id)
                
                # Check runtime_data
                if hasattr(entry, 'runtime_data') and entry.runtime_data:
                    runtime = entry.runtime_data
                    _LOGGER.debug("  Found runtime_data of type: %s", type(runtime))
                    
                    # Try common attribute paths
                    paths_to_try = [
                        # Direct attributes
                        ("session", "auth", "tokenData", "IdToken"),
                        ("session", "auth", "token"),
                        ("session", "auth", "accessToken"),
                        ("api", "auth", "tokenData", "IdToken"),
                        ("api", "auth", "token"),
                        ("api", "session", "auth", "tokenData", "IdToken"),
                        ("api", "session", "auth", "token"),
                        # ApyHiveApi specific paths
                        ("session", "_auth", "tokenData", "IdToken"),
                        ("session", "_auth", "token"),
                        ("_session", "auth", "tokenData", "IdToken"),
                        ("_session", "auth", "token"),
                        # Alternative structures
                        ("hive", "session", "auth", "tokenData", "IdToken"),
                        ("hive", "session", "auth", "token"),
                    ]
                    
                    for path in paths_to_try:
                        obj = runtime
                        success = True
                        
                        for attr in path[:-1]:
                            if hasattr(obj, attr):
                                obj = getattr(obj, attr)
                            else:
                                success = False
                                break
                        
                        if success and hasattr(obj, path[-1]):
                            token_val = getattr(obj, path[-1])
                            
                            # Handle dict with IdToken
                            if isinstance(token_val, dict) and "IdToken" in token_val:
                                token = token_val["IdToken"]
                                if token and isinstance(token, str) and len(token) > 50:
                                    _LOGGER.info("✓ Found token via path: %s", " -> ".join(path))
                                    return token
                            # Handle direct string token
                            elif isinstance(token_val, str) and len(token_val) > 50:
                                _LOGGER.info("✓ Found token via path: %s", " -> ".join(path))
                                return token_val
                    
                    # If paths didn't work, try to explore the object structure
                    _LOGGER.debug("  Exploring runtime_data structure...")
                    if hasattr(runtime, '__dict__'):
                        for key, value in vars(runtime).items():
                            if key.startswith('_'):
                                continue
                            _LOGGER.debug("    runtime.%s: %s", key, type(value))
                            
                            # Check if this looks like it might have auth
                            if hasattr(value, 'auth') or hasattr(value, 'session'):
                                _LOGGER.debug("      Checking %s for auth...", key)
                                token = _extract_token_from_object(value, prefix=f"runtime.{key}")
                                if token:
                                    return token
            
            # Method 2: Try hass.data with entry_id
            for entry in hive_entries:
                entry_id = entry.entry_id
                if entry_id in hass.data:
                    _LOGGER.debug("Checking hass.data[%s]", entry_id)
                    data = hass.data[entry_id]
                    token = _extract_token_from_object(data, prefix=f"hass.data[{entry_id}]")
                    if token:
                        return token
            
            _LOGGER.warning("Could not find Hive auth token in any expected location")
            
        except Exception as e:
            _LOGGER.error("Error searching for Hive token: %s", e, exc_info=True)
        
        return None
    
    def _extract_token_from_object(obj: Any, prefix: str = "", depth: int = 0) -> str | None:
        """Recursively extract token from an object (with depth limit)."""
        if depth > 3:  # Prevent infinite recursion
            return None
        
        if not hasattr(obj, '__dict__'):
            return None
        
        # Check for session/api attributes
        for session_attr in ['session', 'api', '_session', '_api', 'hive']:
            if hasattr(obj, session_attr):
                session_obj = getattr(obj, session_attr)
                _LOGGER.debug("%s.%s exists (type: %s)", prefix, session_attr, type(session_obj))
                
                # Check for auth
                for auth_attr in ['auth', '_auth']:
                    if hasattr(session_obj, auth_attr):
                        auth_obj = getattr(session_obj, auth_attr)
                        _LOGGER.debug("%s.%s.%s exists (type: %s)", prefix, session_attr, auth_attr, type(auth_obj))
                        
                        # Check for token
                        for token_attr in ['tokenData', 'token', 'accessToken', '_token']:
                            if hasattr(auth_obj, token_attr):
                                token_val = getattr(auth_obj, token_attr)
                                
                                # Handle dict
                                if isinstance(token_val, dict) and "IdToken" in token_val:
                                    token = token_val["IdToken"]
                                    if token and isinstance(token, str) and len(token) > 50:
                                        _LOGGER.info("✓ Found token at %s.%s.%s.%s['IdToken']", 
                                                    prefix, session_attr, auth_attr, token_attr)
                                        return token
                                # Handle string
                                elif isinstance(token_val, str) and len(token_val) > 50:
                                    _LOGGER.info("✓ Found token at %s.%s.%s.%s", 
                                                prefix, session_attr, auth_attr, token_attr)
                                    return token_val
                
                # Recurse into session
                token = _extract_token_from_object(session_obj, f"{prefix}.{session_attr}", depth + 1)
                if token:
                    return token
        
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
            if now is None:  # Only log on startup
                _LOGGER.debug("Hive integration not ready yet, will retry every %s", scan_interval)
    
    # Set up periodic refresh
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
    
    # DEBUG SERVICE
    async def handle_debug_hive(call: ServiceCall) -> None:
        """Debug service to inspect Hive data structure."""
        _LOGGER.info("=== MANUAL DEBUG TRIGGERED ===")
        token = await hass.async_add_executor_job(get_hive_auth_token)
        if token:
            _LOGGER.info("✓ Token found! Length: %d", len(token))
        else:
            _LOGGER.error("✗ Token NOT found")
            
            # Additional debugging
            _LOGGER.info("=== DETAILED DEBUG INFO ===")
            hive_entries = hass.config_entries.async_entries("hive")
            _LOGGER.info("Number of Hive entries: %d", len(hive_entries))
            
            for entry in hive_entries:
                _LOGGER.info("Entry ID: %s", entry.entry_id)
                _LOGGER.info("  State: %s", entry.state)
                _LOGGER.info("  Has runtime_data: %s", hasattr(entry, 'runtime_data') and entry.runtime_data is not None)
                
                if hasattr(entry, 'runtime_data') and entry.runtime_data:
                    runtime = entry.runtime_data
                    _LOGGER.info("  Runtime type: %s", type(runtime).__name__)
                    if hasattr(runtime, '__dict__'):
                        attrs = [k for k in vars(runtime).keys() if not k.startswith('_')]
                        _LOGGER.info("  Runtime attributes: %s", attrs)
    
    hass.services.async_register(DOMAIN, "debug_hive_data", handle_debug_hive)
    
    # Register ultra diagnostic service if available
    if ULTRA_DIAGNOSTICS_AVAILABLE:
        create_ultra_diagnostic_service(hass)
        _LOGGER.info("Ultra diagnostic service registered")
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    return True
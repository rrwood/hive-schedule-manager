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
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the API client."""
        self.hass = hass
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://my.hivehome.com",
            "Referer": "https://my.hivehome.com/"
        })
        self._token: str | None = None
        self._hive_api = None  # Store reference to Hive's API client
    
    def set_hive_api(self, hive_api) -> None:
        """Set reference to Hive's API client."""
        self._hive_api = hive_api
        _LOGGER.debug("Set reference to Hive API client")
    
    def update_auth(self, token: str) -> None:
        """Update authorization token."""
        self._token = token
        self.session.headers["Authorization"] = token
        _LOGGER.debug("Updated API authorization token (length: %d)", len(token) if token else 0)
    
    @property
    def has_auth(self) -> bool:
        """Check if we have a valid auth token."""
        return self._token is not None or self._hive_api is not None
    
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
    
    async def _get_auth_header(self) -> str | None:
        """Get current authorization header value."""
        if self._token:
            return self._token
        
        # Try to get token from Hive API
        if self._hive_api and hasattr(self._hive_api, 'auth'):
            auth = self._hive_api.auth
            if hasattr(auth, 'access_token'):
                token = auth.access_token
                if token:
                    _LOGGER.debug("Using token from Hive API client")
                    return token
        
        return None
    
    def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> bool:
        """Send schedule update to Hive."""
        if not self.has_auth:
            _LOGGER.error("Cannot update schedule: No auth token available")
            raise HomeAssistantError(
                "Hive authentication not available. Ensure Hive integration is loaded."
            )
        
        # Get current token (might be from Hive API)
        import asyncio
        loop = asyncio.get_event_loop()
        token = loop.run_until_complete(self._get_auth_header())
        
        if not token:
            _LOGGER.error("Cannot update schedule: Unable to get auth token")
            raise HomeAssistantError("Hive authentication not available")
        
        # Update session header with current token
        self.session.headers["Authorization"] = token
        
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
        _LOGGER.warning("=== SEARCHING FOR HIVE AUTH TOKEN ===")
        
        try:
            # Get Hive config entries
            hive_entries = hass.config_entries.async_entries("hive")
            
            if not hive_entries:
                _LOGGER.warning("No Hive config entries found. Is the Hive integration set up?")
                return None
            
            for entry in hive_entries:
                _LOGGER.warning("Checking Hive config entry: %s", entry.entry_id)
                
                # Method 1: Check runtime_data.auth.access_token (apyhiveapi structure)
                if hasattr(entry, 'runtime_data') and entry.runtime_data:
                    runtime = entry.runtime_data
                    _LOGGER.warning("  Found runtime_data of type: %s", type(runtime).__name__)
                    
                    # apyhiveapi stores auth in runtime.auth.access_token
                    if hasattr(runtime, 'auth'):
                        auth = runtime.auth
                        _LOGGER.warning("  Found runtime.auth of type: %s", type(auth).__name__)
                        
                        if hasattr(auth, 'access_token'):
                            token = auth.access_token
                            _LOGGER.warning("  runtime.auth.access_token type: %s", type(token).__name__ if token else "None")
                            
                            if token and isinstance(token, str) and len(token) > 50:
                                _LOGGER.info("✓ Found token at runtime_data.auth.access_token (length: %d)", len(token))
                                return token
                            else:
                                _LOGGER.warning("  runtime.auth.access_token is None or too short")
                    
                    # Also check session.auth.access_token
                    if hasattr(runtime, 'session') and hasattr(runtime.session, 'auth'):
                        auth = runtime.session.auth
                        if hasattr(auth, 'access_token'):
                            token = auth.access_token
                            if token and isinstance(token, str) and len(token) > 50:
                                _LOGGER.info("✓ Found token at runtime_data.session.auth.access_token")
                                return token
                
                # Method 2: Check entry.data['tokens'] (stored tokens)
                if entry.data and 'tokens' in entry.data:
                    tokens = entry.data['tokens']
                    _LOGGER.warning("  Found 'tokens' in entry.data: %s", type(tokens).__name__)
                    
                    # Tokens might be a dict
                    if isinstance(tokens, dict):
                        _LOGGER.warning("  entry.data['tokens'] is dict with keys: %s", list(tokens.keys())[:10])
                        
                        # AWS Cognito structure: tokens['AuthenticationResult'] contains the actual tokens
                        if 'AuthenticationResult' in tokens:
                            auth_result = tokens['AuthenticationResult']
                            _LOGGER.warning("    Found 'AuthenticationResult', checking for tokens...")
                            
                            if isinstance(auth_result, dict):
                                # Check for common AWS Cognito token keys
                                for key in ['IdToken', 'AccessToken', 'id_token', 'access_token']:
                                    if key in auth_result:
                                        token = auth_result[key]
                                        _LOGGER.warning("      Found '%s' in AuthenticationResult, type: %s", key, type(token).__name__)
                                        
                                        if token and isinstance(token, str) and len(token) > 50:
                                            _LOGGER.info("✓ Found token at entry.data['tokens']['AuthenticationResult']['%s'] (length: %d)", key, len(token))
                                            return token
                                        else:
                                            _LOGGER.warning("      '%s' is None or too short", key)
                        
                        # Also check direct keys (original code)
                        for key in ['IdToken', 'id_token', 'access_token', 'AccessToken', 'token']:
                            if key in tokens:
                                token = tokens[key]
                                _LOGGER.warning("    Found '%s' in tokens dict, type: %s", key, type(token).__name__)
                                
                                if token and isinstance(token, str) and len(token) > 50:
                                    _LOGGER.info("✓ Found token at entry.data['tokens']['%s'] (length: %d)", key, len(token))
                                    return token
                                else:
                                    _LOGGER.warning("    '%s' is None or too short", key)
                    
                    # Tokens might be a string directly
                    elif isinstance(tokens, str) and len(tokens) > 50:
                        _LOGGER.info("✓ Found token at entry.data['tokens'] (length: %d)", len(tokens))
                        return tokens
                    else:
                        _LOGGER.warning("  entry.data['tokens'] is %s: %s", type(tokens).__name__, str(tokens)[:100])
                
                # Method 3: Try to trigger a token refresh by calling the auth method
                if hasattr(entry, 'runtime_data') and entry.runtime_data:
                    runtime = entry.runtime_data
                    if hasattr(runtime, 'auth'):
                        auth = runtime.auth
                        
                        _LOGGER.warning("  Checking auth methods...")
                        # Check if there's a method to get the token
                        for method_name in ['get_access_token', 'getAccessToken', 'token', 'get_token']:
                            if hasattr(auth, method_name):
                                try:
                                    method = getattr(auth, method_name)
                                    if callable(method):
                                        _LOGGER.warning("    Calling auth.%s()...", method_name)
                                        token = method()
                                        if token and isinstance(token, str) and len(token) > 50:
                                            _LOGGER.info("✓ Found token via auth.%s() (length: %d)", method_name, len(token))
                                            return token
                                except Exception as e:
                                    _LOGGER.warning("    Error calling auth.%s(): %s", method_name, str(e))
            
            _LOGGER.warning("Could not find Hive auth token in any expected location")
            
        except Exception as e:
            _LOGGER.error("Error searching for Hive token: %s", e, exc_info=True)
        
        return None
    
    # Initialize API
    api = HiveScheduleAPI(hass)
    hass.data[DOMAIN] = {"api": api}
    
    async def refresh_auth(now=None) -> None:
        """Refresh authentication token from Hive integration."""
        token = await hass.async_add_executor_job(get_hive_auth_token)
        if token:
            if not api.has_auth:
                _LOGGER.info("Successfully obtained Hive authentication token")
            api.update_auth(token)
        else:
            # Try to get reference to Hive API client instead
            hive_entries = hass.config_entries.async_entries("hive")
            for entry in hive_entries:
                if hasattr(entry, 'runtime_data') and entry.runtime_data:
                    runtime = entry.runtime_data
                    if hasattr(runtime, 'api'):
                        api.set_hive_api(runtime.api)
                        _LOGGER.info("Using Hive's API client for authentication")
                        return
            
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
        _LOGGER.warning("=" * 80)
        _LOGGER.warning("MANUAL DEBUG TRIGGERED")
        _LOGGER.warning("=" * 80)
        
        token = await hass.async_add_executor_job(get_hive_auth_token)
        if token:
            _LOGGER.warning("✓ Token found! Length: %d", len(token))
        else:
            _LOGGER.error("✗ Token NOT found")
            
            # Additional debugging
            _LOGGER.warning("=" * 80)
            _LOGGER.warning("DETAILED DEBUG INFO")
            _LOGGER.warning("=" * 80)
            hive_entries = hass.config_entries.async_entries("hive")
            _LOGGER.warning("Number of Hive entries: %d", len(hive_entries))
            
            for idx, entry in enumerate(hive_entries):
                _LOGGER.warning("")
                _LOGGER.warning("Entry #%d:", idx + 1)
                _LOGGER.warning("  Entry ID: %s", entry.entry_id)
                _LOGGER.warning("  State: %s", entry.state)
                
                # Check entry.data in detail
                if entry.data:
                    _LOGGER.warning("  entry.data keys: %s", list(entry.data.keys()))
                    
                    # Look at 'tokens' in detail
                    if 'tokens' in entry.data:
                        tokens = entry.data['tokens']
                        _LOGGER.warning("  entry.data['tokens'] type: %s", type(tokens).__name__)
                        
                        if isinstance(tokens, dict):
                            _LOGGER.warning("  entry.data['tokens'] keys: %s", list(tokens.keys()))
                            for key, value in tokens.items():
                                if isinstance(value, str):
                                    _LOGGER.warning("    '%s': <string length %d>", key, len(value))
                                else:
                                    _LOGGER.warning("    '%s': %s", key, type(value).__name__)
                        elif isinstance(tokens, str):
                            _LOGGER.warning("  entry.data['tokens'] is string, length: %d", len(tokens))
                        else:
                            _LOGGER.warning("  entry.data['tokens'] is: %s", tokens)
                
                # Check runtime_data
                _LOGGER.warning("  Has runtime_data: %s", hasattr(entry, 'runtime_data') and entry.runtime_data is not None)
                
                if hasattr(entry, 'runtime_data') and entry.runtime_data:
                    runtime = entry.runtime_data
                    _LOGGER.warning("  Runtime type: %s", type(runtime).__name__)
                    _LOGGER.warning("  Runtime module: %s", type(runtime).__module__)
                    
                    # Check auth in detail
                    if hasattr(runtime, 'auth'):
                        auth = runtime.auth
                        _LOGGER.warning("  runtime.auth type: %s", type(auth).__name__)
                        
                        # Check access_token
                        if hasattr(auth, 'access_token'):
                            token_val = auth.access_token
                            _LOGGER.warning("    auth.access_token: %s", type(token_val).__name__ if token_val else "None")
                            if token_val and isinstance(token_val, str):
                                _LOGGER.warning("    auth.access_token length: %d", len(token_val))
                        
                        # Check other token-like attributes
                        for attr in ['id_token', 'refresh_token', 'token', '_token']:
                            if hasattr(auth, attr):
                                val = getattr(auth, attr)
                                _LOGGER.warning("    auth.%s: %s", attr, type(val).__name__ if val else "None")
                                if val and isinstance(val, str):
                                    _LOGGER.warning("      length: %d", len(val))
                    
                    # Check if runtime has a 'tokens' attribute (Map)
                    if hasattr(runtime, 'tokens'):
                        tokens_map = runtime.tokens
                        _LOGGER.warning("  runtime.tokens type: %s", type(tokens_map).__name__)
                        
                        # Try to access it like a dict
                        try:
                            if hasattr(tokens_map, '__getitem__'):
                                for key in ['access_token', 'id_token', 'refresh_token', 'AccessToken', 'IdToken']:
                                    try:
                                        val = tokens_map[key]
                                        _LOGGER.warning("    tokens['%s']: %s", key, type(val).__name__ if val else "None")
                                        if val and isinstance(val, str):
                                            _LOGGER.warning("      length: %d", len(val))
                                    except (KeyError, TypeError):
                                        pass
                        except Exception as e:
                            _LOGGER.warning("    Cannot access tokens map: %s", e)
    
    hass.services.async_register(DOMAIN, "debug_hive_data", handle_debug_hive)
    
    # Service to find node IDs
    async def handle_find_nodes(call: ServiceCall) -> None:
        """Find all Hive heating node IDs."""
        _LOGGER.warning("=" * 80)
        _LOGGER.warning("SEARCHING FOR HIVE HEATING NODE IDS")
        _LOGGER.warning("=" * 80)
        
        hive_entries = hass.config_entries.async_entries("hive")
        
        for entry in hive_entries:
            if hasattr(entry, 'runtime_data') and entry.runtime_data:
                runtime = entry.runtime_data
                
                # Check devices dict
                if hasattr(runtime, 'devices'):
                    devices = runtime.devices
                    _LOGGER.warning("Found %d devices in Hive integration:", len(devices))
                    
                    for device_id, device_data in devices.items():
                        _LOGGER.warning("")
                        _LOGGER.warning("Device ID: %s", device_id)
                        _LOGGER.warning("  Type: %s", type(device_data).__name__)
                        
                        if isinstance(device_data, dict):
                            _LOGGER.warning("  Keys: %s", list(device_data.keys())[:20])
                            
                            # Look for heating/climate related data
                            for key, value in device_data.items():
                                if 'heating' in str(key).lower() or 'climate' in str(key).lower() or 'thermostat' in str(key).lower():
                                    _LOGGER.warning("    %s: %s", key, value)
                                if key in ['type', 'model', 'name', 'deviceType']:
                                    _LOGGER.warning("    %s: %s", key, value)
                        
                        # The device_id itself might be the node_id
                        if len(device_id) > 20:  # UUIDs are typically 36 chars
                            _LOGGER.warning("  ★ This might be your node_id: %s", device_id)
                
                # Check deviceList
                if hasattr(runtime, 'deviceList'):
                    device_list = runtime.deviceList
                    _LOGGER.warning("")
                    _LOGGER.warning("Found %d devices in deviceList:", len(device_list))
                    
                    for device_id, device_info in device_list.items():
                        _LOGGER.warning("")
                        _LOGGER.warning("Device: %s", device_id)
                        if isinstance(device_info, dict):
                            device_type = device_info.get('type', 'unknown')
                            device_name = device_info.get('state', {}).get('name', 'unknown')
                            _LOGGER.warning("  Name: %s", device_name)
                            _LOGGER.warning("  Type: %s", device_type)
                            
                            if 'heating' in device_type.lower() or 'thermostat' in device_type.lower():
                                _LOGGER.warning("  ★★★ HEATING DEVICE FOUND ★★★")
                                _LOGGER.warning("  ★★★ Use this node_id: %s", device_id)
        
        _LOGGER.warning("")
        _LOGGER.warning("=" * 80)
    
    hass.services.async_register(DOMAIN, "find_node_ids", handle_find_nodes)
    
    # Register simple diagnostic service
    async def handle_simple_diagnose(call: ServiceCall) -> None:
        """Handle simple diagnostic service call."""
        _LOGGER.warning("=" * 80)
        _LOGGER.warning("SIMPLE DIAGNOSTIC SERVICE CALLED")
        _LOGGER.warning("=" * 80)
        
        try:
            # Import here to avoid issues
            from .simple_diagnostics import simple_diagnostic
            await hass.async_add_executor_job(simple_diagnostic, hass)
        except ImportError as e:
            _LOGGER.error("Failed to import simple_diagnostics: %s", e)
        except Exception as e:
            _LOGGER.error("Error running diagnostic: %s", e, exc_info=True)
    
    hass.services.async_register(DOMAIN, "simple_diagnose", handle_simple_diagnose)
    _LOGGER.warning("Simple diagnostic service 'hive_schedule.simple_diagnose' has been registered")
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    return True
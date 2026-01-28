"""
Hive Schedule Manager Integration for Home Assistant
Version: 1.1.17 (Production - POST only, YAML profiles)
"""
from __future__ import annotations

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
import requests
import yaml
from pycognito import Cognito
import aiofiles

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    COGNITO_POOL_ID,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    SERVICE_SET_DAY,
    ATTR_NODE_ID,
    ATTR_DAY,
    ATTR_SCHEDULE,
    ATTR_PROFILE,
    CONF_ID_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)
PROFILES_FILE = "hive_schedule_profiles.yaml"

# Service schema - profile validation at runtime
SET_DAY_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_DAY): vol.In([
        "monday", "tuesday", "wednesday", "thursday", 
        "friday", "saturday", "sunday"
    ]),
    vol.Optional(ATTR_PROFILE): cv.string,  # Validated at runtime
    vol.Optional(ATTR_SCHEDULE): vol.All(cv.ensure_list, [{
        vol.Required("time"): cv.string,
        vol.Required("temp"): vol.Coerce(float),
    }])
})


async def _load_profiles(hass: HomeAssistant) -> dict:
    """Load schedule profiles from YAML file asynchronously."""
    config_path = hass.config.path(PROFILES_FILE)
    
    # Create default profiles file if it doesn't exist
    if not os.path.exists(config_path):
        _LOGGER.info("Creating default profiles file: %s", config_path)
        await _create_default_profiles_file(config_path)
    
    try:
        async with aiofiles.open(config_path, 'r') as file:
            content = await file.read()
            profiles = yaml.safe_load(content) or {}
            _LOGGER.debug("Loaded %d profiles from %s", len(profiles), PROFILES_FILE)
            return profiles
    except Exception as e:
        _LOGGER.error("Failed to load profiles from %s: %s", PROFILES_FILE, e)
        return _get_builtin_profiles()


def _get_builtin_profiles() -> dict:
    """Get built-in default profiles as fallback."""
    return {
        "workday": [
            {"time": "05:20", "temp": 18.5},
            {"time": "07:00", "temp": 18.0},
            {"time": "16:30", "temp": 19.5},
            {"time": "21:45", "temp": 16.0},
        ],
        "weekend": [
            {"time": "07:30", "temp": 18.5},
            {"time": "09:00", "temp": 18.0},
            {"time": "16:30", "temp": 19.5},
            {"time": "22:00", "temp": 16.0},
        ],
        "nonworkday": [
            {"time": "06:30", "temp": 18.5},
            {"time": "08:00", "temp": 18.0},
            {"time": "16:30", "temp": 19.5},
            {"time": "22:00", "temp": 16.0},
        ],
        "holiday": [
            {"time": "00:00", "temp": 15.0},
        ],
        "all_day_comfort": [
            {"time": "00:00", "temp": 19.0},
        ],
        "custom1": [
            {"time": "05:30", "temp": 17.0},
            {"time": "08:00", "temp": 16.5},
            {"time": "12:00", "temp": 18.0},
            {"time": "17:00", "temp": 19.0},
            {"time": "22:30", "temp": 16.0},
        ],
        "custom2": [
            {"time": "06:00", "temp": 18.0},
            {"time": "09:00", "temp": 17.5},
            {"time": "13:00", "temp": 18.5},
            {"time": "18:00", "temp": 19.5},
            {"time": "23:00", "temp": 16.5},
        ],
    }


async def _create_default_profiles_file(config_path: str) -> None:
    """Create default profiles YAML file asynchronously."""
    default_content = """# Hive Schedule Profiles
# Edit this file to customize your heating schedules
# After editing, changes take effect on the next service call (no restart needed)
# Time format: "HH:MM" (24-hour)
# Temperature: Celsius (5.0 - 32.0)

# Standard weekday schedule (Mon-Thur)
workday:
  - time: "05:20"
    temp: 18.5  # Morning warmup
  - time: "07:00"
    temp: 18.0  # Away during day
  - time: "16:30"
    temp: 19.5  # Evening warmup
  - time: "21:45"
    temp: 16.0  # Night setback

# Weekend schedule
weekend:
  - time: "07:30"
    temp: 18.5  # Later morning warmup
  - time: "09:00"
    temp: 18.0  # Comfortable day temperature
  - time: "16:30"
    temp: 19.5  # Evening warmup
  - time: "22:00"
    temp: 16.0  # Later night setback

# Non working weekday, later start
nonworkday:
  - time: "06:30"
    temp: 18.5
  - time: "08:00"
    temp: 18.0
  - time: "16:30"
    temp: 19.5
  - time: "22:00"
    temp: 16.0

# Away/vacation mode (frost protection)
holiday:
  - time: "00:00"
    temp: 15.0

# All day comfort (constant temperature)
all_day_comfort:
  - time: "00:00"
    temp: 19.0

# Custom profile 1 (5 states)
custom1:
  - time: "05:30"
    temp: 17.0
  - time: "08:00"
    temp: 16.5
  - time: "12:00"
    temp: 18.0
  - time: "17:00"
    temp: 19.0
  - time: "22:30"
    temp: 16.0

# Custom profile 2 (5 states)
custom2:
  - time: "06:00"
    temp: 18.0
  - time: "09:00"
    temp: 17.5
  - time: "13:00"
    temp: 18.5
  - time: "18:00"
    temp: 19.5
  - time: "23:00"
    temp: 16.5
"""
    
    try:
        async with aiofiles.open(config_path, 'w') as file:
            await file.write(default_content)
        _LOGGER.info("Created default profiles file at %s", config_path)
    except Exception as e:
        _LOGGER.error("Failed to create default profiles file: %s", e)


def _validate_schedule(schedule: list) -> bool:
    """Validate a schedule format."""
    if not isinstance(schedule, list):
        raise ValueError("Schedule must be a list")
    
    if len(schedule) == 0:
        raise ValueError("Schedule must have at least one entry")
    
    for entry in schedule:
        if not isinstance(entry, dict):
            raise ValueError("Each schedule entry must be a dictionary")
        
        if "time" not in entry or "temp" not in entry:
            raise ValueError("Each entry must have 'time' and 'temp' keys")
        
        # Validate time format (HH:MM)
        time_str = entry["time"]
        try:
            hours, minutes = time_str.split(":")
            if not (0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid time format: {time_str}. Must be HH:MM")
        
        # Validate temperature
        try:
            temp = float(entry["temp"])
            if not (5.0 <= temp <= 32.0):
                raise ValueError(f"Temperature {temp}°C out of range (5-32°C)")
        except (ValueError, TypeError):
            raise ValueError(f"Invalid temperature: {entry['temp']}")
    
    return True


class HiveAuth:
    """Handle Hive authentication via AWS Cognito."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize Hive authentication."""
        self.hass = hass
        self.entry = entry
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]
        self._cognito = None
        
        # Load tokens from config entry
        self._id_token = entry.data.get(CONF_ID_TOKEN)
        self._access_token = entry.data.get(CONF_ACCESS_TOKEN)
        self._refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
        
        # Parse token expiry
        expiry_str = entry.data.get(CONF_TOKEN_EXPIRY)
        if expiry_str:
            try:
                self._token_expiry = datetime.fromisoformat(expiry_str)
            except (ValueError, TypeError):
                self._token_expiry = None
        else:
            self._token_expiry = None
    
    def refresh_token(self) -> bool:
        """Refresh the authentication token using refresh token."""
        try:
            # Check if we need to refresh
            if self._token_expiry and datetime.now() < self._token_expiry - timedelta(minutes=5):
                _LOGGER.debug("Token still valid, no refresh needed")
                return True
            
            if not self._refresh_token:
                _LOGGER.warning("No refresh token available")
                return False
            
            _LOGGER.info("Refreshing authentication token...")
            
            # Create Cognito instance
            self._cognito = Cognito(
                user_pool_id=COGNITO_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=self.username,
                id_token=self._id_token,
                access_token=self._access_token,
                refresh_token=self._refresh_token,
            )
            
            # Refresh tokens
            self._cognito.renew_access_token()
            
            # Update stored tokens
            self._id_token = self._cognito.id_token
            self._access_token = self._cognito.access_token
            self._token_expiry = datetime.now() + timedelta(minutes=55)
            
            # Save updated tokens to config entry
            self._save_tokens()
            
            _LOGGER.info("Successfully refreshed authentication token")
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to refresh token: %s", e)
            return False
    
    def _save_tokens(self) -> None:
        """Save tokens to config entry."""
        try:
            new_data = dict(self.entry.data)
            new_data[CONF_ID_TOKEN] = self._id_token
            new_data[CONF_ACCESS_TOKEN] = self._access_token
            new_data[CONF_REFRESH_TOKEN] = self._refresh_token
            new_data[CONF_TOKEN_EXPIRY] = self._token_expiry.isoformat() if self._token_expiry else None
            
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            _LOGGER.debug("Saved updated tokens to config entry")
        except Exception as e:
            _LOGGER.error("Failed to save tokens: %s", e)
    
    def get_id_token(self) -> str | None:
        """Get the current ID token."""
        if not self._id_token:
            _LOGGER.error("No ID token available")
            return None
        
        # Refresh if needed
        self.refresh_token()
        
        return self._id_token


class HiveScheduleAPI:
    """API client for Hive Schedule operations using beekeeper-uk endpoint."""
    
    BASE_URL = "https://beekeeper-uk.hivehome.com/1.0"
    
    def __init__(self, auth: HiveAuth) -> None:
        """Initialize the API client."""
        self.auth = auth
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://my.hivehome.com",
            "Referer": "https://my.hivehome.com/"
        })
    
    @staticmethod
    def time_to_minutes(time_str: str) -> int:
        """Convert time string to minutes from midnight."""
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    
    @staticmethod
    def minutes_to_time(minutes: int) -> str:
        """Convert minutes from midnight to time string."""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"
    
    def build_schedule_entry(self, time_str: str, temp: float) -> dict[str, Any]:
        """Build a single schedule entry in beekeeper format."""
        return {
            "value": {"target": float(temp)},
            "start": self.time_to_minutes(time_str)
        }
    
    def _log_api_call(self, method: str, url: str, headers: dict, payload: dict | None = None) -> None:
        """Log detailed API call information for debugging."""
        _LOGGER.debug("=" * 80)
        _LOGGER.debug("API CALL DEBUG INFO")
        _LOGGER.debug("=" * 80)
        _LOGGER.debug("Method: %s", method)
        _LOGGER.debug("URL: %s", url)
        _LOGGER.debug("-" * 80)
        _LOGGER.debug("Headers:")
        # Sanitize authorization header for logging
        safe_headers = headers.copy()
        if "Authorization" in safe_headers:
            token = safe_headers["Authorization"]
            if len(token) > 20:
                safe_headers["Authorization"] = f"{token[:10]}...{token[-10:]}"
        for key, value in safe_headers.items():
            _LOGGER.debug("  %s: %s", key, value)
        _LOGGER.debug("-" * 80)
        if payload:
            _LOGGER.debug("Payload (JSON):")
            _LOGGER.debug("%s", json.dumps(payload, indent=2))
        _LOGGER.debug("=" * 80)
    
    def _format_schedule_readable(self, schedule_data: dict, title: str = "SCHEDULE IN READABLE FORMAT") -> None:
        """Format and log schedule data in a human-readable way."""
        if not schedule_data or "schedule" not in schedule_data:
            return
        
        schedule = schedule_data["schedule"]
        
        _LOGGER.info("=" * 80)
        _LOGGER.info(title)
        _LOGGER.info("=" * 80)
        
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if day in schedule:
                entries = schedule[day]
                _LOGGER.info(f"{day.upper()}:")
                for entry in entries:
                    time_str = self.minutes_to_time(entry["start"])
                    temp = entry["value"]["target"]
                    _LOGGER.info(f"  {time_str} → {temp}°C")
        
        _LOGGER.info("=" * 80)
    
    def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> bool:
        """Send schedule update to Hive using beekeeper-uk API."""
        # Get fresh token
        token = self.auth.get_id_token()
        
        if not token:
            _LOGGER.error("Cannot update schedule: No auth token available")
            raise HomeAssistantError("Failed to authenticate with Hive")
        
        # Update session header with current token
        self.session.headers["Authorization"] = token
        
        url = f"{self.BASE_URL}/nodes/heating/{node_id}"
        
        try:
            # Log the API call details
            self._log_api_call("POST", url, self.session.headers, schedule_data)
            
            _LOGGER.info("Sending schedule update to %s", url)
            
            response = self.session.post(url, json=schedule_data, timeout=30)
            response.raise_for_status()
            
            _LOGGER.debug("Response status: %s", response.status_code)
            _LOGGER.debug("Response text: %s", response.text[:2000] if hasattr(response, 'text') else 'no response')
            
            # Parse and format the response to show what was actually set
            try:
                response_data = response.json()
                _LOGGER.info("Response from Hive API (showing what was set):")
                self._format_schedule_readable(response_data, "UPDATED SCHEDULE (confirmed by Hive)")
            except Exception as e:
                _LOGGER.debug(f"Could not parse response for readable format: {e}")
            
            _LOGGER.info("✓ Successfully updated Hive schedule for node %s", node_id)
            return True
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 401:
                _LOGGER.error("Authentication failed (401)")
                _LOGGER.error("Response: %s", err.response.text[:200] if hasattr(err.response, 'text') else 'no response')
                
                # Try to refresh token and retry once
                _LOGGER.info("Attempting to refresh token and retry...")
                if self.auth.refresh_token():
                    token = self.auth.get_id_token()
                    self.session.headers["Authorization"] = token
                    try:
                        self._log_api_call("POST", url, self.session.headers, schedule_data)
                        response = self.session.post(url, json=schedule_data, timeout=30)
                        response.raise_for_status()
                        _LOGGER.info("✓ Successfully updated Hive schedule after token refresh")
                        
                        try:
                            response_data = response.json()
                            self._format_schedule_readable(response_data, "UPDATED SCHEDULE (confirmed by Hive)")
                        except:
                            pass
                        
                        return True
                    except Exception as retry_err:
                        _LOGGER.error("Retry failed: %s", retry_err)
                
                raise HomeAssistantError("Hive authentication failed") from err
            if err.response.status_code == 404:
                _LOGGER.error("Node ID not found: %s", node_id)
                raise HomeAssistantError(f"Invalid node ID: {node_id}") from err
            _LOGGER.error("HTTP error updating schedule: %s", err)
            if hasattr(err.response, 'text'):
                _LOGGER.error("Response: %s", err.response.text[:500])
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err
        except requests.exceptions.Timeout as err:
            _LOGGER.error("Request to Hive API timed out")
            raise HomeAssistantError("Hive API request timed out") from err
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Request error updating schedule: %s", err)
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hive Schedule Manager from a config entry."""
    
    _LOGGER.info("=" * 80)
    _LOGGER.info("Hive Schedule Manager v1.1.17 Production")
    _LOGGER.info("POST-based schedule updates with YAML profiles")
    _LOGGER.info("=" * 80)
    
    # Initialize authentication and API
    auth = HiveAuth(hass, entry)
    api = HiveScheduleAPI(auth)
    
    # Load profiles asynchronously
    profiles = await _load_profiles(hass)
    _LOGGER.info("Loaded %d schedule profiles", len(profiles))
    
    # Check if we have tokens
    if not auth._id_token:
        _LOGGER.warning("No authentication tokens found in config entry")
    else:
        _LOGGER.info("Loaded authentication tokens from config entry")
        # Try to refresh token to ensure it's valid
        await hass.async_add_executor_job(auth.refresh_token)
    
    # Store in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "auth": auth,
        "api": api,
        "profiles": profiles,
    }
    
    # Set up periodic token refresh
    async def refresh_token_periodic(now=None):
        """Periodically refresh the authentication token."""
        await hass.async_add_executor_job(auth.refresh_token)
    
    entry.async_on_unload(
        async_track_time_interval(hass, refresh_token_periodic, DEFAULT_SCAN_INTERVAL)
    )
    
    # Service: Set day schedule
    async def handle_set_day(call: ServiceCall) -> None:
        """Handle set_day_schedule service call - updates only the specified day."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        profile = call.data.get(ATTR_PROFILE)
        custom_schedule = call.data.get(ATTR_SCHEDULE)
        
        # Reload profiles to pick up any changes (async)
        profiles = await _load_profiles(hass)
        
        # Determine which schedule to use
        if profile and custom_schedule:
            _LOGGER.warning("Both profile and schedule provided, using custom schedule")
            day_schedule = custom_schedule
        elif profile:
            if profile not in profiles:
                raise HomeAssistantError(f"Unknown profile '{profile}'. Available: {', '.join(profiles.keys())}")
            _LOGGER.info("Using profile '%s' for %s", profile, day)
            day_schedule = profiles[profile]
        elif custom_schedule:
            _LOGGER.info("Using custom schedule for %s", day)
            day_schedule = custom_schedule
        else:
            raise HomeAssistantError(
                "Either 'profile' or 'schedule' must be provided"
            )
        
        # Validate schedule
        try:
            _validate_schedule(day_schedule)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid schedule: {err}") from err
        
        _LOGGER.info("Setting schedule for %s on node %s", day, node_id)
        
        # Build schedule with ONLY the selected day (beekeeper format)
        schedule_data = {
            "schedule": {
                day: [
                    api.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in day_schedule
                ]
            }
        }
        
        # Send updated schedule to Hive
        await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)
        
        _LOGGER.info("Successfully updated %s schedule", day)
    
    # Register service
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DAY,
        handle_set_day,
        schema=SET_DAY_SCHEMA
    )
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    _LOGGER.info("Profiles file: %s", hass.config.path(PROFILES_FILE))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id)
    
    # Unregister services if this is the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_DAY)
    
    return True
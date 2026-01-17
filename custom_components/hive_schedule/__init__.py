"""
Hive Schedule Manager Integration for Home Assistant
Standalone with config flow and MFA support.
Version: 1.1.16 (Enhanced Debug)
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
import requests
from pycognito import Cognito

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
from .schedule_profiles import get_profile, get_available_profiles, validate_custom_schedule

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

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
            _LOGGER.debug("Schedule data: %s", json.dumps(schedule_data, indent=2))
            
            response = self.session.post(url, json=schedule_data, timeout=30)
            response.raise_for_status()
            
            _LOGGER.debug("Response status: %s", response.status_code)
            _LOGGER.debug("Response text: %s", response.text[:500] if hasattr(response, 'text') else 'no response')
            
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
    
    _LOGGER.info("Setting up Hive Schedule Manager v1.1.16 (Enhanced Debug)")
    
    # Initialize authentication and API
    auth = HiveAuth(hass, entry)
    api = HiveScheduleAPI(auth)
    
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
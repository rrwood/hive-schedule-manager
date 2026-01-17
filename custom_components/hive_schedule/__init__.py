"""
Hive Schedule Manager Integration for Home Assistant
Manages Hive heating schedules with profile support and config flow.
Version: 1.1.0
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
import requests
from pycognito import Cognito
from pycognito.exceptions import SMSMFAChallengeException
from botocore.exceptions import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import HomeAssistantError, ConfigEntryAuthFailed

from .const import (
    DOMAIN,
    COGNITO_POOL_ID,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    HIVE_API_URL,
    SERVICE_SET_DAY,
    ATTR_NODE_ID,
    ATTR_DAY,
    ATTR_SCHEDULE,
    ATTR_PROFILE,
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
    
    def __init__(self, username: str, password: str) -> None:
        """Initialize Hive authentication."""
        self.username = username
        self.password = password
        self._cognito = None
        self._id_token = None
        self._access_token = None
        self._token_expiry = None
    
    def authenticate(self) -> bool:
        """Authenticate with Hive via AWS Cognito.
        
        Note: This will raise SMSMFAChallengeException if MFA is required.
        During initial setup, the config flow handles MFA.
        After setup, credentials should work without MFA prompts.
        """
        try:
            _LOGGER.debug("Authenticating with Hive API...")
            
            self._cognito = Cognito(
                user_pool_id=COGNITO_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=self.username
            )
            
            try:
                self._cognito.authenticate(password=self.password)
                
                self._id_token = self._cognito.id_token
                self._access_token = self._cognito.access_token
                self._token_expiry = datetime.now() + timedelta(minutes=55)
                
                _LOGGER.info("Successfully authenticated with Hive")
                return True
                
            except SMSMFAChallengeException:
                # This shouldn't happen after initial setup
                # If it does, user needs to reconfigure the integration
                _LOGGER.error(
                    "MFA challenge received - this should not happen after initial setup. "
                    "Please remove and re-add the integration."
                )
                raise ConfigEntryAuthFailed(
                    "MFA required - please reconfigure the integration"
                )
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            _LOGGER.error("Authentication failed: %s - %s", error_code, str(e))
            return False
        except Exception as e:
            _LOGGER.error("Failed to authenticate with Hive: %s", e)
            return False
    
    def refresh_token(self) -> bool:
        """Refresh the authentication token if needed."""
        if not self._token_expiry or datetime.now() >= self._token_expiry - timedelta(minutes=5):
            _LOGGER.debug("Token expired or expiring soon, re-authenticating...")
            return self.authenticate()
        return True
    
    def get_token(self) -> str | None:
        """Get the current ID token."""
        self.refresh_token()
        return self._id_token


class HiveScheduleAPI:
    """API client for Hive schedule management."""
    
    def __init__(self, auth: HiveAuth) -> None:
        """Initialize the API client."""
        self.auth = auth
        self.base_url = HIVE_API_URL
    
    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        token = self.auth.get_token()
        if not token:
            raise HomeAssistantError("No valid authentication token available")
        
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "authorization": token,
        }
    
    def get_current_schedule(self, node_id: str) -> dict[str, Any]:
        """Retrieve the current schedule for a node.
        
        Args:
            node_id: The Hive node ID
            
        Returns:
            Dictionary containing the current schedule for all days
        """
        try:
            url = f"{self.base_url}/nodes/{node_id}"
            headers = self._get_headers()
            
            _LOGGER.debug("Getting current schedule from %s", url)
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract schedule from response
            if 'nodes' in data and len(data['nodes']) > 0:
                node_data = data['nodes'][0]
                if 'attributes' in node_data and 'schedule' in node_data['attributes']:
                    return node_data['attributes']['schedule']
            
            _LOGGER.warning("No schedule found in response, returning empty schedule")
            return {"schedule": {}}
            
        except requests.exceptions.HTTPError as err:
            _LOGGER.error("HTTP error getting schedule: %s", err)
            raise HomeAssistantError(f"Failed to get schedule: {err}") from err
        except requests.exceptions.Timeout:
            _LOGGER.error("Request timeout getting schedule")
            raise HomeAssistantError("Hive API request timed out")
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Request error getting schedule: %s", err)
            raise HomeAssistantError(f"Failed to get schedule: {err}") from err
    
    def build_schedule_entry(self, time: str, temp: float) -> dict[str, Any]:
        """Build a single schedule entry in Hive format.
        
        Args:
            time: Time in HH:MM format
            temp: Temperature in Celsius
            
        Returns:
            Dictionary in Hive schedule format
        """
        hours, minutes = time.split(":")
        start_time = int(hours) * 60 + int(minutes)
        
        return {
            "value": {
                "targetHeatTemperature": temp,
                "temperatureUnit": "C"
            },
            "start": start_time
        }
    
    def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> None:
        """Update the heating schedule for a node.
        
        Args:
            node_id: The Hive node ID
            schedule_data: Complete schedule data in Hive format
        """
        try:
            url = f"{self.base_url}/nodes/{node_id}"
            headers = self._get_headers()
            
            payload = {
                "nodes": [{
                    "attributes": schedule_data
                }]
            }
            
            _LOGGER.debug("Updating schedule at %s", url)
            
            response = requests.put(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            _LOGGER.info("Successfully updated schedule for node %s", node_id)
            
        except requests.exceptions.HTTPError as err:
            _LOGGER.error("HTTP error updating schedule: %s", err)
            if hasattr(err, 'response') and err.response is not None:
                _LOGGER.error("Response body: %s", err.response.text)
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err
        except requests.exceptions.Timeout:
            _LOGGER.error("Request timeout updating schedule")
            raise HomeAssistantError("Hive API request timed out")
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Request error updating schedule: %s", err)
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hive Schedule Manager from a config entry."""
    
    _LOGGER.info("Setting up Hive Schedule Manager v1.1.0")
    
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    
    # Initialize authentication and API
    auth = HiveAuth(username, password)
    api = HiveScheduleAPI(auth)
    
    # Initial authentication
    def initial_auth():
        """Perform initial authentication."""
        try:
            return auth.authenticate()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            _LOGGER.error("Authentication error: %s", err)
            return False
    
    try:
        success = await hass.async_add_executor_job(initial_auth)
        if not success:
            raise ConfigEntryAuthFailed("Failed to authenticate with Hive")
    except ConfigEntryAuthFailed:
        raise
    
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
        """Handle set_day_schedule service call - only updates the specified day."""
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
        
        # Get current schedule for all days
        current_schedule = await hass.async_add_executor_job(
            api.get_current_schedule, node_id
        )
        
        # Update only the specified day
        if "schedule" not in current_schedule:
            current_schedule["schedule"] = {}
        
        current_schedule["schedule"][day] = [
            api.build_schedule_entry(entry["time"], entry["temp"])
            for entry in day_schedule
        ]
        
        # Send updated schedule to Hive
        await hass.async_add_executor_job(api.update_schedule, node_id, current_schedule)
        
        _LOGGER.info("Successfully updated %s schedule", day)
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DAY,
        handle_set_day,
        schema=SET_DAY_SCHEMA
    )
    
    # Manual refresh service
    async def handle_refresh_token(call: ServiceCall) -> None:
        """Manually refresh the Hive authentication token."""
        _LOGGER.info("Manual token refresh requested")
        success = await hass.async_add_executor_job(auth.refresh_token)
        if success:
            _LOGGER.info("Token refresh successful")
        else:
            _LOGGER.error("Token refresh failed")
    
    hass.services.async_register(DOMAIN, "refresh_token", handle_refresh_token)
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id)
    
    # Unregister services if this is the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_DAY)
        hass.services.async_remove(DOMAIN, "refresh_token")
    
    return True
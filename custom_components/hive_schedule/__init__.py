"""
Hive Schedule Manager Integration for Home Assistant (Hybrid Version)
Uses own authentication but leverages Hive integration's API client for schedule updates.

Version: 2.1.0 (Hybrid)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
import json

import voluptuous as vol
from pycognito import Cognito
from pycognito.exceptions import SMSMFAChallengeException

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "hive_schedule"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

# Hive AWS Cognito configuration
COGNITO_POOL_ID = "eu-west-1_SamNfoWtf"
COGNITO_CLIENT_ID = "3rl4i0ajrmtdm8sbre54p9dvd9"
COGNITO_REGION = "eu-west-1"

# Service names
SERVICE_SET_SCHEDULE = "set_heating_schedule"
SERVICE_SET_DAY = "set_day_schedule"
SERVICE_UPDATE_FROM_CALENDAR = "update_from_calendar"
SERVICE_VERIFY_MFA = "verify_mfa_code"

# Attributes
ATTR_NODE_ID = "node_id"
ATTR_DAY = "day"
ATTR_SCHEDULE = "schedule"
ATTR_IS_WORKDAY = "is_workday"
ATTR_WAKE_TIME = "wake_time"
ATTR_MFA_CODE = "mfa_code"

# Configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Required(CONF_USERNAME): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
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

MFA_SCHEMA = vol.Schema({
    vol.Required(ATTR_MFA_CODE): cv.string,
})


class HiveAuth:
    """Handle Hive authentication via AWS Cognito with MFA support."""
    
    def __init__(self, username: str, password: str) -> None:
        """Initialize Hive authentication."""
        self.username = username
        self.password = password
        self._cognito = None
        self._id_token = None
        self._access_token = None
        self._refresh_token = None
        self._token_expiry = None
        self._mfa_required = False
        self._mfa_session = None
        self._mfa_session_token = None
    
    def authenticate(self) -> bool:
        """Authenticate with Hive via AWS Cognito."""
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
                self._refresh_token = self._cognito.refresh_token
                self._token_expiry = datetime.now() + timedelta(minutes=55)
                
                _LOGGER.info("✓ Successfully authenticated with Hive (token expires in ~55 minutes)")
                return True
                
            except SMSMFAChallengeException as mfa_ex:
                _LOGGER.warning("MFA code required for authentication")
                _LOGGER.info("Please call the 'hive_schedule.verify_mfa_code' service with your MFA code")
                
                self._mfa_required = True
                self._mfa_session = self._cognito
                self._mfa_session_token = mfa_ex.get_session()
                
                return False
            
        except Exception as e:
            _LOGGER.error("Failed to authenticate with Hive: %s", e)
            return False
    
    def verify_mfa_code(self, mfa_code: str) -> bool:
        """Verify MFA code and complete authentication."""
        # Clean the code - remove spaces, dashes, etc.
        mfa_code = mfa_code.strip().replace(' ', '').replace('-', '')
        
        if not mfa_code.isdigit() or len(mfa_code) != 6:
            _LOGGER.error("Invalid MFA code format. Expected 6 digits, got: '%s'", mfa_code)
            return False
        
        if not self._mfa_required:
            _LOGGER.warning("MFA not required - you may already be authenticated")
            return False
        
        if not self._mfa_session or not self._mfa_session_token:
            _LOGGER.error("No MFA session available - the session may have expired")
            _LOGGER.info("Attempting to re-authenticate to get a fresh MFA session...")
            
            # Re-authenticate to get a fresh MFA challenge
            if not self.authenticate():
                _LOGGER.error("Re-authentication failed")
                return False
            
            if not self._mfa_required:
                _LOGGER.info("✓ Re-authentication succeeded without MFA")
                return True
            
            _LOGGER.info("Got fresh MFA session, please try entering your code again")
            return False
        
        try:
            _LOGGER.info("Verifying MFA code: %s", mfa_code)
            _LOGGER.debug("Session token exists: %s", bool(self._mfa_session_token))
            
            self._mfa_session.respond_to_sms_mfa_challenge(
                mfa_code,
                self._mfa_session_token
            )
            
            if not self._mfa_session.id_token:
                _LOGGER.error("MFA verification failed - no tokens received")
                return False
            
            self._id_token = self._mfa_session.id_token
            self._access_token = self._mfa_session.access_token
            self._refresh_token = self._mfa_session.refresh_token
            self._token_expiry = datetime.now() + timedelta(minutes=55)
            self._mfa_required = False
            self._mfa_session = None
            self._mfa_session_token = None
            
            _LOGGER.info("✓ MFA verification successful - authenticated with Hive")
            return True
            
        except Exception as e:
            error_msg = str(e)
            _LOGGER.error("MFA verification failed: %s", error_msg)
            
            if "CodeMismatchException" in error_msg or "Invalid code" in error_msg:
                _LOGGER.error("The code you entered is incorrect or has expired")
                _LOGGER.info("Request a new code and try again, or restart HA to get a fresh session")
            elif "auth state" in error_msg.lower():
                _LOGGER.error("The MFA session has expired")
                _LOGGER.info("Restart Home Assistant to get a fresh MFA session")
            
            return False
    
    def is_mfa_required(self) -> bool:
        """Check if MFA is required."""
        return self._mfa_required
    
    def refresh_token(self) -> bool:
        """Refresh the authentication token if needed."""
        if not self._token_expiry or datetime.now() >= self._token_expiry:
            _LOGGER.info("Token expired or missing, re-authenticating...")
            return self.authenticate()
        
        try:
            if self._cognito and self._refresh_token:
                _LOGGER.debug("Refreshing token...")
                self._cognito.renew_access_token()
                self._id_token = self._cognito.id_token
                self._access_token = self._cognito.access_token
                self._token_expiry = datetime.now() + timedelta(minutes=55)
                _LOGGER.info("✓ Token refreshed successfully")
                return True
        except Exception as e:
            _LOGGER.warning("Token refresh failed, re-authenticating: %s", e)
            return self.authenticate()
        
        return False
    
    def get_id_token(self) -> str | None:
        """Get the current ID token, refreshing if needed."""
        if not self._id_token or datetime.now() >= self._token_expiry:
            self.refresh_token()
        return self._id_token
    
    def get_access_token(self) -> str | None:
        """Get the current access token, refreshing if needed."""
        if not self._access_token or datetime.now() >= self._token_expiry:
            self.refresh_token()
        return self._access_token


class HiveScheduleAPI:
    """API client for Hive Schedule operations using Hive integration's client."""
    
    def __init__(self, hass: HomeAssistant, auth: HiveAuth) -> None:
        """Initialize the API client."""
        self.hass = hass
        self.auth = auth
    
    @staticmethod
    def time_to_minutes(time_str: str) -> int:
        """Convert time string to minutes from midnight."""
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    
    @staticmethod
    def build_schedule_entry(time_str: str, temp: float) -> dict[str, Any]:
        """Build a single schedule entry."""
        return {
            "value": {"target": float(temp)},
            "start": HiveScheduleAPI.time_to_minutes(time_str)
        }
    
    def _get_hive_session(self):
        """Get the Hive API session from the official integration."""
        hive_entries = self.hass.config_entries.async_entries("hive")
        
        if not hive_entries:
            raise HomeAssistantError("Hive integration not installed or not configured")
        
        for entry in hive_entries:
            if hasattr(entry, 'runtime_data') and entry.runtime_data:
                return entry.runtime_data
        
        raise HomeAssistantError("Hive integration not loaded")
    
    def _inject_our_token(self, hive_session) -> bool:
        """Inject our authentication token into the Hive session."""
        try:
            our_token = self.auth.get_id_token()
            
            if not our_token:
                _LOGGER.error("No authentication token available")
                return False
            
            # Update the Hive session's auth with our token
            if hasattr(hive_session, 'auth'):
                _LOGGER.debug("Injecting our auth token into Hive session")
                
                # Try to update various token storage locations
                if hasattr(hive_session.auth, 'access_token'):
                    hive_session.auth.access_token = our_token
                if hasattr(hive_session.auth, 'id_token'):
                    hive_session.auth.id_token = our_token
                if hasattr(hive_session.auth, '_id_token'):
                    hive_session.auth._id_token = our_token
                
                return True
            
            return False
            
        except Exception as e:
            _LOGGER.warning("Could not inject token: %s", e)
            return False
    
    async def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> bool:
        """Update the heating schedule using Hive integration's API."""
        try:
            # Get the Hive session
            hive_session = await self.hass.async_add_executor_job(self._get_hive_session)
            
            # Inject our authentication token
            self._inject_our_token(hive_session)
            
            # The apyhiveapi library has methods that handle authentication internally
            # We need to use their heating module's methods
            
            if hasattr(hive_session, 'heating'):
                heating_module = hive_session.heating
                
                # Try to find a method to update the schedule
                # The apyhiveapi might have methods like set_schedule, update_schedule, etc.
                _LOGGER.debug("Heating module methods: %s", [m for m in dir(heating_module) if not m.startswith('_')])
                
                # Look for schedule-related methods
                for method_name in ['setSchedule', 'set_schedule', 'updateSchedule', 'update_schedule', 'put_schedule']:
                    if hasattr(heating_module, method_name):
                        method = getattr(heating_module, method_name)
                        _LOGGER.info("Found method: %s", method_name)
                        
                        try:
                            # Try calling with different parameter combinations
                            result = await self.hass.async_add_executor_job(
                                method, node_id, schedule_data
                            )
                            _LOGGER.info("✓ Successfully updated Hive schedule using %s", method_name)
                            return True
                        except Exception as e:
                            _LOGGER.debug("Method %s failed: %s", method_name, e)
                            continue
            
            # Fallback: Use the Hive API's low-level request method
            if hasattr(hive_session, 'api') and hasattr(hive_session.api, 'request'):
                api = hive_session.api
                
                _LOGGER.info("Attempting to use Hive's api.request method")
                
                # The apyhiveapi's request method should handle auth internally
                result = await self.hass.async_add_executor_job(
                    api.request,
                    'PUT',
                    f'https://beekeeper-uk.hivehome.com/1.0/nodes/heating/{node_id}',
                    schedule_data
                )
                
                if result:
                    _LOGGER.info("✓ Successfully updated Hive schedule")
                    return True
                else:
                    _LOGGER.error("API request returned no result")
                    return False
            
            # Last resort: Check if there's a working authenticated session we can use
            _LOGGER.error("Could not find suitable API method in Hive integration")
            _LOGGER.error("Available methods on hive_session: %s", [m for m in dir(hive_session) if not m.startswith('_')])
            
            if hasattr(hive_session, 'api'):
                _LOGGER.error("Available methods on api: %s", [m for m in dir(hive_session.api) if not m.startswith('_')])
            
            return False
            
        except HomeAssistantError as e:
            _LOGGER.error("%s", str(e))
            _LOGGER.error("Please ensure the Hive integration is installed and configured")
            return False
        except Exception as e:
            _LOGGER.error("Error updating schedule: %s", e)
            import traceback
            _LOGGER.debug("Traceback: %s", traceback.format_exc())
            return False


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Hive Schedule Manager component."""
    
    _LOGGER.info("Setting up Hive Schedule Manager (Hybrid v2.1)")
    
    # Get configuration
    conf = config.get(DOMAIN, {})
    username = conf.get(CONF_USERNAME)
    password = conf.get(CONF_PASSWORD)
    scan_interval = conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    if not username or not password:
        _LOGGER.error("Hive username and password are required in configuration.yaml")
        return False
    
    # Check if Hive integration is available
    hive_entries = hass.config_entries.async_entries("hive")
    if not hive_entries:
        _LOGGER.error("Hive integration not found - it MUST be installed for this hybrid version to work!")
        _LOGGER.error("Please install the official Hive integration first")
        return False
    
    # Initialize authentication and API
    auth = HiveAuth(username, password)
    api = HiveScheduleAPI(hass, auth)
    
    # Store in hass.data
    hass.data[DOMAIN] = {
        "auth": auth,
        "api": api
    }
    
    # Initial authentication
    def initial_auth():
        """Perform initial authentication."""
        if not auth.authenticate():
            if auth.is_mfa_required():
                _LOGGER.warning("MFA code required - call hive_schedule.verify_mfa_code service")
                return True  # Don't fail setup, just wait for MFA
            else:
                _LOGGER.error("Initial authentication failed - check your Hive username and password")
                return False
        return True
    
    if not await hass.async_add_executor_job(initial_auth):
        _LOGGER.warning("Failed to authenticate on startup - will retry")
    
    # Set up periodic token refresh
    async def refresh_token_periodic(now=None):
        """Periodically refresh the authentication token."""
        if not auth.is_mfa_required():
            await hass.async_add_executor_job(auth.refresh_token)
    
    async_track_time_interval(hass, refresh_token_periodic, scan_interval)
    
    # Service handlers
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
                        HiveScheduleAPI.build_schedule_entry(entry["time"], entry["temp"])
                    )
                schedule_data["schedule"][day] = day_schedule
            else:
                schedule_data["schedule"][day] = [
                    HiveScheduleAPI.build_schedule_entry("00:00", 16.0)
                ]
        
        success = await api.update_schedule(node_id, schedule_data)
        if not success:
            raise HomeAssistantError("Failed to update schedule")
    
    async def handle_set_day(call: ServiceCall) -> None:
        """Handle set_day_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        day_schedule = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info("Setting schedule for %s on node %s", day, node_id)
        
        # Default schedule for other days
        default_schedule = [
            HiveScheduleAPI.build_schedule_entry("00:00", 16.0),
            HiveScheduleAPI.build_schedule_entry("08:00", 18.0),
            HiveScheduleAPI.build_schedule_entry("22:00", 16.0)
        ]
        
        schedule_data: dict[str, Any] = {"schedule": {}}
        
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d == day:
                schedule_data["schedule"][d] = [
                    HiveScheduleAPI.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in day_schedule
                ]
            else:
                schedule_data["schedule"][d] = default_schedule
        
        success = await api.update_schedule(node_id, schedule_data)
        if not success:
            raise HomeAssistantError(f"Failed to update schedule for {day}")
    
    async def handle_calendar_update(call: ServiceCall) -> None:
        """Handle update_from_calendar service call."""
        node_id = call.data[ATTR_NODE_ID]
        is_workday = call.data[ATTR_IS_WORKDAY]
        wake_time = call.data.get(ATTR_WAKE_TIME, "06:30" if is_workday else "07:30")
        
        tomorrow = datetime.now() + timedelta(days=1)
        day = tomorrow.strftime("%A").lower()
        
        _LOGGER.info("Updating %s schedule from calendar (workday=%s)", day, is_workday)
        
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
        
        await handle_set_day(
            ServiceCall(
                DOMAIN,
                SERVICE_SET_DAY,
                {ATTR_NODE_ID: node_id, ATTR_DAY: day, ATTR_SCHEDULE: day_schedule}
            )
        )
    
    async def handle_verify_mfa(call: ServiceCall) -> None:
        """Handle MFA code verification."""
        mfa_code = call.data[ATTR_MFA_CODE]
        
        _LOGGER.info("MFA verification requested")
        
        success = await hass.async_add_executor_job(auth.verify_mfa_code, mfa_code)
        
        if success:
            _LOGGER.info("✓ MFA verification successful - you can now use the schedule services")
        else:
            raise HomeAssistantError("MFA verification failed - check your code and try again")
    
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
    
    hass.services.async_register(
        DOMAIN, SERVICE_VERIFY_MFA, handle_verify_mfa, schema=MFA_SCHEMA
    )
    
    # Manual refresh service
    async def handle_refresh_token(call: ServiceCall) -> None:
        """Manually refresh the Hive authentication token."""
        _LOGGER.info("Manual token refresh requested")
        
        if auth.is_mfa_required():
            _LOGGER.warning("Cannot refresh - MFA code required first")
            raise HomeAssistantError("MFA verification required - call verify_mfa_code service first")
        
        success = await hass.async_add_executor_job(auth.refresh_token)
        if success:
            _LOGGER.info("✓ Token refresh successful")
        else:
            _LOGGER.error("✗ Token refresh failed")
            raise HomeAssistantError("Token refresh failed")
    
    hass.services.async_register(DOMAIN, "refresh_token", handle_refresh_token)
    
    # Diagnostic service to explore Hive API
    async def handle_diagnose_hive_api(call: ServiceCall) -> None:
        """Diagnose what methods are available in the Hive integration."""
        try:
            hive_session = await hass.async_add_executor_job(api._get_hive_session)
            
            _LOGGER.warning("=" * 80)
            _LOGGER.warning("HIVE API DIAGNOSTIC")
            _LOGGER.warning("=" * 80)
            
            _LOGGER.warning("Hive session type: %s", type(hive_session).__name__)
            _LOGGER.warning("Hive session attributes: %s", [a for a in dir(hive_session) if not a.startswith('_')][:20])
            
            if hasattr(hive_session, 'heating'):
                _LOGGER.warning("")
                _LOGGER.warning("Heating module found!")
                _LOGGER.warning("Heating methods: %s", [m for m in dir(hive_session.heating) if not m.startswith('_')])
            
            if hasattr(hive_session, 'api'):
                _LOGGER.warning("")
                _LOGGER.warning("API module found!")
                _LOGGER.warning("API methods: %s", [m for m in dir(hive_session.api) if not m.startswith('_')][:20])
                
                if hasattr(hive_session.api, 'request'):
                    _LOGGER.warning("  → api.request method exists!")
                if hasattr(hive_session.api, 'http'):
                    _LOGGER.warning("  → api.http method exists!")
            
            _LOGGER.warning("=" * 80)
            
        except Exception as e:
            _LOGGER.error("Diagnostic failed: %s", e)
            import traceback
            _LOGGER.error("Traceback: %s", traceback.format_exc())
    
    hass.services.async_register(DOMAIN, "diagnose_hive_api", handle_diagnose_hive_api)
    
    # Service to re-trigger MFA
    async def handle_request_mfa(call: ServiceCall) -> None:
        """Re-authenticate to get a fresh MFA code."""
        _LOGGER.info("Re-authentication requested to get fresh MFA session")
        
        success = await hass.async_add_executor_job(auth.authenticate)
        
        if not success:
            if auth.is_mfa_required():
                _LOGGER.info("✓ MFA code sent - check your SMS and call verify_mfa_code")
            else:
                raise HomeAssistantError("Authentication failed - check your credentials")
        else:
            _LOGGER.info("✓ Authentication successful without MFA")
    
    hass.services.async_register(DOMAIN, "request_new_mfa", handle_request_mfa)
    
    _LOGGER.info("✓ Hive Schedule Manager setup complete (Hybrid v2.1)")
    _LOGGER.info("This version uses the official Hive integration's API client with your own authentication")
    return True
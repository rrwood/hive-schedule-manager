"""
Hive Schedule Manager Integration for Home Assistant (Standalone Version)
Handles its own authentication with Hive API independently.

Version: 2.0.0 (Standalone)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
import json
import traceback

import voluptuous as vol
import requests
from pycognito import Cognito
from pycognito.exceptions import SMSMFAChallengeException
from botocore.exceptions import ClientError

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
ATTR_MFA_CODE = "code"

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
    """Handle Hive authentication via AWS Cognito."""
    
    def __init__(self, username: str, password: str) -> None:
        """Initialize Hive authentication."""
        self.username = username
        self.password = password
        self._cognito = None
        self._id_token = None
        self._access_token = None
        self._token_expiry = None
        self._mfa_required = False
        self._mfa_session = None
        self._mfa_session_token = None
    
    def authenticate(self, mfa_code: str | None = None) -> bool:
        """Authenticate with Hive via AWS Cognito."""
        try:
            _LOGGER.debug("Authenticating with Hive API...")
            
            self._cognito = Cognito(
                user_pool_id=COGNITO_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=self.username
            )
            
            if mfa_code:
                return self.verify_mfa(mfa_code)
            
            try:
                self._cognito.authenticate(password=self.password)
            except SMSMFAChallengeException as mfa_error:
                _LOGGER.debug("SMSMFAChallengeException caught during authentication")
                self._mfa_required = True
                self._mfa_session = self._cognito
                
                if len(mfa_error.args) > 1 and isinstance(mfa_error.args[1], dict):
                    challenge_params = mfa_error.args[1]
                    self._mfa_session_token = challenge_params.get('Session')
                
                _LOGGER.info("MFA required - SMS code has been sent to your registered phone")
                return False
            except ClientError as auth_error:
                error_code = auth_error.response.get("Error", {}).get("Code", "")
                error_message = str(auth_error)
                
                if error_code in ["UserMFATypeNotFound", "SMS_MFA", "SOFTWARE_TOKEN_MFA"] or "mfa" in error_message.lower():
                    self._mfa_required = True
                    self._mfa_session = self._cognito
                    _LOGGER.info("MFA required - SMS code has been sent to your registered phone")
                    return False
                
                raise
            
            self._id_token = self._cognito.id_token
            self._access_token = self._cognito.access_token
            self._token_expiry = datetime.now() + timedelta(minutes=55)
            self._mfa_required = False
            
            _LOGGER.info("✓ Successfully authenticated with Hive (token expires in ~55 minutes)")
            return True
            
        except Exception as e:
            _LOGGER.error("Failed to authenticate with Hive: %s", e)
            return False
    
    def verify_mfa(self, mfa_code: str) -> bool:
        """Verify MFA code and complete authentication."""
        try:
            if not self._mfa_session or not self._mfa_required:
                _LOGGER.error("No active MFA session - cannot verify code")
                return False
            
            _LOGGER.debug("Verifying MFA code...")
            
            if hasattr(self._mfa_session, 'client'):
                client = self._mfa_session.client
                
                challenge_responses = {
                    "USERNAME": str(self.username),
                    "SMS_MFA_CODE": str(mfa_code)
                }
                
                response = client.respond_to_auth_challenge(
                    ClientId=COGNITO_CLIENT_ID,
                    ChallengeName="SMS_MFA",
                    Session=self._mfa_session_token,
                    ChallengeResponses=challenge_responses
                )
                
                auth_result = response.get("AuthenticationResult", {})
                if auth_result:
                    self._mfa_session.id_token = auth_result.get("IdToken")
                    self._mfa_session.access_token = auth_result.get("AccessToken")
                else:
                    _LOGGER.error("No AuthenticationResult in response")
                    return False
            else:
                _LOGGER.error("Cannot access boto3 client from cognito session")
                return False
            
            self._id_token = self._mfa_session.id_token
            self._access_token = self._mfa_session.access_token
            self._token_expiry = datetime.now() + timedelta(minutes=55)
            self._mfa_required = False
            self._mfa_session = None
            self._mfa_session_token = None
            
            _LOGGER.info("✓ MFA verification successful - authenticated with Hive")
            return True
            
        except Exception as e:
            _LOGGER.error("MFA verification failed: %s", e)
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
            if self._cognito:
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
    """API client for Hive Schedule operations."""
    
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
        """Build a single schedule entry."""
        return {
            "value": {"target": float(temp)},
            "start": self.time_to_minutes(time_str)
        }
    
    def get_schedule(self, node_id: str) -> dict[str, Any] | None:
        """Fetch current schedule from Hive - try multiple endpoints and methods."""
        # Try both ID token and access token
        id_token = self.auth.get_id_token()
        access_token = self.auth.get_access_token()
        
        if not id_token:
            _LOGGER.error("Cannot get schedule: No auth token available")
            return None
        
        tokens_to_try = [
            ("ID Token", id_token),
            ("Access Token", access_token) if access_token else None
        ]
        tokens_to_try = [t for t in tokens_to_try if t is not None]
        
        endpoints_to_try = [
            f"{self.BASE_URL}/nodes/heating/{node_id}",
            f"{self.BASE_URL}/heating/{node_id}",
            f"{self.BASE_URL}/schedules/{node_id}",
        ]
        
        for token_name, token in tokens_to_try:
            _LOGGER.info("Trying with %s", token_name)
            self.session.headers["Authorization"] = f"Bearer {token}"
            
            for url in endpoints_to_try:
                try:
                    _LOGGER.debug("Attempting to fetch schedule from: %s with %s", url, token_name)
                    response = self.session.get(url, timeout=30)
                    
                    _LOGGER.info("Response status from %s: %d", url, response.status_code)
                    
                    if response.status_code == 403:
                        _LOGGER.warning("Access forbidden (403)")
                        continue
                    
                    if response.status_code == 404:
                        _LOGGER.debug("Not found (404) - trying next endpoint")
                        continue
                    
                    response.raise_for_status()
                    
                    data = response.json()
                    _LOGGER.info("✓ Successfully fetched schedule from %s with %s", url, token_name)
                    _LOGGER.info("Response: %s", json.dumps(data, indent=2, default=str)[:500])
                    
                    if isinstance(data, dict) and "schedule" in data:
                        return data.get("schedule")
                    
                    return data
                    
                except Exception as err:
                    _LOGGER.debug("Error fetching from %s: %s", url, err)
                    continue
        
        _LOGGER.error("Could not fetch schedule from any endpoint for node %s", node_id)
        return None
    
    def _extract_schedule_from_devices(self, devices_data: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        """Extract schedule for a specific node from the devices response."""
        _LOGGER.info("=== STARTING SCHEDULE EXTRACTION ===")
        _LOGGER.info("Looking for node_id: %s", node_id)
        
        try:
            # Write ENTIRE response to file for inspection FIRST
            try:
                import os
                config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                debug_file = os.path.join(config_dir, "hive_all_devices_debug.json")
                
                with open(debug_file, 'w') as f:
                    json.dump(devices_data, f, indent=2, default=str)
                
                _LOGGER.info("✓ Wrote ALL devices response to: %s", debug_file)
            except Exception as e:
                _LOGGER.error("Could not write all devices debug file: %s", e)
            
            # Structure 1: Check if it's a list
            if isinstance(devices_data, list):
                _LOGGER.info("Response is a list with %d items", len(devices_data))
                
                # First, log all top-level IDs
                top_level_ids = []
                for idx, device in enumerate(devices_data):
                    device_id = device.get("id") if isinstance(device, dict) else "N/A"
                    top_level_ids.append(device_id)
                    device_keys = list(device.keys()) if isinstance(device, dict) else "N/A"
                    device_type = device.get("type") if isinstance(device, dict) else "N/A"
                    _LOGGER.info("Item %d: id=%s, type=%s, keys=%s", idx, device_id, device_type, device_keys)
                
                _LOGGER.info("Top-level device IDs: %s", top_level_ids)
                
                # Now search recursively in all devices for the target node_id
                _LOGGER.info("Searching recursively for node_id: %s", node_id)
                for idx, device in enumerate(devices_data):
                    device_id = device.get("id") if isinstance(device, dict) else "N/A"
                    _LOGGER.debug("Searching in device %d (id=%s)", idx, device_id)
                    
                    # Search this device for the node_id
                    schedule = self._find_schedule_in_object(device, node_id)
                    if schedule:
                        _LOGGER.info("✓ Found schedule for node_id %s in device %d", node_id, idx)
                        return schedule
                
                _LOGGER.warning("Could not find node_id %s in any device", node_id)
                _LOGGER.info("Target node_id: %s", node_id)
                _LOGGER.info("Available top-level IDs: %s", top_level_ids)
                return None
            
            # Structure 2: Check if it's a dict
            elif isinstance(devices_data, dict):
                _LOGGER.info("Response is a dict with %d keys", len(devices_data))
                all_keys = list(devices_data.keys())
                _LOGGER.info("Dict keys: %s", all_keys)
                
                # Try to directly find the node_id as a key
                if node_id in devices_data:
                    _LOGGER.info("✓ Found node_id as direct key in response")
                    node_data = devices_data[node_id]
                    if isinstance(node_data, dict) and "schedule" in node_data:
                        _LOGGER.info("✓ Found schedule in direct node_id entry")
                        return node_data.get("schedule")
                
                # Recursively search all values
                _LOGGER.info("Searching recursively in dict values for node_id: %s", node_id)
                for key, value in devices_data.items():
                    if isinstance(value, (dict, list)):
                        result = self._find_schedule_in_object(value, node_id, 0, f"[key={key}]")
                        if result:
                            return result
                
                _LOGGER.warning("Could not find node_id %s in dict", node_id)
                return None
            
            _LOGGER.warning("Response is neither list nor dict, it's: %s", type(devices_data))
            return None
            
        except Exception as err:
            _LOGGER.error("Error extracting schedule from devices: %s", err)
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return None
    
    def _find_schedule_in_object(self, obj: Any, node_id: str, depth: int = 0, path: str = "") -> dict[str, Any] | None:
        """Recursively find schedule in an object, optionally associated with a node_id."""
        if depth > 15:  # Prevent infinite recursion
            return None
        
        if isinstance(obj, dict):
            current_id = obj.get("id", "")
            current_path = f"{path}[id={current_id}]" if current_id else path
            
            # Log if we find the target node_id
            if current_id == node_id:
                _LOGGER.info("Found target node_id at depth %d, path: %s", depth, current_path)
            
            # If this object has schedule, check if it matches our node_id
            if "schedule" in obj:
                obj_id = obj.get("id")
                if obj_id is None or obj_id == node_id:
                    _LOGGER.info("✓ Found schedule at depth %d, path: %s", depth, current_path)
                    return obj.get("schedule")
            
            # Recursively search nested dicts
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    result = self._find_schedule_in_object(value, node_id, depth + 1, f"{current_path}.{key}")
                    if result:
                        return result
        
        elif isinstance(obj, list):
            # Recursively search list items
            for idx, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    result = self._find_schedule_in_object(item, node_id, depth + 1, f"{path}[{idx}]")
                    if result:
                        return result
        
        return None
    
    def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> bool:
        """Update the heating schedule for a node."""
        # Try both ID token and access token
        id_token = self.auth.get_id_token()
        access_token = self.auth.get_access_token()
        
        if not id_token:
            _LOGGER.error("Cannot update schedule: No auth token available")
            return False
        
        tokens_to_try = [
            ("ID Token", id_token),
            ("Access Token", access_token) if access_token else None
        ]
        tokens_to_try = [t for t in tokens_to_try if t is not None]
        
        endpoints_to_try = [
            f"{self.BASE_URL}/nodes/heating/{node_id}",
            f"{self.BASE_URL}/heating/{node_id}",
            f"{self.BASE_URL}/schedules/{node_id}",
        ]
        
        for token_name, token in tokens_to_try:
            _LOGGER.info("Trying update with %s", token_name)
            _LOGGER.debug("Token (first 50 chars): %s...", token[:50] if token else "None")
            self.session.headers["Authorization"] = f"Bearer {token}"
            
            for url in endpoints_to_try:
                try:
                    _LOGGER.info("Attempting to update schedule at: %s with %s", url, token_name)
                    _LOGGER.debug("Payload: %s", json.dumps(schedule_data, indent=2, default=str))
                    response = self.session.put(url, json=schedule_data, timeout=30)
                    
                    _LOGGER.info("Response status from %s: %d", url, response.status_code)
                    _LOGGER.debug("Response headers: %s", dict(response.headers))
                    
                    if response.text:
                        _LOGGER.debug("Response body: %s", response.text[:500])
                    
                    if response.status_code == 403:
                        _LOGGER.warning("Access forbidden (403)")
                        continue
                    
                    if response.status_code == 404:
                        _LOGGER.debug("Not found (404) - trying next endpoint")
                        continue
                    
                    response.raise_for_status()
                    _LOGGER.info("✓ Successfully updated schedule at %s with %s", url, token_name)
                    return True
                    
                except Exception as err:
                    _LOGGER.debug("Error updating schedule at %s: %s", url, err)
                    continue
        
        _LOGGER.error("Could not update schedule at any endpoint for node %s", node_id)
        return False

async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Hive Schedule Manager component."""
    
    _LOGGER.info("Setting up Hive Schedule Manager (Standalone v2.0)")
    
    conf = config.get(DOMAIN, {})
    username = conf.get(CONF_USERNAME)
    password = conf.get(CONF_PASSWORD)
    scan_interval = conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    if not username or not password:
        _LOGGER.error("Hive username and password are required in configuration.yaml")
        return False
    
    auth = HiveAuth(username, password)
    api = HiveScheduleAPI(auth)
    
    hass.data[DOMAIN] = {
        "auth": auth,
        "api": api
    }
    
    def initial_auth():
        """Perform initial authentication."""
        if not auth.authenticate():
            if auth.is_mfa_required():
                _LOGGER.warning("MFA required - waiting for user to provide SMS code via verify_mfa_code service")
                return False
            _LOGGER.error("Initial authentication failed - check your Hive username and password")
            return False
        return True
    
    if not await hass.async_add_executor_job(initial_auth):
        if not auth.is_mfa_required():
            _LOGGER.warning("Failed to authenticate on startup - will retry")
    
    async def refresh_token_periodic(now=None):
        """Periodically refresh the authentication token."""
        await hass.async_add_executor_job(auth.refresh_token)
    
    async_track_time_interval(hass, refresh_token_periodic, scan_interval)
    
    async def handle_verify_mfa(call: ServiceCall) -> None:
        """Handle MFA code verification."""
        mfa_code = call.data.get(ATTR_MFA_CODE)
        if not mfa_code:
            _LOGGER.error("MFA code not provided")
            return
        
        _LOGGER.info("Verifying MFA code...")
        success = await hass.async_add_executor_job(auth.verify_mfa, mfa_code)
        
        if success:
            _LOGGER.info("✓ MFA verified successfully - integration setup complete")
        else:
            _LOGGER.error("✗ MFA verification failed - invalid code")
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_VERIFY_MFA,
        handle_verify_mfa,
        schema=MFA_SCHEMA
    )
    
    async def handle_set_schedule(call: ServiceCall) -> None:
        """Handle set_heating_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        schedule_config = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info("Setting complete schedule for node %s", node_id)
        
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
                schedule_data["schedule"][day] = [
                    api.build_schedule_entry("00:00", 16.0)
                ]
        
        await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)
    
    async def handle_set_day(call: ServiceCall) -> None:
        """Handle set_day_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        day_schedule = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info("Setting schedule for %s on node %s", day, node_id)
        _LOGGER.debug("New schedule for %s: %s", day, day_schedule)
        
        # For set_day_schedule, we'll create a complete week with the new day
        # and default schedules for other days
        schedule_data: dict[str, Any] = {"schedule": {}}
        
        default_schedule = [
            api.build_schedule_entry("00:00", 16.0),
            api.build_schedule_entry("08:00", 18.0),
            api.build_schedule_entry("22:00", 16.0)
        ]
        
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d == day:
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in day_schedule
                ]
                _LOGGER.info("Updated %s with new schedule: %s", d, json.dumps(schedule_data["schedule"][d], indent=2))
            else:
                # Use default schedule for other days
                schedule_data["schedule"][d] = default_schedule
                _LOGGER.info("Set %s to default schedule", d)
        
        _LOGGER.info("Complete schedule to send: %s", json.dumps(schedule_data, indent=2, default=str))
        success = await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)
        
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
    
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, schema=SET_SCHEDULE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DAY, handle_set_day, schema=SET_DAY_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_FROM_CALENDAR, handle_calendar_update, schema=CALENDAR_SCHEMA
    )
    
    async def handle_refresh_token(call: ServiceCall) -> None:
        """Manually refresh the Hive authentication token."""
        _LOGGER.info("Manual token refresh requested")
        success = await hass.async_add_executor_job(auth.refresh_token)
        if success:
            _LOGGER.info("✓ Token refresh successful")
        else:
            _LOGGER.error("✗ Token refresh failed")
    
    hass.services.async_register(DOMAIN, "refresh_token", handle_refresh_token)
    
    _LOGGER.info("✓ Hive Schedule Manager setup complete (Standalone v2.0)")
    return True
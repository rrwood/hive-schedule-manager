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
        token = self.auth.get_id_token()
        
        if not token:
            _LOGGER.error("Cannot get schedule: No auth token available")
            return None
        
        self.session.headers["Authorization"] = token
        
        # First try direct endpoints
        endpoints_to_try = [
            (f"{self.BASE_URL}/nodes/heating/{node_id}", "GET"),
            (f"{self.BASE_URL}/nodes/{node_id}", "GET"),
            (f"{self.BASE_URL}/heating/{node_id}", "GET"),
        ]
        
        for url, method in endpoints_to_try:
            try:
                _LOGGER.debug("Attempting to fetch schedule: %s %s", method, url)
                response = self.session.get(url, timeout=30)
                
                if response.status_code in [403, 404]:
                    _LOGGER.debug("Status %s - trying next endpoint", response.status_code)
                    continue
                
                response.raise_for_status()
                
                data = response.json()
                _LOGGER.info("✓ Successfully fetched schedule from %s", url)
                
                if "schedule" in data:
                    return data.get("schedule")
                
            except Exception as err:
                _LOGGER.debug("Error fetching from %s: %s", url, err)
                continue
        
        # If direct endpoints fail, fetch all devices and extract schedule for this node
        _LOGGER.info("Direct endpoints failed, attempting to fetch from /devices endpoint")
        try:
            devices_url = f"{self.BASE_URL}/devices"
            _LOGGER.info("Fetching devices from: %s", devices_url)
            response = self.session.get(devices_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            _LOGGER.info("Successfully received devices response, attempting to extract schedule")
            
            # Try to find the node in various structures
            schedule = self._extract_schedule_from_devices(data, node_id)
            if schedule:
                _LOGGER.info("✓ Successfully extracted schedule for node %s from devices", node_id)
                return schedule
            else:
                _LOGGER.warning("_extract_schedule_from_devices returned None for node %s", node_id)
            
        except Exception as err:
            _LOGGER.error("Error fetching from /devices endpoint: %s", err)
            _LOGGER.error("Traceback: %s", traceback.format_exc())
        
        _LOGGER.error("Could not fetch schedule from any endpoint for node %s", node_id)
        return None
    
    def _extract_schedule_from_devices(self, devices_data: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        """Extract schedule for a specific node from the devices response."""
        _LOGGER.info("=== STARTING SCHEDULE EXTRACTION ===")
        _LOGGER.info("Looking for node_id: %s", node_id)
        
        try:
            # Log the FULL structure for debugging
            _LOGGER.info("=== DEVICES RESPONSE DEBUG ===")
            _LOGGER.info("Response type: %s", type(devices_data).__name__)
            
            if isinstance(devices_data, dict):
                _LOGGER.info("Response keys: %s", list(devices_data.keys()))
            else:
                _LOGGER.info("Response is not a dict, it's: %s", type(devices_data))
            
            response_str = json.dumps(devices_data, indent=2, default=str)
            _LOGGER.info("Full response length: %d chars", len(response_str))
            _LOGGER.info("Full response:\n%s", response_str)
            _LOGGER.info("=== END DEVICES RESPONSE ===")
            
            # Structure 1: Check if it's a list
            if isinstance(devices_data, list):
                _LOGGER.info("Response is a list with %d items", len(devices_data))
                for idx, device in enumerate(devices_data):
                    device_id = device.get("id") if isinstance(device, dict) else "N/A"
                    has_schedule = "schedule" in device if isinstance(device, dict) else False
                    _LOGGER.info("Item %d: id=%s, has_schedule=%s", idx, device_id, has_schedule)
                    if device_id == node_id and has_schedule:
                        _LOGGER.info("✓ Found schedule in list item %d", idx)
                        return device.get("schedule")
            
            # Structure 2: Check for 'devices' key
            if isinstance(devices_data, dict) and "devices" in devices_data:
                _LOGGER.info("Found 'devices' key in response")
                devices_list = devices_data.get("devices", [])
                _LOGGER.info("devices is a: %s with %d items", type(devices_list).__name__, len(devices_list) if isinstance(devices_list, (list, dict)) else "N/A")
                
                if isinstance(devices_list, list):
                    for idx, device in enumerate(devices_list):
                        device_id = device.get("id") if isinstance(device, dict) else "N/A"
                        _LOGGER.info("Device %d in devices list: id=%s", idx, device_id)
                        if device_id == node_id and "schedule" in device:
                            _LOGGER.info("✓ Found schedule in devices list")
                            return device.get("schedule")
            
            # Structure 3: Check for 'nodes' key
            if isinstance(devices_data, dict) and "nodes" in devices_data:
                _LOGGER.info("Found 'nodes' key in response")
                nodes_list = devices_data.get("nodes", [])
                _LOGGER.info("nodes is a: %s", type(nodes_list).__name__)
                
                if isinstance(nodes_list, list):
                    for idx, node in enumerate(nodes_list):
                        node_id_found = node.get("id") if isinstance(node, dict) else "N/A"
                        _LOGGER.info("Node %d in nodes list: id=%s", idx, node_id_found)
                        if node_id_found == node_id and "schedule" in node:
                            _LOGGER.info("✓ Found schedule in nodes list")
                            return node.get("schedule")
            
            # Structure 4: Check for 'heating' key
            if isinstance(devices_data, dict) and "heating" in devices_data:
                _LOGGER.info("Found 'heating' key in response")
                heating = devices_data.get("heating", {})
                _LOGGER.info("heating is a: %s", type(heating).__name__)
                
                if isinstance(heating, dict):
                    if "schedule" in heating:
                        _LOGGER.info("✓ Found schedule directly in heating key")
                        return heating.get("schedule")
                    if node_id in heating:
                        node = heating.get(node_id, {})
                        if "schedule" in node:
                            _LOGGER.info("✓ Found schedule in heating[%s]", node_id)
                            return node.get("schedule")
            
            _LOGGER.warning("Could not find schedule for node %s using standard structures", node_id)
            return None
            
        except Exception as err:
            _LOGGER.error("Error extracting schedule from devices: %s", err)
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return None
    
    def update_schedule(self, node_id: str, schedule_data: dict[str, Any]) -> bool:
        """Send schedule update to Hive."""
        token = self.auth.get_id_token()
        
        if not token:
            _LOGGER.error("Cannot update schedule: No auth token available")
            raise HomeAssistantError("Failed to authenticate with Hive")
        
        self.session.headers["Authorization"] = token
        url = f"{self.BASE_URL}/nodes/heating/{node_id}"
        
        try:
            _LOGGER.debug("Sending schedule update to %s", url)
            response = self.session.post(url, json=schedule_data, timeout=30)
            response.raise_for_status()
            _LOGGER.info("✓ Successfully updated Hive schedule for node %s", node_id)
            return True
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 401:
                _LOGGER.error("Authentication failed (401)")
                if self.auth.refresh_token():
                    token = self.auth.get_id_token()
                    self.session.headers["Authorization"] = token
                    try:
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
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err
        except requests.exceptions.Timeout as err:
            _LOGGER.error("Request to Hive API timed out")
            raise HomeAssistantError("Hive API request timed out") from err
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Request error updating schedule: %s", err)
            raise HomeAssistantError(f"Failed to update schedule: {err}") from err


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
        
        current_schedule = await hass.async_add_executor_job(api.get_schedule, node_id)
        
        if current_schedule is None:
            _LOGGER.error("Could not fetch current schedule - cannot safely update single day")
            raise HomeAssistantError(
                "Unable to fetch current schedule. Please use set_heating_schedule to set complete schedule."
            )
        
        schedule_data: dict[str, Any] = {"schedule": {}}
        
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d == day:
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in day_schedule
                ]
                _LOGGER.info("Updated %s: %s", d, json.dumps(schedule_data["schedule"][d], indent=2))
            else:
                if d in current_schedule:
                    schedule_data["schedule"][d] = current_schedule[d]
                    _LOGGER.info("Preserved %s: %s", d, json.dumps(current_schedule[d], indent=2, default=str))
                else:
                    _LOGGER.error("Day %s missing from fetched schedule!", d)
                    raise HomeAssistantError(f"Schedule for {d} missing in response")
        
        _LOGGER.info("Complete schedule to send: %s", json.dumps(schedule_data, indent=2, default=str))
        await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)
    
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
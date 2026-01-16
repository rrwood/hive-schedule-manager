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
                # Complete MFA authentication
                return self.verify_mfa(mfa_code)
            
            # Initial authentication attempt
            try:
                self._cognito.authenticate(password=self.password)
            except SMSMFAChallengeException as mfa_error:
                _LOGGER.debug("SMSMFAChallengeException caught during authentication")
                _LOGGER.debug("Challenge info: %s", mfa_error)
                
                # Store the MFA session for later use
                self._mfa_required = True
                self._mfa_session = self._cognito
                
                # Extract session token from the exception - it's in args[1]['Session']
                if len(mfa_error.args) > 1 and isinstance(mfa_error.args[1], dict):
                    challenge_params = mfa_error.args[1]
                    self._mfa_session_token = challenge_params.get('Session')
                    _LOGGER.debug("Extracted session token from MFA exception")
                    _LOGGER.debug("Session token (first 50 chars): %s", str(self._mfa_session_token)[:50] if self._mfa_session_token else "None")
                
                _LOGGER.info("MFA required - SMS code has been sent to your registered phone")
                return False
            except ClientError as auth_error:
                error_code = auth_error.response.get("Error", {}).get("Code", "")
                error_message = str(auth_error)
                
                _LOGGER.debug("Authentication error code: %s", error_code)
                _LOGGER.debug("Authentication error message: %s", error_message)
                
                # Check if MFA is required
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
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            error_message = str(e)
            
            _LOGGER.debug("ClientError - Code: %s, Message: %s", error_code, error_message)
            
            if error_code in ["UserMFATypeNotFound", "SMS_MFA", "SOFTWARE_TOKEN_MFA"] or "mfa" in error_message.lower():
                self._mfa_required = True
                self._mfa_session = self._cognito
                _LOGGER.info("MFA required - SMS code has been sent to your registered phone")
                return False
            
            _LOGGER.error("Failed to authenticate with Hive: %s", e)
            return False
            
        except Exception as e:
            _LOGGER.error("Failed to authenticate with Hive: %s", e)
            _LOGGER.debug("Exception type: %s", type(e).__name__)
            return False
    
    def verify_mfa(self, mfa_code: str) -> bool:
        """Verify MFA code and complete authentication."""
        try:
            if not self._mfa_session or not self._mfa_required:
                _LOGGER.error("No active MFA session - cannot verify code")
                _LOGGER.debug("_mfa_session: %s, _mfa_required: %s", self._mfa_session, self._mfa_required)
                return False
            
            _LOGGER.debug("Verifying MFA code...")
            _LOGGER.debug("MFA Session token available: %s", bool(self._mfa_session_token))
            
            # Use the stored cognito session to respond to the challenge
            try:
                # Try to answer the SMS MFA challenge
                _LOGGER.debug("Attempting to answer SMS MFA challenge...")
                
                # Method 1: Direct client call with proper parameters
                if hasattr(self._mfa_session, 'client'):
                    client = self._mfa_session.client
                    
                    _LOGGER.debug("Calling respond_to_auth_challenge with ClientId=%s, ChallengeName=SMS_MFA", COGNITO_CLIENT_ID)
                    
                    # Build challenge responses - ensure all values are strings
                    challenge_responses = {
                        "USERNAME": str(self.username),
                        "SMS_MFA_CODE": str(mfa_code)
                    }
                    
                    _LOGGER.debug("Challenge responses: USERNAME=%s, SMS_MFA_CODE=%s", self.username, mfa_code)
                    
                    response = client.respond_to_auth_challenge(
                        ClientId=COGNITO_CLIENT_ID,
                        ChallengeName="SMS_MFA",
                        Session=self._mfa_session_token,
                        ChallengeResponses=challenge_responses
                    )
                    
                    _LOGGER.debug("Auth challenge response status: %s", response.get("ResponseMetadata", {}).get("HTTPStatusCode"))
                    
                    # Extract tokens from response
                    auth_result = response.get("AuthenticationResult", {})
                    if auth_result:
                        self._mfa_session.id_token = auth_result.get("IdToken")
                        self._mfa_session.access_token = auth_result.get("AccessToken")
                        _LOGGER.debug("Successfully extracted tokens from response")
                    else:
                        _LOGGER.error("No AuthenticationResult in response")
                        _LOGGER.debug("Full response keys: %s", response.keys())
                        return False
                else:
                    _LOGGER.error("Cannot access boto3 client from cognito session")
                    return False
            
            except TypeError as type_err:
                _LOGGER.error("Type error - likely parameter validation issue: %s", type_err)
                _LOGGER.debug("Type error details: %s", str(type_err))
                return False
            except Exception as e:
                _LOGGER.error("Failed to answer MFA challenge: %s", e)
                _LOGGER.debug("Exception type: %s, Full error: %s", type(e).__name__, str(e))
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
            _LOGGER.debug("Exception type: %s", type(e).__name__)
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
        
        # Try multiple endpoint variations
        endpoints_to_try = [
            # Standard endpoint variations
            (f"{self.BASE_URL}/nodes/heating/{node_id}", "GET", None),
            (f"{self.BASE_URL}/nodes/{node_id}", "GET", None),
            (f"{self.BASE_URL}/heating/{node_id}", "GET", None),
            
            # Try POST with empty body (some APIs return data on POST)
            (f"{self.BASE_URL}/nodes/heating/{node_id}", "POST", {}),
            (f"{self.BASE_URL}/nodes/{node_id}", "POST", {}),
            (f"{self.BASE_URL}/heating/{node_id}", "POST", {}),
        ]
        
        for url, method, body in endpoints_to_try:
            try:
                _LOGGER.debug("Attempting to fetch schedule from: %s", url)
                
                if method == "GET":
                    response = self.session.get(url, timeout=30)
                else:
                    response = self.session.post(url, json=body, timeout=30)
                
                response.raise_for_status()
                
                data = response.json()
                _LOGGER.info("✓ Successfully fetched schedule from %s", url)
                _LOGGER.debug("Response keys: %s", list(data.keys()))
                _LOGGER.debug("Full response: %s", json.dumps(data, indent=2, default=str)[:1000])
                
                return data
                
            except Exception as err:
                _LOGGER.debug("Error fetching from %s: %s", url, err)
                continue
        
        _LOGGER.error("Could not fetch schedule from any endpoint")
        return None
    
    def set_schedule(self, node_id: str, schedule: dict[str, Any]) -> bool:
        """Set the heating schedule for a node."""
        token = self.auth.get_access_token()
        
        if not token:
            _LOGGER.error("Cannot set schedule: No auth token available")
            return False
        
        self.session.headers["Authorization"] = token
        
        url = f"{self.BASE_URL}/nodes/heating/{node_id}/schedule"
        
        try:
            _LOGGER.debug("Setting schedule for node %s: %s", node_id, schedule)
            response = self.session.put(url, json=schedule, timeout=30)
            response.raise_for_status()
            
            _LOGGER.info("✓ Successfully set schedule for node %s", node_id)
            return True
        
        except Exception as e:
            _LOGGER.error("Failed to set schedule for node %s: %s", node_id, e)
            return False
    
    def set_day_schedule(self, node_id: str, day: str, schedule: list[dict[str, Any]]) -> bool:
        """Set the heating schedule for a specific day."""
        token = self.auth.get_access_token()
        
        if not token:
            _LOGGER.error("Cannot set day schedule: No auth token available")
            return False
        
        self.session.headers["Authorization"] = token
        
        url = f"{self.BASE_URL}/nodes/heating/{node_id}/schedule/{day}"
        
        try:
            _LOGGER.debug("Setting day schedule for node %s, day %s: %s", node_id, day, schedule)
            response = self.session.put(url, json=schedule, timeout=30)
            response.raise_for_status()
            
            _LOGGER.info("✓ Successfully set day schedule for node %s, day %s", node_id, day)
            return True
        
        except Exception as e:
            _LOGGER.error("Failed to set day schedule for node %s, day %s: %s", node_id, day, e)
            return False
    
    def update_from_calendar(self, node_id: str, is_workday: bool, wake_time: str | None) -> bool:
        """Update the schedule based on calendar event (workday or not)."""
        token = self.auth.get_access_token()
        
        if not token:
            _LOGGER.error("Cannot update from calendar: No auth token available")
            return False
        
        self.session.headers["Authorization"] = token
        
        url = f"{self.BASE_URL}/nodes/heating/{node_id}/calendar"
        
        payload = {
            "is_workday": is_workday,
            "wake_time": wake_time
        }
        
        try:
            _LOGGER.debug("Updating from calendar for node %s: %s", node_id, payload)
            response = self.session.put(url, json=payload, timeout=30)
            response.raise_for_status()
            
            _LOGGER.info("✓ Successfully updated from calendar for node %s", node_id)
            return True
        
        except Exception as e:
            _LOGGER.error("Failed to update from calendar for node %s: %s", node_id, e)
            return False
    
    def get_all_devices(self) -> dict[str, Any] | None:
        """Fetch all devices/nodes to get complete state including schedules."""
        token = self.auth.get_id_token()
        
        if not token:
            _LOGGER.error("Cannot get devices: No auth token available")
            return None
        
        self.session.headers["Authorization"] = token
        
        endpoints_to_try = [
            f"{self.BASE_URL}/nodes",
            f"{self.BASE_URL}/devices",
            f"{self.BASE_URL}/home",
            f"{self.BASE_URL}/user/devices",
        ]
        
        for url in endpoints_to_try:
            try:
                _LOGGER.debug("Attempting to fetch devices from: %s", url)
                response = self.session.get(url, timeout=30)
                
                if response.status_code in [403, 404]:
                    _LOGGER.debug("Status %s for %s - trying next", response.status_code, url)
                    continue
                
                response.raise_for_status()
                
                data = response.json()
                _LOGGER.info("✓ Successfully fetched devices from %s", url)
                _LOGGER.debug("Response keys: %s", list(data.keys()))
                _LOGGER.debug("Full response: %s", json.dumps(data, indent=2, default=str)[:1000])
                
                return data
                    
            except Exception as err:
                _LOGGER.debug("Error fetching from %s: %s", url, err)
                continue
        
        _LOGGER.error("Could not fetch devices from any endpoint")
        return None


async def handle_set_day(hass: HomeAssistant, api: HiveScheduleAPI, call: ServiceCall) -> None:
        """Handle set_day_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        day_schedule = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info("Setting schedule for %s on node %s", day, node_id)
        _LOGGER.debug("New schedule for %s: %s", day, day_schedule)
        
        # Try to fetch current schedule
        current_schedule = await hass.async_add_executor_job(api.get_schedule, node_id)
        
        if current_schedule is None:
            _LOGGER.warning("Could not fetch schedule directly, trying to get all devices")
            # Try to fetch all devices to find this node's schedule
            all_devices = await hass.async_add_executor_job(api.get_all_devices)
            if all_devices:
                _LOGGER.debug("Got devices response, looking for node %s", node_id)
                # You'll need to parse this based on actual API response structure
                _LOGGER.debug("Full devices response: %s", json.dumps(all_devices, indent=2, default=str)[:2000])
            
            _LOGGER.error("Could not fetch current schedule - cannot safely update single day")
            raise HomeAssistantError(
                "Unable to fetch current schedule. Please use set_heating_schedule to set complete schedule."
            )
        
        schedule_data: dict[str, Any] = {"schedule": {}}
        
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d == day:
                # Update the specified day with new schedule
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry["time"], entry["temp"])
                    for entry in day_schedule
                ]
                _LOGGER.info("Updated %s: %s", d, json.dumps(schedule_data["schedule"][d], indent=2))
            else:
                # Preserve existing schedule for other days
                if d in current_schedule:
                    schedule_data["schedule"][d] = current_schedule[d]
                    _LOGGER.info("Preserved %s: %s", d, json.dumps(current_schedule[d], indent=2, default=str))
                else:
                    _LOGGER.error("Day %s missing from fetched schedule!", d)
                    raise HomeAssistantError(f"Schedule for {d} missing in response")
        
        _LOGGER.info("Complete schedule to send: %s", json.dumps(schedule_data, indent=2, default=str))
        await hass.async_add_executor_job(api.update_schedule, node_id, schedule_data)

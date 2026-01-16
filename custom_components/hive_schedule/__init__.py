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
        
        # Try /nodes endpoint to list all nodes
        _LOGGER.info("Direct endpoints failed, attempting to fetch from /nodes endpoint")
        try:
            nodes_url = f"{self.BASE_URL}/nodes"
            _LOGGER.info("Fetching all nodes from: %s", nodes_url)
            response = self.session.get(nodes_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            _LOGGER.info("Successfully received nodes response")
            
            # Write to file for inspection
            try:
                import os
                config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                debug_file = os.path.join(config_dir, "hive_nodes_debug.json")
                
                with open(debug_file, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                
                _LOGGER.info("✓ Wrote nodes response to: %s", debug_file)
            except Exception as e:
                _LOGGER.error("Could not write nodes debug file: %s", e)
            
            schedule = self._extract_schedule_from_devices(data, node_id)
            if schedule:
                _LOGGER.info("✓ Successfully extracted schedule for node %s from nodes endpoint", node_id)
                return schedule
            
        except Exception as err:
            _LOGGER.debug("Error fetching from /nodes endpoint: %s", err)
        
        # Last resort: fetch all devices
        _LOGGER.info("Nodes endpoint failed, attempting to fetch from /devices endpoint")
        try:
            devices_url = f"{self.BASE_URL}/devices"
            _LOGGER.info("Fetching devices from: %s", devices_url)
            response = self.session.get(devices_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            _LOGGER.info("Successfully received devices response")
            
            schedule = self._extract_schedule_from_devices(data, node_id)
            if schedule:
                _LOGGER.info("✓ Successfully extracted schedule for node %s from devices", node_id)
                return schedule
            
        except Exception as err:
            _LOGGER.error("Error fetching from /devices endpoint: %s", err)
        
        _LOGGER.error("Could not fetch schedule from any endpoint for node %s", node_id)
        return None
    
    def _extract_schedule_from_devices(self, devices_data: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        """Extract schedule for a specific node from the devices response."""
        _LOGGER.info("=== STARTING SCHEDULE EXTRACTION ===")
        _LOGGER.info("Looking for node_id: %s", node_id)
        
        try:
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
                
                # Write ENTIRE response to file for inspection
                try:
                    import os
                    config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    debug_file = os.path.join(config_dir, "hive_all_devices_debug.json")
                    
                    with open(debug_file, 'w') as f:
                        json.dump(devices_data, f, indent=2, default=str)
                    
                    _LOGGER.info("✓ Wrote ALL devices to: %s", debug_file)
                except Exception as e:
                    _LOGGER.error("Could not write all devices debug file: %s", e)
                
                # Now search recursively in all devices for the target node_id
                _LOGGER.info("Searching recursively for node_id: %s", node_id)
                for idx, device in enumerate(devices_data):
                    device_id = device.get("id") if isinstance(device, dict) else "N/A"
                    device_type = device.get("type") if isinstance(device, dict) else "N/A"
                    _LOGGER.debug("Searching in device %d (id=%s, type=%s)", idx, device_id, device_type)
                    
                    # Search this device for the node_id
                    schedule = self._find_schedule_in_object(device, node_id)
                    if schedule:
                        _LOGGER.info("✓ Found schedule for node_id %s in device %d", node_id, idx)
                        return schedule
                
                _LOGGER.warning("Could not find node_id %s in any device", node_id)
                _LOGGER.info("Target node_id: %s", node_id)
                _LOGGER.info("Available top-level IDs: %s", top_level_ids)
                return None
            
            # Structure 2: Check if it's a dict (keyed by ID)
            elif isinstance(devices_data, dict):
                _LOGGER.info("Response is a dict with %d keys", len(devices_data))
                all_keys = list(devices_data.keys())
                _LOGGER.info("Dict keys: %s", all_keys)
                
                # Write entire dict to file
                try:
                    import os
                    config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    debug_file = os.path.join(config_dir, "hive_all_devices_debug.json")
                    
                    with open(debug_file, 'w') as f:
                        json.dump(devices_data, f, indent=2, default=str)
                    
                    _LOGGER.info("✓ Wrote dict response to: %s", debug_file)
                except Exception as e:
                    _LOGGER.error("Could not write debug file: %s", e)
                
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
                
                return None
        
        except Exception as e:
            _LOGGER.error("Error extracting schedule from devices: %s", e)
            return None
           
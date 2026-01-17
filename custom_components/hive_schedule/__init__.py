"""
Hive Schedule Manager Integration for Home Assistant
Standalone with config flow and MFA support.
Version: 1.2.0 (Enhanced Debug + AWS SigV4 GET Support)
"""
from __future__ import annotations

import logging
import json
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
import requests
from pycognito import Cognito
from jose import jwt

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

# Service schemas
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

GET_SCHEDULE_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
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
        
        # AWS credentials from tokens
        self._aws_access_key = None
        self._aws_secret_key = None
        self._aws_session_token = None
        self._extract_aws_credentials()
    
    def _extract_aws_credentials(self) -> None:
        """Extract AWS credentials from Cognito tokens."""
        try:
            if self._id_token:
                # Decode the ID token (don't verify signature, just extract claims)
                decoded = jwt.get_unverified_claims(self._id_token)
                _LOGGER.debug("ID Token claims: %s", list(decoded.keys()))
                
                # Try to find AWS credentials in the token
                # Cognito tokens may contain identityId which we can use
                if 'cognito:username' in decoded:
                    _LOGGER.debug("Found Cognito username in token")
                
                # Check if we have AWS credentials in access token
                if self._access_token:
                    access_decoded = jwt.get_unverified_claims(self._access_token)
                    _LOGGER.debug("Access Token claims: %s", list(access_decoded.keys()))
                    
                    # Look for AWS credentials
                    for key in ['aws_access_key', 'AccessKeyId', 'access_key']:
                        if key in access_decoded:
                            self._aws_access_key = access_decoded[key]
                            _LOGGER.info("Found AWS access key in token")
                    
                    for key in ['aws_secret_key', 'SecretAccessKey', 'secret_key']:
                        if key in access_decoded:
                            self._aws_secret_key = access_decoded[key]
                            _LOGGER.info("Found AWS secret key in token")
                    
                    for key in ['aws_session_token', 'SessionToken', 'session_token']:
                        if key in access_decoded:
                            self._aws_session_token = access_decoded[key]
                            _LOGGER.info("Found AWS session token")
        
        except Exception as e:
            _LOGGER.debug("Could not extract AWS credentials from tokens: %s", e)
    
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
            
            # Try to extract AWS credentials from new tokens
            self._extract_aws_credentials()
            
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
    
    def has_aws_credentials(self) -> bool:
        """Check if we have AWS credentials."""
        return bool(self._aws_access_key and self._aws_secret_key)


class AWSV4Signer:
    """AWS Signature Version 4 request signer."""
    
    def __init__(self, access_key: str, secret_key: str, session_token: str | None, region: str, service: str):
        """Initialize the signer."""
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.region = region
        self.service = service
    
    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        """HMAC-SHA256 signing."""
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
    
    def _get_signature_key(self, date_stamp: str) -> bytes:
        """Derive the signing key."""
        k_date = self._sign(f"AWS4{self.secret_key}".encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, 'aws4_request')
        return k_signing
    
    def sign_request(self, method: str, url: str, headers: dict, payload: str = '') -> dict:
        """Sign an HTTP request with AWS Signature Version 4."""
        # Parse URL
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = parsed.path if parsed.path else '/'
        canonical_querystring = parsed.query if parsed.query else ''
        
        # Create timestamp
        t = datetime.utcnow()
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = t.strftime('%Y%m%d')
        
        # Build canonical headers
        headers_to_sign = {'host': host, 'x-amz-date': amz_date}
        
        # Add session token if available
        if self.session_token:
            headers_to_sign['x-amz-security-token'] = self.session_token
        
        # Add content-type if present
        if 'Content-Type' in headers:
            headers_to_sign['content-type'] = headers['Content-Type']
        
        # Sort and format headers
        sorted_headers = sorted(headers_to_sign.items())
        canonical_headers = ''.join([f"{k}:{v}\n" for k, v in sorted_headers])
        signed_headers = ';'.join([k for k, v in sorted_headers])
        
        # Create payload hash
        payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        
        # Create canonical request
        canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        
        # Create string to sign
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        canonical_request_hash = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{canonical_request_hash}"
        
        # Calculate signature
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # Create authorization header
        authorization_header = (
            f"{algorithm} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        
        # Build final headers
        signed_request_headers = dict(headers_to_sign)
        signed_request_headers['Authorization'] = authorization_header
        
        # Add other original headers that weren't signed
        for key, value in headers.items():
            if key.lower() not in [h.lower() for h in headers_to_sign.keys()] and key != 'Authorization':
                signed_request_headers[key] = value
        
        return signed_request_headers


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
            auth_header = safe_headers["Authorization"]
            if len(auth_header) > 50:
                safe_headers["Authorization"] = f"{auth_header[:30]}...{auth_header[-20:]}"
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
    
    def get_schedule(self, node_id: str) -> dict[str, Any]:
        """Retrieve the current schedule from Hive using GET request."""
        _LOGGER.info("Retrieving current schedule from Hive for node %s", node_id)
        
        url = f"{self.BASE_URL}/nodes/heating/{node_id}"
        
        # Try with AWS SigV4 first if we have credentials
        if self.auth.has_aws_credentials():
            _LOGGER.info("Using AWS Signature V4 for GET request")
            try:
                return self._get_with_sigv4(url, node_id)
            except Exception as e:
                _LOGGER.warning("AWS SigV4 failed: %s, trying bearer token", e)
        
        # Fallback to bearer token
        _LOGGER.info("Using bearer token for GET request")
        return self._get_with_bearer(url, node_id)
    
    def _get_with_sigv4(self, url: str, node_id: str) -> dict[str, Any]:
        """GET request with AWS Signature V4."""
        # Create signer
        signer = AWSV4Signer(
            access_key=self.auth._aws_access_key,
            secret_key=self.auth._aws_secret_key,
            session_token=self.auth._aws_session_token,
            region='eu-west-1',  # Hive uses eu-west-1
            service='execute-api'  # API Gateway service
        )
        
        # Sign the request
        headers = self.session.headers.copy()
        signed_headers = signer.sign_request('GET', url, headers, '')
        
        self._log_api_call("GET", url, signed_headers)
        
        response = self.session.get(url, headers=signed_headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        _LOGGER.info("✓ Successfully retrieved schedule using AWS SigV4")
        self._format_schedule_readable(data, "CURRENT SCHEDULE FROM HIVE (via AWS SigV4)")
        
        return data
    
    def _get_with_bearer(self, url: str, node_id: str) -> dict[str, Any]:
        """GET request with bearer token."""
        token = self.auth.get_id_token()
        
        if not token:
            raise HomeAssistantError("No auth token available")
        
        headers = self.session.headers.copy()
        headers["Authorization"] = token
        
        self._log_api_call("GET", url, headers)
        
        response = self.session.get(url, headers=headers, timeout=30)
        
        if response.status_code == 403:
            _LOGGER.error("GET request forbidden - AWS credentials may be required")
            _LOGGER.error("Response: %s", response.text[:500])
            raise HomeAssistantError(
                "GET requests require AWS Signature V4. "
                "Could not extract AWS credentials from Cognito tokens. "
                "This is a limitation of the Hive API."
            )
        
        response.raise_for_status()
        
        data = response.json()
        _LOGGER.info("✓ Successfully retrieved schedule using bearer token")
        self._format_schedule_readable(data, "CURRENT SCHEDULE FROM HIVE")
        
        return data
    
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
    
    _LOGGER.info("Setting up Hive Schedule Manager v1.2.0 (AWS SigV4 + GET Support)")
    
    # Initialize authentication and API
    auth = HiveAuth(hass, entry)
    api = HiveScheduleAPI(auth)
    
    # Check if we have tokens
    if not auth._id_token:
        _LOGGER.warning("No authentication tokens found in config entry")
    else:
        _LOGGER.info("Loaded authentication tokens from config entry")
        if auth.has_aws_credentials():
            _LOGGER.info("✓ AWS credentials extracted from tokens - GET requests should work!")
        else:
            _LOGGER.warning("⚠ Could not extract AWS credentials - GET requests may fail")
            _LOGGER.info("GET requests will attempt bearer token fallback")
        
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
    
    # Service: Get schedule
    async def handle_get_schedule(call: ServiceCall) -> None:
        """Handle get_schedule service call - retrieves current schedule from Hive."""
        node_id = call.data[ATTR_NODE_ID]
        
        _LOGGER.info("Getting current schedule from Hive for node %s", node_id)
        
        try:
            schedule_data = await hass.async_add_executor_job(
                api.get_schedule, node_id
            )
            
            if schedule_data:
                _LOGGER.info("Successfully retrieved current schedule from Hive")
                # Fire event with the schedule data
                hass.bus.async_fire(
                    f"{DOMAIN}_schedule_retrieved",
                    {
                        "node_id": node_id,
                        "schedule": schedule_data.get("schedule"),
                    }
                )
        except Exception as err:
            _LOGGER.error("Failed to get schedule: %s", err)
            raise
    
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
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DAY,
        handle_set_day,
        schema=SET_DAY_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN,
        "get_schedule",
        handle_get_schedule,
        schema=GET_SCHEDULE_SCHEMA
    )
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    _LOGGER.info("Available services: set_day_schedule, get_schedule")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id)
    
    # Unregister services if this is the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_DAY)
        hass.services.async_remove(DOMAIN, "get_schedule")
    
    return True
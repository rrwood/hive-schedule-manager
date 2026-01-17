"""
Hive Schedule Manager Integration for Home Assistant
Manages Hive heating schedules with profile support and config flow.
Version: 1.1.0
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
import requests
from pycognito import Cognito
from botocore.exceptions import ClientError
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import boto3

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
    CONF_ID_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
)
from .schedule_profiles import get_profile, get_available_profiles, validate_custom_schedule

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

# Cognito Identity Pool ID for Hive (if we need AWS credentials)
COGNITO_IDENTITY_POOL_ID = "eu-west-1:d235e7e0-bb62-4f74-980a-98e89519cba8"

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
        
        # Load tokens from config entry if available
        self._id_token = entry.data.get(CONF_ID_TOKEN)
        self._access_token = entry.data.get(CONF_ACCESS_TOKEN)
        self._refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
        
        # AWS credentials for API signing
        self._aws_access_key = None
        self._aws_secret_key = None
        self._aws_session_token = None
        self._aws_credentials_expiry = None
        
        # Parse token expiry
        expiry_str = entry.data.get(CONF_TOKEN_EXPIRY)
        if expiry_str:
            try:
                self._token_expiry = datetime.fromisoformat(expiry_str)
            except (ValueError, TypeError):
                self._token_expiry = None
        else:
            self._token_expiry = None
    
    def get_aws_credentials(self) -> dict[str, str]:
        """Get AWS credentials from Cognito Identity Pool."""
        try:
            # Check if we need to refresh AWS credentials
            if (self._aws_credentials_expiry and 
                datetime.now() < self._aws_credentials_expiry - timedelta(minutes=5) and
                self._aws_access_key):
                _LOGGER.debug("AWS credentials still valid")
                return {
                    'access_key': self._aws_access_key,
                    'secret_key': self._aws_secret_key,
                    'session_token': self._aws_session_token,
                }
            
            _LOGGER.info("Getting AWS credentials from Cognito Identity Pool...")
            
            # Create Cognito Identity client
            identity_client = boto3.client(
                'cognito-identity',
                region_name=COGNITO_REGION
            )
            
            # Get Identity ID
            identity_response = identity_client.get_id(
                IdentityPoolId=COGNITO_IDENTITY_POOL_ID,
                Logins={
                    f'cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_POOL_ID}': self._id_token
                }
            )
            
            identity_id = identity_response['IdentityId']
            _LOGGER.debug("Got Identity ID: %s", identity_id[:20] + "...")
            
            # Get credentials for the identity
            credentials_response = identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins={
                    f'cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_POOL_ID}': self._id_token
                }
            )
            
            credentials = credentials_response['Credentials']
            self._aws_access_key = credentials['AccessKeyId']
            self._aws_secret_key = credentials['SecretKey']
            self._aws_session_token = credentials['SessionToken']
            self._aws_credentials_expiry = credentials['Expiration'].replace(tzinfo=None)
            
            _LOGGER.info("Successfully obtained AWS credentials")
            
            return {
                'access_key': self._aws_access_key,
                'secret_key': self._aws_secret_key,
                'session_token': self._aws_session_token,
            }
            
        except Exception as e:
            _LOGGER.error("Failed to get AWS credentials: %s", e)
            raise HomeAssistantError(f"Failed to get AWS credentials: {e}")
    
    def refresh_token(self) -> bool:
        """Refresh the authentication token using refresh token."""
        try:
            # Check if we need to refresh
            if self._token_expiry and datetime.now() < self._token_expiry - timedelta(minutes=5):
                _LOGGER.debug("Token still valid, no refresh needed")
                return True
            
            if not self._refresh_token:
                _LOGGER.warning("No refresh token available, cannot refresh")
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
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            _LOGGER.error("Failed to refresh token: %s - %s", error_code, str(e))
            
            # If refresh token is invalid, user needs to re-authenticate
            if "NotAuthorizedException" in error_code:
                _LOGGER.error("Refresh token invalid - please reconfigure integration")
                raise ConfigEntryAuthFailed("Refresh token expired - please reconfigure")
            
            return False
            
        except Exception as e:
            _LOGGER.error("Error refreshing token: %s", e)
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
    
    def get_token(self) -> str | None:
        """Get the current ID token."""
        if not self._id_token:
            _LOGGER.error("No ID token available - integration may need reconfiguration")
            return None
        
        # Refresh if needed
        if not self.refresh_token():
            _LOGGER.warning("Token refresh failed")
        
        return self._id_token


class HiveScheduleAPI:
    """API client for Hive schedule management."""
    
    def __init__(self, auth: HiveAuth) -> None:
        """Initialize the API client."""
        self.auth = auth
        self.base_url = HIVE_API_URL
    
    def _sign_request(self, method: str, url: str, body: str = None) -> dict[str, str]:
        """Sign request with AWS Signature v4."""
        try:
            # Get AWS credentials
            aws_creds = self.auth.get_aws_credentials()
            
            # Parse URL
            parsed_url = urlparse(url)
            
            # Create AWS request
            request = AWSRequest(
                method=method,
                url=url,
                data=body,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                }
            )
            
            # Create credentials object for signing
            from botocore.credentials import Credentials
            credentials = Credentials(
                access_key=aws_creds['access_key'],
                secret_key=aws_creds['secret_key'],
                token=aws_creds['session_token']
            )
            
            # Sign the request
            SigV4Auth(credentials, 'execute-api', COGNITO_REGION).add_auth(request)
            
            _LOGGER.debug("Request signed with AWS Signature v4")
            
            return dict(request.headers)
            
        except Exception as e:
            _LOGGER.error("Failed to sign request: %s", e)
            raise HomeAssistantError(f"Failed to sign request: {e}")
    
    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests - deprecated, use _sign_request."""
        token = self.auth.get_token()
        if not token:
            raise HomeAssistantError(
                "No valid authentication token available. "
                "Please reconfigure the Hive Schedule Manager integration."
            )
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": token,  # Capital A - Hive API might be case-sensitive
        }
        
        _LOGGER.debug("Request headers: %s", {k: v[:20] + "..." if k == "authorization" else v for k, v in headers.items()})
        
        return headers
    
    def get_current_schedule(self, node_id: str) -> dict[str, Any]:
        """Retrieve the current schedule for a node."""
        try:
            url = f"{self.base_url}/nodes/{node_id}"
            headers = self._get_headers()
            
            _LOGGER.debug("Getting current schedule from %s", url)
            
            response = requests.get(url, headers=headers, timeout=30)
            
            # Log response details before raising for status
            _LOGGER.debug("Response status: %d", response.status_code)
            if response.status_code != 200:
                _LOGGER.error("Response body: %s", response.text[:500])
            
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
            if hasattr(err, 'response') and err.response is not None:
                _LOGGER.error("Response status: %d", err.response.status_code)
                _LOGGER.error("Response headers: %s", dict(err.response.headers))
                _LOGGER.error("Response body: %s", err.response.text[:500])
            raise HomeAssistantError(f"Failed to get schedule: {err}") from err
        except requests.exceptions.Timeout:
            _LOGGER.error("Request timeout getting schedule")
            raise HomeAssistantError("Hive API request timed out")
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Request error getting schedule: %s", err)
            raise HomeAssistantError(f"Failed to get schedule: {err}") from err
    
    def build_schedule_entry(self, time: str, temp: float) -> dict[str, Any]:
        """Build a single schedule entry in Hive format."""
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
        """Update the heating schedule for a node."""
        try:
            url = f"{self.base_url}/nodes/{node_id}"
            
            payload = {
                "nodes": [{
                    "attributes": schedule_data
                }]
            }
            
            body = json.dumps(payload)
            
            _LOGGER.debug("Updating schedule at %s", url)
            _LOGGER.debug("Payload: %s", payload)
            
            # Sign the request with AWS Signature v4
            headers = self._sign_request('PUT', url, body)
            
            response = requests.put(url, headers=headers, data=body, timeout=30)
            
            # Log response details before raising for status
            _LOGGER.debug("Response status: %d", response.status_code)
            if response.status_code != 200:
                _LOGGER.error("Response body: %s", response.text[:500])
            
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
    
    # Initialize authentication and API
    auth = HiveAuth(hass, entry)
    api = HiveScheduleAPI(auth)
    
    # Check if we have tokens
    if not auth._id_token:
        _LOGGER.warning(
            "No authentication tokens found in config entry. "
            "Integration may not work until reconfigured with MFA."
        )
    else:
        _LOGGER.info("Loaded authentication tokens from config entry")
        # Try to refresh token to ensure it's valid
        def check_token():
            return auth.refresh_token()
        
        try:
            await hass.async_add_executor_job(check_token)
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
        try:
            await hass.async_add_executor_job(auth.refresh_token)
        except ConfigEntryAuthFailed:
            _LOGGER.error("Token refresh failed - reconfiguration required")
    
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
        
        # Build schedule with ONLY the selected day
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
    
    # Manual refresh service
    async def handle_refresh_token(call: ServiceCall) -> None:
        """Manually refresh the Hive authentication token."""
        _LOGGER.info("Manual token refresh requested")
        try:
            success = await hass.async_add_executor_job(auth.refresh_token)
            if success:
                _LOGGER.info("Token refresh successful")
            else:
                _LOGGER.error("Token refresh failed")
        except ConfigEntryAuthFailed:
            _LOGGER.error("Token refresh failed - reconfiguration required")
    
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
"""Config flow for Hive Schedule Manager integration."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timedelta

import voluptuous as vol
from pycognito import Cognito
from pycognito.exceptions import SMSMFAChallengeException
from botocore.exceptions import ClientError

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    COGNITO_POOL_ID,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    CONF_MFA_CODE,
    CONF_ID_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
)

_LOGGER = logging.getLogger(__name__)


class HiveScheduleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hive Schedule Manager."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._username = None
        self._password = None
        self._session_token = None
        self._cognito = None
        self._auth_result = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - username and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            try:
                # Try to authenticate
                result = await self.hass.async_add_executor_job(
                    self._try_authenticate
                )
                
                if result.get("mfa_required"):
                    # MFA needed, go to MFA step
                    _LOGGER.info("MFA required, proceeding to MFA step")
                    return await self.async_step_mfa()
                elif result.get("success"):
                    # Success without MFA
                    _LOGGER.info("Authentication successful without MFA")
                    return await self._create_or_update_entry()
                else:
                    errors["base"] = "invalid_auth"

            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception as ex:
                _LOGGER.exception("Unexpected exception in user step: %s", ex)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle MFA code entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mfa_code = user_input[CONF_MFA_CODE]

            try:
                # Verify MFA code
                result = await self.hass.async_add_executor_job(
                    self._verify_mfa, mfa_code
                )
                
                if result.get("success"):
                    # MFA verified successfully
                    _LOGGER.info("MFA verified, storing tokens and creating entry")
                    self._auth_result = result.get("auth_result")
                    return await self._create_or_update_entry()
                else:
                    _LOGGER.warning("MFA verification failed")
                    errors["base"] = "invalid_mfa"

            except Exception as ex:
                _LOGGER.exception("Exception during MFA verification: %s", ex)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({
                vol.Required(CONF_MFA_CODE): str,
            }),
            errors=errors,
            description_placeholders={
                "username": self._username,
            },
        )

    async def _create_or_update_entry(self) -> FlowResult:
        """Create a new entry or update existing one."""
        # Prepare data to store
        entry_data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
        }
        
        # Add tokens if we have them from MFA
        if self._auth_result:
            entry_data[CONF_ID_TOKEN] = self._auth_result.get('IdToken', '')
            entry_data[CONF_ACCESS_TOKEN] = self._auth_result.get('AccessToken', '')
            entry_data[CONF_REFRESH_TOKEN] = self._auth_result.get('RefreshToken', '')
            # Token expires in ~1 hour, store expiry time
            expiry = (datetime.now() + timedelta(minutes=55)).isoformat()
            entry_data[CONF_TOKEN_EXPIRY] = expiry
            _LOGGER.debug("Stored authentication tokens in config entry")
        
        # Check if entry already exists
        existing_entry = await self.async_set_unique_id(self._username.lower())
        
        if existing_entry:
            # Update existing entry
            _LOGGER.info("Updating existing config entry for %s", self._username)
            self.hass.config_entries.async_update_entry(
                existing_entry,
                data=entry_data
            )
            # Reload the entry to use new credentials
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
        
        # Create new entry
        _LOGGER.info("Creating new config entry for %s", self._username)
        return self.async_create_entry(
            title=self._username,
            data=entry_data
        )

    def _try_authenticate(self) -> dict[str, Any]:
        """Try to authenticate - returns status dict."""
        try:
            self._cognito = Cognito(
                user_pool_id=COGNITO_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=self._username
            )
            
            try:
                self._cognito.authenticate(password=self._password)
                # Success without MFA - store tokens
                _LOGGER.info("Authentication successful without MFA")
                self._auth_result = {
                    'IdToken': self._cognito.id_token,
                    'AccessToken': self._cognito.access_token,
                    'RefreshToken': self._cognito.refresh_token,
                }
                return {"success": True}
                
            except SMSMFAChallengeException as mfa_error:
                _LOGGER.info("MFA required - SMS code sent to registered phone")
                # Extract session token from the exception
                if len(mfa_error.args) > 1 and isinstance(mfa_error.args[1], dict):
                    self._session_token = mfa_error.args[1].get('Session')
                    _LOGGER.debug("MFA session token extracted")
                return {"mfa_required": True}
                
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            error_message = str(err)
            
            _LOGGER.error("Auth error: %s - %s", error_code, error_message)
            
            if "NotAuthorizedException" in error_code or "not authorized" in error_message.lower():
                raise InvalidAuth
            elif "UserNotFoundException" in error_code:
                raise InvalidAuth
            else:
                raise CannotConnect
                
        except Exception as err:
            _LOGGER.exception("Unexpected exception during auth: %s", err)
            raise CannotConnect

    def _verify_mfa(self, mfa_code: str) -> dict[str, Any]:
        """Verify MFA code - returns status dict with tokens."""
        try:
            if not self._cognito or not self._session_token:
                _LOGGER.error("No MFA session available for verification")
                return {"success": False}
            
            _LOGGER.debug("Verifying MFA code...")
            
            # Use boto3 client directly to respond to MFA challenge
            client = self._cognito.client
            response = client.respond_to_auth_challenge(
                ClientId=COGNITO_CLIENT_ID,
                ChallengeName='SMS_MFA',
                Session=self._session_token,
                ChallengeResponses={
                    'SMS_MFA_CODE': mfa_code,
                    'USERNAME': self._username,
                }
            )
            
            # Check if we got authentication result
            if 'AuthenticationResult' in response:
                _LOGGER.info("MFA verification successful - tokens received")
                return {
                    "success": True,
                    "auth_result": response['AuthenticationResult']
                }
            else:
                _LOGGER.warning("MFA response did not contain authentication result")
                return {"success": False}
                
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            error_msg = err.response.get("Error", {}).get("Message", "")
            _LOGGER.error("MFA verification error: %s - %s", error_code, error_msg)
            
            if "CodeMismatchException" in error_code:
                _LOGGER.warning("Invalid MFA code provided")
            
            return {"success": False}
            
        except Exception as err:
            _LOGGER.exception("Unexpected error during MFA verification: %s", err)
            return {"success": False}


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
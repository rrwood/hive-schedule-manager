"""Config flow for Hive Schedule Manager integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pycognito import Cognito
from pycognito.exceptions import SMSMFAChallengeException
from botocore.exceptions import ClientError

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    COGNITO_POOL_ID,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    CONF_MFA_CODE,
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
        self._mfa_verified = False

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
                    await self.async_set_unique_id(self._username)
                    self._abort_if_unique_id_configured()
                    
                    return self.async_create_entry(
                        title=self._username,
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                        }
                    )
                else:
                    errors["base"] = "invalid_auth"

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
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
                    # MFA verified successfully - we can now create the entry
                    _LOGGER.info("MFA verification successful, creating config entry")
                    self._mfa_verified = True
                    
                    await self.async_set_unique_id(self._username)
                    self._abort_if_unique_id_configured()
                    
                    # Create entry with just credentials - tokens will be obtained on first use
                    return self.async_create_entry(
                        title=self._username,
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                        }
                    )
                else:
                    _LOGGER.warning("MFA verification failed")
                    errors["base"] = "invalid_mfa"

            except Exception:
                _LOGGER.exception("Unexpected exception during MFA verification")
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
                # Success without MFA
                _LOGGER.info("Authentication successful without MFA")
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
            _LOGGER.exception("Unexpected exception during auth")
            raise CannotConnect

    def _verify_mfa(self, mfa_code: str) -> dict[str, Any]:
        """Verify MFA code - returns status dict."""
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
                # Don't store tokens here - they'll be fresh when integration starts
                # Just confirm MFA worked
                return {"success": True}
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
            _LOGGER.exception("Unexpected error during MFA verification")
            return {"success": False}


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
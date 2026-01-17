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
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    COGNITO_POOL_ID,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    CONF_MFA_CODE,
)

_LOGGER = logging.getLogger(__name__)


async def validate_auth(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user credentials and handle MFA if needed."""
    
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    mfa_code = data.get(CONF_MFA_CODE)
    
    def _authenticate():
        """Perform authentication in executor."""
        try:
            cognito = Cognito(
                user_pool_id=COGNITO_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=username
            )
            
            if mfa_code:
                # Complete MFA challenge
                _LOGGER.debug("Attempting MFA verification")
                cognito.authenticate(password=password)
                # This shouldn't happen if MFA is required, but handle it
                return {
                    "title": username,
                    "id_token": cognito.id_token,
                    "access_token": cognito.access_token,
                }
            else:
                # Initial authentication
                try:
                    cognito.authenticate(password=password)
                    return {
                        "title": username,
                        "id_token": cognito.id_token,
                        "access_token": cognito.access_token,
                    }
                except SMSMFAChallengeException as mfa_error:
                    _LOGGER.debug("MFA required - SMS sent")
                    # Extract session info
                    session_token = None
                    if len(mfa_error.args) > 1 and isinstance(mfa_error.args[1], dict):
                        session_token = mfa_error.args[1].get('Session')
                    
                    return {
                        "mfa_required": True,
                        "session_token": session_token,
                    }
                    
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            error_message = str(err)
            
            if "NotAuthorizedException" in error_code or "not authorized" in error_message.lower():
                raise InvalidAuth
            elif "UserNotFoundException" in error_code:
                raise InvalidAuth
            else:
                _LOGGER.error("Cognito error: %s - %s", error_code, error_message)
                raise CannotConnect
                
        except Exception as err:
            _LOGGER.exception("Unexpected exception during auth")
            raise CannotConnect
    
    return await hass.async_add_executor_job(_authenticate)


class HiveScheduleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hive Schedule Manager."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._username = None
        self._password = None
        self._session_token = None
        self._mfa_required = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - username and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            try:
                info = await validate_auth(
                    self.hass,
                    {
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                    }
                )
                
                if info.get("mfa_required"):
                    # Store session info and proceed to MFA step
                    self._mfa_required = True
                    self._session_token = info.get("session_token")
                    return await self.async_step_mfa()
                else:
                    # Success - no MFA needed
                    await self.async_set_unique_id(self._username)
                    self._abort_if_unique_id_configured()
                    
                    return self.async_create_entry(
                        title=info["title"],
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                        }
                    )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
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
                def _verify_mfa():
                    try:
                        cognito = Cognito(
                            user_pool_id=COGNITO_POOL_ID,
                            client_id=COGNITO_CLIENT_ID,
                            user_pool_region=COGNITO_REGION,
                            username=self._username
                        )
                        
                        # First authenticate to trigger MFA
                        try:
                            cognito.authenticate(password=self._password)
                        except SMSMFAChallengeException:
                            pass  # Expected
                        
                        # Now respond to the SMS challenge
                        client = cognito.client
                        response = client.respond_to_auth_challenge(
                            ClientId=COGNITO_CLIENT_ID,
                            ChallengeName='SMS_MFA',
                            Session=self._session_token,
                            ChallengeResponses={
                                'SMS_MFA_CODE': mfa_code,
                                'USERNAME': self._username,
                            }
                        )
                        
                        if 'AuthenticationResult' in response:
                            return {
                                "success": True,
                                "id_token": response['AuthenticationResult']['IdToken'],
                                "access_token": response['AuthenticationResult']['AccessToken'],
                            }
                        else:
                            return {"success": False}
                            
                    except ClientError as err:
                        error_code = err.response.get("Error", {}).get("Code", "")
                        if "CodeMismatchException" in error_code:
                            return {"success": False, "error": "invalid_code"}
                        raise
                
                result = await self.hass.async_add_executor_job(_verify_mfa)
                
                if result.get("success"):
                    # MFA verified successfully
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
                    errors["base"] = "invalid_mfa"

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during MFA")
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


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""

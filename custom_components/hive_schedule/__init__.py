"""
Hive Schedule Manager Integration for Home Assistant
Enables programmatic control of British Gas Hive heating schedules

For more details about this integration, please refer to the documentation at
https://github.com/YOUR_USERNAME/hive-schedule-manager
"""

import logging
import voluptuous as vol
from datetime import time, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "hive_schedule"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

# Service names
SERVICE_SET_SCHEDULE = "set_heating_schedule"
SERVICE_SET_DAY = "set_day_schedule"
SERVICE_UPDATE_FROM_CALENDAR = "update_from_calendar"

# Attributes
ATTR_NODE_ID = "node_id"
ATTR_DAY = "day"
ATTR_SCHEDULE = "schedule"
ATTR_IS_WORKDAY = "is_workday"
ATTR_WAKE_TIME = "wake_time"

# Configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period,
        })
    },
    extra=vol.ALLOW_EXTRA,
)

# Service schemas
SET_SCHEDULE_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_SCHEDULE): vol.Schema({
        vol.Optional('monday'): cv.ensure_list,
        vol.Optional('tuesday'): cv.ensure_list,
        vol.Optional('wednesday'): cv.ensure_list,
        vol.Optional('thursday'): cv.ensure_list,
        vol.Optional('friday'): cv.ensure_list,
        vol.Optional('saturday'): cv.ensure_list,
        vol.Optional('sunday'): cv.ensure_list,
    })
})

SET_DAY_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_DAY): vol.In(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']),
    vol.Required(ATTR_SCHEDULE): [{
        vol.Required('time'): cv.string,
        vol.Required('temp'): vol.Coerce(float),
    }]
})

CALENDAR_SCHEMA = vol.Schema({
    vol.Required(ATTR_NODE_ID): cv.string,
    vol.Required(ATTR_IS_WORKDAY): cv.boolean,
    vol.Optional(ATTR_WAKE_TIME): cv.string,
})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Hive Schedule Manager component."""
    
    _LOGGER.info("Setting up Hive Schedule Manager")
    
    # Get auth token from existing Hive integration
    def get_hive_auth_token() -> Optional[str]:
        """Extract auth token from existing Hive integration."""
        if 'hive' not in hass.data:
            _LOGGER.error("Hive integration not found. Please ensure the official Hive integration is set up first.")
            return None
            
        try:
            # Try to access the Hive session
            hive_session = hass.data['hive'].get('session')
            if hive_session and hasattr(hive_session, 'auth'):
                token = getattr(hive_session.auth, 'token', None)
                if token:
                    _LOGGER.debug("Successfully retrieved Hive auth token")
                    return token
        except (KeyError, AttributeError) as e:
            _LOGGER.error(f"Could not access Hive auth token: {e}")
        
        return None
    
    class HiveScheduleAPI:
        """API client for Hive Schedule operations."""
        
        BASE_URL = "https://beekeeper-uk.hivehome.com/1.0"
        
        def __init__(self):
            """Initialize the API client."""
            self.session = requests.Session()
            self.session.headers.update({
                'Content-Type': 'application/json',
                'Accept': '*/*',
                'Origin': 'https://my.hivehome.com',
                'Referer': 'https://my.hivehome.com/'
            })
            self._token = None
        
        def update_auth(self, token: str) -> None:
            """Update authorization token."""
            self._token = token
            self.session.headers['Authorization'] = token
            _LOGGER.debug("Updated API authorization token")
        
        @property
        def has_auth(self) -> bool:
            """Check if we have a valid auth token."""
            return self._token is not None
        
        @staticmethod
        def time_to_minutes(t: str) -> int:
            """Convert time string to minutes from midnight."""
            if isinstance(t, str):
                h, m = map(int, t.split(':'))
                return h * 60 + m
            return t.hour * 60 + t.minute
        
        def build_schedule_entry(self, time_str: str, temp: float) -> Dict:
            """Build a single schedule entry."""
            return {
                "value": {"target": float(temp)},
                "start": self.time_to_minutes(time_str)
            }
        
        def update_schedule(self, node_id: str, schedule_data: Dict) -> bool:
            """Send schedule update to Hive."""
            if not self.has_auth:
                _LOGGER.error("Cannot update schedule: No auth token available")
                raise HomeAssistantError("Hive authentication not available. Ensure Hive integration is loaded.")
            
            url = f"{self.BASE_URL}/nodes/heating/{node_id}"
            
            try:
                _LOGGER.debug(f"Sending schedule update to {url}")
                response = self.session.post(url, json=schedule_data, timeout=30)
                response.raise_for_status()
                _LOGGER.info(f"Successfully updated Hive schedule for node {node_id}")
                return True
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    _LOGGER.error("Authentication failed. Token may have expired.")
                    raise HomeAssistantError("Hive authentication failed. Try reloading the Hive integration.")
                elif e.response.status_code == 404:
                    _LOGGER.error(f"Node ID not found: {node_id}")
                    raise HomeAssistantError(f"Invalid node ID: {node_id}")
                else:
                    _LOGGER.error(f"HTTP error updating schedule: {e}")
                    raise HomeAssistantError(f"Failed to update schedule: {e}")
            except requests.exceptions.Timeout:
                _LOGGER.error("Request to Hive API timed out")
                raise HomeAssistantError("Hive API request timed out")
            except requests.exceptions.RequestException as e:
                _LOGGER.error(f"Request error updating schedule: {e}")
                raise HomeAssistantError(f"Failed to update schedule: {e}")
    
    # Initialize API
    api = HiveScheduleAPI()
    hass.data[DOMAIN] = {'api': api}
    
    # Refresh auth token periodically
    async def refresh_auth(now=None):
        """Refresh authentication token from Hive integration."""
        token = await hass.async_add_executor_job(get_hive_auth_token)
        if token:
            api.update_auth(token)
        else:
            _LOGGER.warning("Could not refresh Hive auth token")
    
    # Initial auth
    await refresh_auth()
    
    if not api.has_auth:
        _LOGGER.error("Failed to initialize: Could not get Hive authentication token")
        return False
    
    # Set up periodic refresh
    scan_interval = config.get(DOMAIN, {}).get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    async_track_time_interval(hass, refresh_auth, scan_interval)
    _LOGGER.debug(f"Set up auth token refresh every {scan_interval}")
    
    # Service: Set complete week schedule
    async def handle_set_schedule(call: ServiceCall) -> None:
        """Handle set_heating_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        schedule_config = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info(f"Setting complete schedule for node {node_id}")
        
        # Build schedule in Hive format
        schedule_data = {"schedule": {}}
        
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            if day in schedule_config:
                day_schedule = []
                for entry in schedule_config[day]:
                    day_schedule.append(
                        api.build_schedule_entry(entry['time'], entry['temp'])
                    )
                schedule_data["schedule"][day] = day_schedule
            else:
                # Default: 16°C all day
                schedule_data["schedule"][day] = [
                    api.build_schedule_entry("00:00", 16.0)
                ]
        
        # Update schedule
        try:
            await hass.async_add_executor_job(
                api.update_schedule, node_id, schedule_data
            )
        except HomeAssistantError:
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error setting schedule: {e}")
            raise HomeAssistantError(f"Unexpected error: {e}")
    
    # Service: Set single day schedule
    async def handle_set_day(call: ServiceCall) -> None:
        """Handle set_day_schedule service call."""
        node_id = call.data[ATTR_NODE_ID]
        day = call.data[ATTR_DAY].lower()
        day_schedule = call.data[ATTR_SCHEDULE]
        
        _LOGGER.info(f"Setting schedule for {day} on node {node_id}")
        
        # For single day update, use a default schedule for other days
        default_schedule = [
            {"time": "06:30", "temp": 18.0},
            {"time": "08:00", "temp": 16.0},
            {"time": "16:30", "temp": 19.5},
            {"time": "21:30", "temp": 16.0}
        ]
        
        schedule_data = {"schedule": {}}
        
        for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            if d == day:
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry['time'], entry['temp'])
                    for entry in day_schedule
                ]
            else:
                schedule_data["schedule"][d] = [
                    api.build_schedule_entry(entry['time'], entry['temp'])
                    for entry in default_schedule
                ]
        
        try:
            await hass.async_add_executor_job(
                api.update_schedule, node_id, schedule_data
            )
        except HomeAssistantError:
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error setting day schedule: {e}")
            raise HomeAssistantError(f"Unexpected error: {e}")
    
    # Service: Update based on calendar (work day vs weekend)
    async def handle_calendar_update(call: ServiceCall) -> None:
        """Handle update_from_calendar service call."""
        node_id = call.data[ATTR_NODE_ID]
        is_workday = call.data[ATTR_IS_WORKDAY]
        wake_time = call.data.get(ATTR_WAKE_TIME, "06:30" if is_workday else "07:30")
        
        # Determine tomorrow's day
        tomorrow = datetime.now() + timedelta(days=1)
        day = tomorrow.strftime('%A').lower()
        
        _LOGGER.info(f"Updating {day} schedule from calendar (workday={is_workday})")
        
        # Build appropriate schedule
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
        
        # Update just tomorrow's schedule
        await handle_set_day(ServiceCall(
            DOMAIN,
            SERVICE_SET_DAY,
            {ATTR_NODE_ID: node_id, ATTR_DAY: day, ATTR_SCHEDULE: day_schedule}
        ))
        
        _LOGGER.info(f"Updated {day} schedule for {'workday' if is_workday else 'weekend'}")
    
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
    
    _LOGGER.info("Hive Schedule Manager setup complete")
    return True

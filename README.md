# Hive Schedule Manager v3.0

A Home Assistant custom integration for managing Hive heating schedules with support for schedule profiles and two-factor authentication.

## Features

- **UI Configuration Flow**: Easy setup through Home Assistant UI with 2FA support
- **Persistent Credentials**: Credentials stored securely, no need to re-enter 2FA on restart
- **Schedule Profiles**: Pre-defined heating schedules for different scenarios
- **Single Day Updates**: Update only the day you want without affecting other days
- **Automatic Token Refresh**: Handles authentication token renewal automatically

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right and select "Custom repositories"
4. Add the repository URL: `https://github.com/rrwood/hive-schedule-manager`
5. Select category: "Integration"
6. Click "Add"
7. Search for "Hive Schedule Manager" and install
8. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy the `hive_schedule` folder to your `custom_components` directory
3. Restart Home Assistant

## Setup

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Hive Schedule Manager"
4. Enter your Hive account email and password
5. If you have 2FA enabled, enter the verification code sent to your phone
6. Click Submit

The integration will now be configured and ready to use!

## Usage

### Service: `hive_schedule.set_day_schedule`

Update the heating schedule for a specific day using either a pre-defined profile or a custom schedule.

#### Using a Profile

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"
```

#### Using a Custom Schedule

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "saturday"
  schedule:
    - time: "08:00"
      temp: 18.0
    - time: "22:00"
      temp: 16.0
```

### Available Profiles

- **weekday**: Standard workday schedule (early rise, away during day, evening warmup)
- **weekend**: Relaxed weekend schedule (later start, comfortable all day)
- **holiday**: Holiday schedule (relaxed timing, extended evening)
- **weekday_early**: Early start workday (5:30 AM warmup)
- **weekday_late**: Late return workday (6:30 PM warmup)
- **wfh**: Work from home schedule (comfortable all day)
- **away**: Minimal heating for frost protection
- **all_day_comfort**: Constant comfortable temperature

### Finding Your Node ID

The easiest way to find your Hive thermostat's node ID is to:

1. Go to Developer Tools → States
2. Find your Hive climate entity (e.g., `climate.heating`)
3. Look for the `node_id` attribute in the entity's attributes

Alternatively, check the diagnostic logs when the integration starts up - it will show available Hive nodes.

## Example Automations

### Set Weekday Schedule

```yaml
automation:
  - alias: "Set Weekday Heating Schedule"
    trigger:
      - platform: time
        at: "00:01:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "your-node-id-here"
          day: "{{ now().strftime('%A').lower() }}"
          profile: "weekday"
```

### Set Weekend Schedule

```yaml
automation:
  - alias: "Set Weekend Heating Schedule"
    trigger:
      - platform: time
        at: "00:01:00"
    condition:
      - condition: time
        weekday:
          - sat
          - sun
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "your-node-id-here"
          day: "{{ now().strftime('%A').lower() }}"
          profile: "weekend"
```

### Custom Schedule Based on Calendar

```yaml
automation:
  - alias: "Adjust Heating for Early Meeting"
    trigger:
      - platform: calendar
        event: start
        entity_id: calendar.work
        offset: "-12:00:00"
    condition:
      - condition: template
        value_template: "{{ '07:00' in trigger.calendar_event.summary.lower() }}"
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "your-node-id-here"
          day: "{{ (now() + timedelta(hours=12)).strftime('%A').lower() }}"
          profile: "weekday_early"
```

## Customizing Profiles

To customize the schedule profiles, edit the `schedule_profiles.py` file in the integration directory. Each profile is defined as a list of time/temperature pairs:

```python
PROFILES = {
    "my_custom_profile": [
        {"time": "06:00", "temp": 19.0},
        {"time": "09:00", "temp": 17.0},
        {"time": "17:00", "temp": 20.0},
        {"time": "23:00", "temp": 16.0},
    ],
}
```

After editing, restart Home Assistant for changes to take effect.

## Troubleshooting

### Authentication Issues

If you're having trouble authenticating:

1. Verify your Hive credentials are correct
2. Check that 2FA is enabled on your Hive account if prompted
3. Try removing and re-adding the integration
4. Check the Home Assistant logs for detailed error messages

### Service Not Updating Schedule

If the service call completes but the schedule doesn't update:

1. Verify the node_id is correct
2. Check that the time format is HH:MM (24-hour format)
3. Ensure temperatures are between 5°C and 32°C
4. Check Home Assistant logs for API errors

### Token Refresh Issues

The integration automatically refreshes tokens every 30 minutes. If you experience authentication issues:

1. Use the `hive_schedule.refresh_token` service to manually refresh
2. Check logs for token refresh errors
3. If issues persist, remove and re-add the integration

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/rrwood/hive-schedule-manager/issues

## Changelog

### v3.0.0
- Added UI configuration flow with 2FA support
- Credentials now stored securely (no re-authentication on restart)
- Added schedule profile system
- Fixed `set_day_schedule` to only update specified day
- Removed unused services (set_heating_schedule, update_from_calendar)
- Improved error handling and logging

### v2.0.0
- Added 2FA support (required each restart)
- Standalone authentication

### v1.0.0
- Initial release

# Hive Schedule Manager for Home Assistant

Control your Hive heating schedules directly from Home Assistant with customizable YAML-based schedule profiles.

**Version:** 1.1.17 Production  
**Status:** Stable - POST-based schedule updates

## Features

✅ **Set heating schedules** for any day of the week  
✅ **YAML-based profiles** - easily customize schedules  
✅ **Multiple built-in profiles** (weekday, weekend, holiday, etc.)  
✅ **Custom schedules** via service calls  
✅ **Automatic token management** with AWS Cognito  
✅ **MFA support** during setup  
✅ **Debug logging** with readable schedule output  
✅ **Home Assistant config flow** - easy UI-based setup

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click "Integrations"
3. Click the 3 dots in the top right → "Custom repositories"
4. Add this repository URL
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/hive_schedule` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Step 1: Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **Hive Schedule Manager**
4. Enter your Hive credentials (email and password)
5. Complete MFA verification if prompted
6. Done!

### Step 2: Find Your Node ID

Your heating node ID is needed to control schedules.

**How to find it:**

1. Log into the Hive web interface: https://my.hivehome.com
2. Click on your heating device
3. Look at the URL in your browser - the node ID is the **last part of the URL**

**Example:**
```
URL: https://my.hivehome.com/products/heating/d2708e98-f22f-483e-b590-9ddbd642a3b7
Node ID: d2708e98-f22f-483e-b590-9ddbd642a3b7
```

Copy this ID - you'll need it for service calls!

### Step 3: Customize Schedule Profiles (Optional)

A file called `hive_schedule_profiles.yaml` will be automatically created in your Home Assistant config directory on first run.

**Location:** `/config/hive_schedule_profiles.yaml`

Edit this file to customize your schedules:

```yaml
# Example: Custom weekend schedule
weekend:
  - time: "08:00"
    temp: 19.0
  - time: "23:00"
    temp: 17.0

# Add your own profiles
my_custom_profile:
  - time: "07:00"
    temp: 18.5
  - time: "22:00"
    temp: 16.0
```

**Rules:**
- Time format: `"HH:MM"` (24-hour, in quotes)
- Temperature: 5.0 - 32.0°C
- At least one entry per profile
- Times in chronological order recommended

After editing, restart Home Assistant or just call the service - profiles are reloaded automatically!

## Built-in Profiles

The integration includes these pre-configured profiles:

| Profile | Description | Schedule |
|---------|-------------|----------|
| `weekday` | Standard workday | 06:30→18°C, 08:00→16°C, 16:30→19.5°C, 21:30→16°C |
| `weekend` | Relaxed weekend | 07:30→18°C, 09:00→19°C, 22:00→16°C |
| `holiday` | Extended comfort | 08:00→18°C, 22:30→16°C |
| `weekday_early` | Early start workday | 05:30→18°C, 07:00→16°C, 16:30→19.5°C, 21:30→16°C |
| `weekday_late` | Late return workday | 06:30→18°C, 08:00→16°C, 18:30→19.5°C, 23:00→16°C |
| `wfh` | Work from home | 06:30→18°C, 09:00→19°C, 17:00→19.5°C, 22:00→16°C |
| `away` | Frost protection | 00:00→12°C |
| `all_day_comfort` | Constant warmth | 00:00→19°C |

## Usage

### Set Schedule Using a Profile

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"
```

### Set Schedule with Custom Times

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "saturday"
  schedule:
    - time: "08:00"
      temp: 19.0
    - time: "23:00"
      temp: 17.0
```

### Example Automation: Set Weekday Schedules

```yaml
automation:
  - alias: "Set Hive Weekday Schedule"
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
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ now().strftime('%A').lower() }}"
          profile: "weekday"
```

### Example Automation: Weekend Override

```yaml
automation:
  - alias: "Weekend Heating Schedule"
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
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ now().strftime('%A').lower() }}"
          profile: "weekend"
```

## Services

### `hive_schedule.set_day_schedule`

Update the heating schedule for a specific day.

**Parameters:**

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `node_id` | Yes | string | Your Hive heating node ID |
| `day` | Yes | string | Day of week: monday, tuesday, wednesday, thursday, friday, saturday, sunday |
| `profile` | No* | string | Profile name from hive_schedule_profiles.yaml |
| `schedule` | No* | list | Custom schedule (list of time/temp objects) |

*Either `profile` OR `schedule` must be provided

## Viewing Schedules

After setting a schedule, check your Home Assistant logs to see what was actually set:

```
UPDATED SCHEDULE (confirmed by Hive)
================================================================================
MONDAY:
  06:30 → 18.0°C
  08:00 → 16.0°C
  16:30 → 19.5°C
  21:30 → 16.0°C
================================================================================
```

**Note:** This integration can SET schedules but cannot READ the current schedule from Hive due to API limitations. To view your current schedules:
- Check Home Assistant logs after setting a schedule
- Use the official Hive mobile app or website

## Troubleshooting

### "Invalid Refresh Token" Error

Your authentication tokens have expired. Fix:

1. Go to **Settings** → **Devices & Services**
2. Find **Hive Schedule Manager**
3. Click **Delete**
4. Restart Home Assistant
5. Add the integration again

### "Node ID not found" Error

Double-check your node ID:
1. Log into https://my.hivehome.com
2. Click your heating device
3. Copy the ID from the **end of the URL**

### Profile Not Found

If you get "Unknown profile":
1. Check `hive_schedule_profiles.yaml` exists in `/config/`
2. Verify the profile name matches exactly (case-sensitive)
3. Restart Home Assistant after editing profiles

### Changes Not Applied

If the integration seems to use old code:
1. **Restart Home Assistant** (not just reload)
2. Check logs for version number: `v1.1.17`
3. Clear browser cache if using the UI

## Debug Logging

To enable detailed logging, add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.hive_schedule: debug
```

Then restart Home Assistant. You'll see:
- Full API request/response details
- Token refresh attempts
- Schedule updates in readable format

## Limitations

### What Works ✅
- Setting heating schedules for any day
- Using custom profiles
- Automatic token management
- MFA during setup

### What Doesn't Work ❌
- **Reading current schedules** - Hive API restricts GET requests to third-party apps
- **Multi-zone systems** - Single node ID per installation (add integration multiple times for multiple zones)

### Why No Schedule Reading?

The Hive API uses different permissions for different clients:
- Official Hive apps: Full read/write access
- Third-party integrations: Write-only access

This is an intentional API restriction by Hive (British Gas) to protect their infrastructure and encourage use of official apps.

**Workaround:** Use the Hive mobile app or website to view schedules, use this integration to automate schedule changes!

## Advanced Usage

### Multiple Heating Zones

If you have multiple heating zones:

1. Add the integration once per zone
2. Get the node ID for each zone (different URL ending)
3. Each integration manages one zone
4. Create separate automations for each zone

### Dynamic Schedules

```yaml
automation:
  - alias: "Smart Heating Schedule"
    trigger:
      - platform: state
        entity_id: input_boolean.away_mode
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "your-node-id"
          day: "{{ now().strftime('%A').lower() }}"
          profile: >
            {% if is_state('input_boolean.away_mode', 'on') %}
              away
            {% elif now().weekday() < 5 %}
              weekday
            {% else %}
              weekend
            {% endif %}
```

### Vacation Mode Script

```yaml
script:
  set_vacation_mode:
    sequence:
      - repeat:
          count: 7
          sequence:
            - service: hive_schedule.set_day_schedule
              data:
                node_id: "your-node-id"
                day: >
                  {{ ['monday', 'tuesday', 'wednesday', 'thursday', 
                      'friday', 'saturday', 'sunday'][repeat.index - 1] }}
                profile: "away"
            - delay: 2
```

## Support

### Reporting Issues

Please include:
- Home Assistant version
- Integration version (check logs for `v1.1.17`)
- Relevant log entries (with debug enabled)
- Steps to reproduce

### Useful Information

When reporting issues, please provide:
- Error messages from logs
- Your `hive_schedule_profiles.yaml` (if relevant)
- Service call YAML that's causing issues

## Credits

Created for Home Assistant community  
Uses AWS Cognito for authentication  
Integrates with Hive (British Gas) heating API

## License

MIT License - see LICENSE file

## Changelog

### v1.1.17 (Production)
- ✨ YAML-based schedule profiles
- ✨ Automatic profile file creation
- ✨ Dynamic profile reloading
- ✨ Cleaner code structure
- ✨ Improved logging output
- 🐛 POST-only approach (GET not supported by API)
- 📚 Comprehensive documentation

### Earlier Versions
- v1.1.16: Enhanced debug logging
- v1.1.0: Initial release with config flow
- v1.0.0: Basic functionality

---

**Enjoy automated Hive heating schedules! 🔥**

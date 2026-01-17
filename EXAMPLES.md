# Hive Schedule Manager v3.0 - Service Examples

## Quick Reference

```yaml
# Using a profile
service: hive_schedule.set_day_schedule
data:
  node_id: "your-node-id"
  day: "monday"
  profile: "weekday"

# Using custom schedule
service: hive_schedule.set_day_schedule
data:
  node_id: "your-node-id"
  day: "saturday"
  schedule:
    - time: "08:00"
      temp: 18.0
    - time: "22:00"
      temp: 16.0
```

## Finding Your Node ID

### Method 1: Developer Tools
1. Go to **Developer Tools** → **States**
2. Search for your Hive climate entity (e.g., `climate.heating`)
3. Look for the `node_id` attribute

### Method 2: From Logs
When the integration starts, it logs available nodes. Check your logs:
```
Settings → System → Logs
Search for: "Hive"
```

## Profile Examples

### Standard Weekday
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"
```

Schedule applied:
- 06:30 - 18.0°C (morning warmup)
- 08:00 - 16.0°C (away during day)
- 16:30 - 19.5°C (evening warmup)
- 21:30 - 16.0°C (night setback)

### Weekend
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "saturday"
  profile: "weekend"
```

Schedule applied:
- 07:30 - 18.0°C (later morning)
- 09:00 - 19.0°C (comfortable day)
- 22:00 - 16.0°C (later night setback)

### Work From Home
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "wednesday"
  profile: "wfh"
```

Schedule applied:
- 06:30 - 18.0°C
- 09:00 - 19.0°C (comfortable for working)
- 17:00 - 19.5°C
- 22:00 - 16.0°C

### Away/Vacation Mode
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "{{ now().strftime('%A').lower() }}"
  profile: "away"
```

Schedule applied:
- 00:00 - 12.0°C (frost protection only)

## Custom Schedule Examples

### Simple Two-Period Day
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "sunday"
  schedule:
    - time: "08:00"
      temp: 19.0
    - time: "23:00"
      temp: 16.0
```

### Complex Multi-Period Schedule
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "tuesday"
  schedule:
    - time: "05:30"
      temp: 18.0  # Early morning warmup
    - time: "07:00"
      temp: 16.0  # Leave for work
    - time: "12:00"
      temp: 17.0  # Lunch time boost
    - time: "13:00"
      temp: 16.0  # Back down
    - time: "17:00"
      temp: 19.5  # Evening warmup
    - time: "22:00"
      temp: 17.0  # Pre-bed
    - time: "23:00"
      temp: 16.0  # Sleep
```

### Constant Temperature
```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "friday"
  schedule:
    - time: "00:00"
      temp: 20.0  # Same temp all day
```

## Automation Examples

### Daily Schedule Automation

Set different schedules for different days:

```yaml
automation:
  - alias: "Set Daily Heating Schedule"
    trigger:
      - platform: time
        at: "00:01:00"
    action:
      - choose:
          # Weekdays
          - conditions:
              - condition: time
                weekday:
                  - mon
                  - tue
                  - wed
                  - thu
                  - fri
            sequence:
              - service: hive_schedule.set_day_schedule
                data:
                  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
                  day: "{{ now().strftime('%A').lower() }}"
                  profile: "weekday"
          
          # Weekend
          - conditions:
              - condition: time
                weekday:
                  - sat
                  - sun
            sequence:
              - service: hive_schedule.set_day_schedule
                data:
                  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
                  day: "{{ now().strftime('%A').lower() }}"
                  profile: "weekend"
```

### Work From Home Detection

Adjust schedule based on WFH sensor:

```yaml
automation:
  - alias: "WFH Heating Adjustment"
    trigger:
      - platform: state
        entity_id: input_boolean.working_from_home
        to: "on"
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ now().strftime('%A').lower() }}"
          profile: "wfh"
```

### Calendar-Based Scheduling

Adjust schedule based on calendar events:

```yaml
automation:
  - alias: "Early Meeting Heating"
    trigger:
      - platform: calendar
        event: start
        entity_id: calendar.work
        offset: "-12:00:00"
    condition:
      - condition: template
        value_template: >
          {{ 'early' in trigger.calendar_event.summary.lower() or
             trigger.calendar_event.start < (now() + timedelta(hours=12)).replace(hour=7, minute=0) }}
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ (now() + timedelta(hours=12)).strftime('%A').lower() }}"
          profile: "weekday_early"
```

### Vacation Mode

Automatically set minimal heating when away:

```yaml
automation:
  - alias: "Vacation Mode Heating"
    trigger:
      - platform: state
        entity_id: input_boolean.vacation_mode
        to: "on"
    action:
      - repeat:
          count: 7
          sequence:
            - service: hive_schedule.set_day_schedule
              data:
                node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
                day: >
                  {% set days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] %}
                  {{ days[repeat.index - 1] }}
                profile: "away"
            - delay: "00:00:01"
```

### Weather-Based Adjustment

Boost heating on very cold days:

```yaml
automation:
  - alias: "Cold Day Heating Boost"
    trigger:
      - platform: numeric_state
        entity_id: weather.home
        attribute: temperature
        below: 0
    condition:
      - condition: time
        after: "00:00:00"
        before: "06:00:00"
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ now().strftime('%A').lower() }}"
          schedule:
            - time: "06:00"
              temp: 19.5  # Higher temp on cold days
            - time: "08:00"
              temp: 17.0
            - time: "16:00"
              temp: 20.0  # Higher evening temp
            - time: "22:00"
              temp: 17.0  # Higher night temp
```

### Guest Mode

Comfortable all-day heating when guests stay:

```yaml
automation:
  - alias: "Guest Mode Heating"
    trigger:
      - platform: state
        entity_id: input_boolean.guest_mode
        to: "on"
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ now().strftime('%A').lower() }}"
          profile: "all_day_comfort"
```

### Tomorrow's Schedule Based on Workday Sensor

```yaml
automation:
  - alias: "Set Tomorrow's Schedule"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ (now() + timedelta(days=1)).strftime('%A').lower() }}"
          profile: >
            {% if is_state('binary_sensor.workday_tomorrow', 'on') %}
              weekday
            {% else %}
              weekend
            {% endif %}
```

## Script Examples

### Reusable Schedule Script

Create a script for easy schedule changes:

```yaml
script:
  set_heating_profile:
    alias: "Set Heating Profile"
    fields:
      profile_name:
        description: "Profile to apply"
        example: "weekday"
      target_day:
        description: "Day to update (optional, defaults to today)"
        example: "monday"
    sequence:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "{{ target_day | default(now().strftime('%A').lower()) }}"
          profile: "{{ profile_name }}"
```

Usage:
```yaml
# In automation or manual call
service: script.set_heating_profile
data:
  profile_name: "wfh"
  target_day: "wednesday"
```

### Set Week's Schedule Script

```yaml
script:
  set_weekly_schedule:
    alias: "Set Full Week Schedule"
    sequence:
      - repeat:
          count: 5
          sequence:
            - service: hive_schedule.set_day_schedule
              data:
                node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
                day: >
                  {% set days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'] %}
                  {{ days[repeat.index - 1] }}
                profile: "weekday"
            - delay: "00:00:01"
      
      - repeat:
          count: 2
          sequence:
            - service: hive_schedule.set_day_schedule
              data:
                node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
                day: >
                  {% set days = ['saturday', 'sunday'] %}
                  {{ days[repeat.index - 1] }}
                profile: "weekend"
            - delay: "00:00:01"
```

## Manual Token Refresh

Normally automatic, but you can manually refresh:

```yaml
service: hive_schedule.refresh_token
```

Useful in automations if you suspect auth issues:

```yaml
automation:
  - alias: "Refresh Hive Token Weekly"
    trigger:
      - platform: time
        at: "03:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - service: hive_schedule.refresh_token
```

## Troubleshooting Examples

### Test Service Call in Developer Tools

1. Go to **Developer Tools** → **Services**
2. Select `hive_schedule.set_day_schedule`
3. Enter YAML:
   ```yaml
   node_id: "your-node-id"
   day: "monday"
   profile: "weekday"
   ```
4. Click "Call Service"
5. Check logs for success/errors

### Verify Schedule Was Applied

Check Hive app or:
1. Use official Hive integration to view current schedule
2. Or check the diagnostic logs after calling the service

### Debug Logging

Enable debug logging to see detailed API calls:

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.hive_schedule: debug
```

Then check Settings → System → Logs for detailed information about each API call.

## Important Notes

### Time Format
- Must be 24-hour format: `"HH:MM"`
- Examples: `"06:30"`, `"18:00"`, `"23:45"`
- Invalid: `"6:30 AM"`, `"18:00:00"`

### Temperature Range
- Minimum: 5.0°C
- Maximum: 32.0°C
- Use decimals: `18.0`, `19.5`

### Day Names
- Must be lowercase: `"monday"`, `"tuesday"`, etc.
- Use templates for dynamic days: `{{ now().strftime('%A').lower() }}`

### Node ID
- Get from Hive climate entity attributes
- Format: UUID (e.g., `"d2708e98-f22f-483e-b590-9ddbd642a3b7"`)
- Stays constant for each thermostat

### Profile vs Schedule
- Can't use both in same call
- If both provided, `schedule` takes priority
- One of them must be provided

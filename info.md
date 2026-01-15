# Hive Schedule Manager

Extends the Hive integration to enable programmatic control of heating schedules.

## Features

✅ Update heating schedules via service calls
✅ Set schedules for individual days or full week  
✅ Calendar-based automation support
✅ Compatible with existing Hive integration

## Quick Start

After installation:

1. Add to `configuration.yaml`:
   ```yaml
   hive_schedule:
   ```
2. Restart Home Assistant
3. Find your Node ID (see README)
4. Use service calls in automations

## Services

- `hive_schedule.set_heating_schedule` - Full week schedule
- `hive_schedule.set_day_schedule` - Single day
- `hive_schedule.update_from_calendar` - Calendar-based

## Example

```yaml
service: hive_schedule.update_from_calendar
data:
  node_id: "YOUR_NODE_ID"
  is_workday: true
```

See full documentation in [README](https://github.com/YOUR_USERNAME/hive-schedule-manager).

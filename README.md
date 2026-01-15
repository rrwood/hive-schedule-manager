# Hive Schedule Manager for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/rrwood/hive-schedule-manager.svg)](https://github.com/rrwood/hive-schedule-manager/releases)
[![License](https://img.shields.io/github/license/rrwood/hive-schedule-manager.svg)](LICENSE)

A Home Assistant custom integration that extends the official Hive integration to enable programmatic control of heating schedules.

## Features

- ✅ Full schedule control for any day of the week
- ✅ Calendar-based automation
- ✅ Works with existing Hive integration
- ✅ Simple service calls

## Installation

### HACS (Recommended)

1. Open HACS
2. Go to "Integrations"
3. Click the three dots (top right) → "Custom repositories"
4. Add: `https://github.com/rrwood/hive-schedule-manager`
5. Category: "Integration"
6. Click "Add"
7. Find "Hive Schedule Manager" and click "Download"
8. Restart Home Assistant

### Manual

Copy `custom_components/hive_schedule` to your `<config>/custom_components/` directory.

## Configuration

Add to `configuration.yaml`:

```yaml
hive_schedule:
```

Restart Home Assistant.

## Finding Your Node ID

1. Go to https://my.hivehome.com
2. Open Developer Tools (F12)
3. Go to Network tab
4. Make a change to your heating
5. Look for requests to `beekeeper-uk.hivehome.com`
6. The URL contains your node ID

## Usage

### Set Tomorrow's Schedule

```yaml
service: hive_schedule.update_from_calendar
data:
  node_id: "YOUR_NODE_ID"
  is_workday: true
```

### Set Specific Day

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "YOUR_NODE_ID"
  day: "monday"
  schedule:
    - time: "06:30"
      temp: 18.0
    - time: "21:30"
      temp: 16.0
```

## Example Automation

```yaml
automation:
  - alias: "Update Tomorrow's Heating"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: hive_schedule.update_from_calendar
        data:
          node_id: "YOUR_NODE_ID"
          is_workday: >
            {{ (now() + timedelta(days=1)).weekday() < 5 }}
```

## Support

- [Report a Bug](https://github.com/rrwood/hive-schedule-manager/issues/new?template=bug_report.md)
- [Request a Feature](https://github.com/rrwood/hive-schedule-manager/issues/new?template=feature_request.md)

## License

MIT License - see [LICENSE](LICENSE)

## Disclaimer

This is unofficial and not affiliated with British Gas or Hive.

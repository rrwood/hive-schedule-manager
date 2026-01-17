# Hive Schedule Manager - Enhanced Debug Version 1.1.16

## What's New

This enhanced version includes two major improvements:

### 1. 🔍 Enhanced Debug Logging

The integration now provides comprehensive debug logging for all API calls, making troubleshooting much easier.

#### What's Logged:

- **Full API call details** including:
  - HTTP method (GET/POST)
  - Complete URL
  - All headers (with authorization token safely truncated)
  - Request payload (formatted JSON)
  - Response status
  - Response data

#### How to Enable Debug Logging:

Add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.hive_schedule: debug
```

Then restart Home Assistant. You'll see detailed logs like:

```
================================================================================
API CALL DEBUG INFO
================================================================================
Method: POST
URL: https://beekeeper-uk.hivehome.com/1.0/nodes/heating/d2708e98-f22f-483e-b590-9ddbd642a3b7
--------------------------------------------------------------------------------
Headers:
  Content-Type: application/json
  Accept: */*
  Origin: https://my.hivehome.com
  Referer: https://my.hivehome.com/
  Authorization: eyJraWQiO...GHI789xyz (truncated for security)
--------------------------------------------------------------------------------
Payload (JSON):
{
  "schedule": {
    "monday": [
      {
        "value": {
          "target": 18.0
        },
        "start": 390
      },
      {
        "value": {
          "target": 16.0
        },
        "start": 1320
      }
    ]
  }
}
================================================================================
```

### 2. 📖 Read Schedule Before Writing

The integration now reads the current schedule from Hive before making updates, which helps with:

- **Verification**: Confirm what schedule is currently set
- **Debugging**: See exactly what's changing
- **Safety**: Understand the state before modifications

#### Automatic Read-Before-Write:

This is **enabled by default** for the `set_day_schedule` service. The current schedule is logged before any update is sent.

#### New `get_schedule` Service:

You can also manually retrieve the current schedule:

```yaml
service: hive_schedule.get_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
```

This will:
- Retrieve the full schedule from Hive
- Log it in both raw and human-readable formats
- Fire a `hive_schedule_schedule_retrieved` event with the data

## Usage Examples

### Example 1: Set a Day Schedule (with automatic read-before-write)

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"
```

**What happens:**
1. Current schedule is read and logged
2. New schedule is sent
3. All API calls are fully logged

### Example 2: Get Current Schedule

```yaml
service: hive_schedule.get_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
```

**What you'll see in logs:**

```
Current schedule (readable format):
{
  "monday": [
    {"time": "06:30", "temp": 18.0},
    {"time": "22:00", "temp": 16.0}
  ],
  "tuesday": [
    {"time": "06:30", "temp": 18.0},
    {"time": "22:00", "temp": 16.0}
  ],
  ...
}
```

### Example 3: Listen for Schedule Retrieved Event

You can create automations that respond to schedule retrieval:

```yaml
automation:
  - alias: "Log Hive Schedule Retrieved"
    trigger:
      platform: event
      event_type: hive_schedule_schedule_retrieved
    action:
      - service: notify.persistent_notification
        data:
          message: >
            Schedule for {{ trigger.event.data.node_id }} retrieved!
            {{ trigger.event.data.schedule }}
```

## Debugging Tips

### Common Issues to Check:

1. **Authentication Issues (401 errors)**
   - Check the truncated token in logs
   - Verify token refresh is working
   - Look for "Successfully refreshed authentication token" messages

2. **Invalid Node ID (404 errors)**
   - Check the URL in the debug logs
   - Verify your node_id is correct

3. **Payload Format Issues**
   - Examine the formatted JSON payload in logs
   - Verify time is in "HH:MM" format
   - Verify temperatures are valid floats

4. **Network Issues**
   - Check for timeout messages
   - Verify response status codes

### What to Look For in Logs:

✅ **Success indicators:**
- `✓ Successfully updated Hive schedule for node X`
- `✓ Successfully retrieved schedule for node X`
- `Response status: 200`

❌ **Failure indicators:**
- `Authentication failed (401)`
- `Node ID not found: X`
- `Request to Hive API timed out`

## Installation

1. Copy the entire `custom_components/hive_schedule/` directory to your Home Assistant `custom_components` folder
2. Restart Home Assistant
3. Enable debug logging (see above)

## Files Changed

- `__init__.py`: Enhanced with debug logging and read-before-write capability
- `services.yaml`: Added `get_schedule` service documentation

## Compatibility

- Works with existing Hive Schedule Manager configurations
- No breaking changes
- All existing services continue to work as before

## Support

When reporting issues, please include:
1. Relevant logs from the debug output (with tokens redacted)
2. The service call you're trying to make
3. Your node_id (can be anonymized)
4. Home Assistant version

---

**Version**: 1.1.16 (Enhanced Debug)  
**Original Version**: Based on Hive Schedule Manager 1.1.0

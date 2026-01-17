# Hive Schedule Manager - Enhanced Debug Version 1.1.16

## What's New

This enhanced version includes comprehensive debugging for all API calls.

### ✅ Enhanced API Call Debugging

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

### ⚠️ GET Request Limitation (Read Schedule)

**Important Discovery**: The Hive beekeeper-uk API has different authentication requirements for GET vs POST:

- **POST requests** (setting schedules) ✅ Work with bearer token authentication
- **GET requests** (reading schedules) ❌ Require AWS Signature V4 authentication

This means the `get_schedule` service and read-before-write features are **currently not functional** without implementing AWS SigV4 signing.

#### Why This Happens:

The error you'll see:
```json
{
  "message": "Authorization header requires 'Credential' parameter. 
              Authorization header requires 'Signature' parameter. 
              Authorization header requires 'SignedHeaders' parameter..."
}
```

This is AWS API Gateway requiring a signed request using AWS Signature Version 4 protocol.

#### Workaround:

**Good news!** POST requests return the schedule in the response:

```json
{
  "schedule": {
    "wednesday": [
      {"value": {"target": 18.5}, "start": 330},
      {"value": {"target": 16.5}, "start": 540},
      {"value": {"target": 18.5}, "start": 960},
      {"value": {"target": 16}, "start": 1320}
    ]
  }
}
```

When you set a schedule, you can see the result in the debug logs:
```
Response text: {"schedule":{"wednesday":[...]}}
```

#### Current Status:

- ✅ **set_day_schedule**: Works perfectly with full debug output
- ❌ **get_schedule**: Currently disabled (requires AWS SigV4 implementation)
- ❌ **read_before_write**: Disabled by default (requires AWS SigV4 implementation)

## Usage Examples

### Example 1: Set a Day Schedule (Working)

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"
```

**What happens:**
1. Full API call is logged with all details
2. New schedule is sent via POST (works!)
3. Response includes the updated schedule
4. All details logged for debugging

**Example log output:**
```
2026-01-17 17:47:26.637 INFO Sending schedule update to https://beekeeper-uk.hivehome.com/1.0/nodes/heating/...
2026-01-17 17:47:27.137 DEBUG Response status: 200
2026-01-17 17:47:27.137 DEBUG Response text: {"schedule":{"wednesday":[...]}}
2026-01-17 17:47:27.137 INFO ✓ Successfully updated Hive schedule
```

### Example 2: View Schedule from POST Response

After any `set_day_schedule` call, check the debug logs for:
```
Response text: {"schedule":{"wednesday":[...]}}
```

This shows you the current state of that day's schedule.

### Example 3: Get Schedule (Not Currently Working)

```yaml
service: hive_schedule.get_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
```

**Current result**: 403 Forbidden error due to AWS SigV4 requirement.

**Alternative**: Use POST response to see schedule updates.

## Debugging Tips

### Success Indicators in Logs:

✅ Look for these:
- `✓ Successfully updated Hive schedule for node X`
- `Response status: 200`
- `Response text: {"schedule":...}` - this shows the updated schedule!

### Error Indicators:

❌ Watch for:
- `403 Forbidden` - AWS SigV4 auth required (for GET requests)
- `401 Unauthorized` - Token issue (for POST requests)
- `404 Not Found` - Invalid node_id

### Reading the POST Response:

The POST response includes the schedule you just set. In the debug logs, find:
```
Response text: {"schedule":{"wednesday":[{"value":{"target":18.5},"start":330}...]}}
```

Convert start times (minutes from midnight):
- `330` minutes = 5:30 (330 ÷ 60 = 5.5 hours = 5:30)
- `540` minutes = 9:00 (540 ÷ 60 = 9 hours)
- `960` minutes = 16:00 (960 ÷ 60 = 16 hours = 4:00 PM)
- `1320` minutes = 22:00 (1320 ÷ 60 = 22 hours = 10:00 PM)

## Future Enhancement Possibilities

To make GET requests work, we would need to:

1. Implement AWS Signature V4 signing for requests
2. Use the AWS credentials that the Cognito authentication provides
3. Sign GET requests with proper headers:
   - `X-Amz-Date`
   - `Authorization` with Credential, SignedHeaders, Signature
   - Properly hashed and signed payload

This is feasible but requires additional implementation. For now, the POST responses give us the schedule information we need.

## Installation

1. Copy the entire `custom_components/hive_schedule/` directory to your Home Assistant `custom_components` folder
2. Restart Home Assistant
3. Enable debug logging (see above)

## Files Changed

- `__init__.py`: Enhanced with comprehensive debug logging
- `services.yaml`: Kept for documentation (get_schedule won't work until AWS SigV4 implemented)

## What You Get Right Now

### ✅ Working Features:
- **Comprehensive debug logging** for all API calls
- **Full request/response visibility** for troubleshooting
- **Safe token truncation** in logs
- **Pretty-printed JSON** payloads and responses
- **POST responses show schedule** after updates

### ⏳ Future Features (Need AWS SigV4):
- Direct schedule reading via GET
- Read-before-write capability
- Standalone get_schedule service

## Support

When reporting issues, please include:
1. Relevant logs from the debug output (with tokens redacted)
2. The service call you're trying to make
3. Your node_id (can be anonymized)
4. Home Assistant version

The debug output should give you all the information you need to troubleshoot issues!

---

**Version**: 1.1.16 (Enhanced Debug)  
**Status**: Debug logging fully functional, GET requests require AWS SigV4 implementation

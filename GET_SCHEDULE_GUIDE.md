# Hive Schedule Manager v1.2.0 - GET Support with AWS SigV4

## What's New! 🎉

This version implements **AWS Signature Version 4** authentication to enable GET requests, allowing you to **read the current schedule directly from Hive**.

## New Service: `get_schedule`

Read the MASTER schedule from Hive (not just what you set, but what's actually configured):

```yaml
service: hive_schedule.get_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
```

### What You'll See:

```
INFO Retrieving current schedule from Hive for node d2708e98...
INFO Using AWS Signature V4 for GET request  (or bearer token fallback)
DEBUG API CALL DEBUG INFO
DEBUG Method: GET
INFO ✓ Successfully retrieved schedule
================================================================================
CURRENT SCHEDULE FROM HIVE
================================================================================
MONDAY:
  06:30 → 18.0°C
  22:00 → 16.0°C
TUESDAY:
  06:30 → 18.0°C
  22:00 → 16.0°C
WEDNESDAY:
  06:30 → 18.0°C
  22:00 → 16.0°C
... (all 7 days)
================================================================================
```

**This shows ALL 7 days** in one call!

## How It Works

The integration attempts TWO methods:

### Method 1: AWS Signature V4 (Preferred)
- Extracts AWS credentials from Cognito tokens
- Signs GET requests properly
- Should work if credentials are available

### Method 2: Bearer Token Fallback
- Uses the ID token directly
- May work, may get 403
- Fallback if AWS credentials unavailable

## Installation

1. **Install python-jose** dependency:
   ```bash
   # In your Home Assistant container or venv:
   pip install python-jose
   ```

2. **Copy files**:
   ```
   custom_components/hive_schedule/__init__.py
   custom_components/hive_schedule/services.yaml
   ```

3. **Restart Home Assistant**

4. **Check logs** on startup:
   ```
   INFO Setting up Hive Schedule Manager v1.2.0 (AWS SigV4 + GET Support)
   INFO ✓ AWS credentials extracted from tokens - GET requests should work!
   ```

   OR

   ```
   WARNING ⚠ Could not extract AWS credentials - GET requests may fail
   INFO GET requests will attempt bearer token fallback
   ```

## Usage Examples

### Read Current Schedule

```yaml
service: hive_schedule.get_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
```

Check your logs - you'll see all 7 days beautifully formatted!

### Update and Verify

```yaml
# Set Monday's schedule
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  schedule:
    - time: "07:00"
      temp: 19.0
    - time: "23:00"
      temp: 17.0

# Then read back to verify
service: hive_schedule.get_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
```

### In Automations

```yaml
automation:
  - alias: "Read Hive Schedule Every Morning"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: hive_schedule.get_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
      # Check logs for the current schedule
```

## Troubleshooting

### If AWS Credentials Aren't Extracted

You'll see:
```
WARNING ⚠ Could not extract AWS credentials
```

**This is okay!** The integration will try bearer token fallback. It may:
- ✅ Work anyway (some Hive accounts)
- ❌ Return 403 error

If you get 403, you'll see:
```
ERROR GET request forbidden - AWS credentials may be required
ERROR Response: {"message":"Authorization header requires 'Credential'..."}
```

### Solution if GET Fails

Use the POST approach from v1.1.17:
- Set each day's schedule
- Read from POST response
- Still works perfectly!

## What AWS SigV4 Does

When enabled, the integration:

1. **Extracts credentials** from Cognito ID/Access tokens
2. **Signs requests** with:
   - Access Key ID
   - Secret Access Key  
   - Session Token (if available)
   - Timestamp (X-Amz-Date)
   - Signature (HMAC-SHA256)
3. **Sends proper headers** that Hive API Gateway expects

## Benefits Over Previous Version

| Feature | v1.1.17 | v1.2.0 |
|---------|---------|--------|
| Set schedules | ✅ | ✅ |
| Read from POST | ✅ | ✅ |
| Read via GET | ❌ | ✅ (if AWS creds available) |
| All days at once | ❌ | ✅ |
| True master read | ❌ | ✅ |
| Debug logging | ✅ | ✅ |

## Dependencies

- `python-jose` - For JWT token decoding
- All existing dependencies

## Backward Compatibility

✅ **100% backward compatible** with v1.1.17
- All existing functionality works
- New get_schedule service is optional
- Falls back gracefully if GET fails

## What to Expect

### Best Case (AWS Credentials Available):
```
✓ AWS credentials extracted from tokens
✓ GET requests work perfectly
✓ Read all 7 days in one call
✓ True master schedule from Hive
```

### Fallback Case (No AWS Credentials):
```
⚠ Could not extract AWS credentials
GET may fail with 403
Use POST responses to read schedules (still works!)
```

## Testing

After installation:

1. **Check startup logs** for AWS credential status
2. **Try get_schedule service**
3. **Check if GET succeeds or falls back**
4. **Report results!**

This will help determine if AWS credentials are actually in the tokens for your account.

---

**Version**: 1.2.0  
**Status**: Experimental GET support with AWS SigV4  
**Fallback**: POST-based reading (v1.1.17 method) always available

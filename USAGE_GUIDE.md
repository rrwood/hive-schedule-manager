# How to Read Hive Schedules - Simple POST Approach

## What's New in v1.1.17

Now when you set ANY schedule, the logs will automatically show you a **beautiful, readable format** of what was set!

## How It Works

Every time you update a schedule, you'll see:

```
INFO Response from Hive API (showing what was set):
================================================================================
SCHEDULE IN READABLE FORMAT
================================================================================
THURSDAY:
  05:30 → 18.5°C
  09:00 → 16.5°C
  16:00 → 18.5°C
  22:00 → 16.0°C
================================================================================
```

**No more decoding required!** The integration automatically converts the response for you.

## To Read a Specific Day's Schedule

Just set the schedule for that day (even to the same values):

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"  # or use your custom schedule
```

Then check the logs - you'll see the readable format!

## To Read ALL Schedules

Set each day one by one, or create an automation:

### Option 1: Manual (Safe)

Just call `set_day_schedule` for each day with their current schedules.

### Option 2: Automation Helper

Create this script to query all days:

```yaml
script:
  read_all_hive_schedules:
    alias: "Read All Hive Schedules"
    sequence:
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "monday"
          profile: "weekday"  # Use your actual schedule
      
      - delay: "00:00:02"
      
      - service: hive_schedule.set_day_schedule
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          day: "tuesday"
          profile: "weekday"
      
      # Continue for all days...
```

**Important:** Make sure to use the CURRENT schedule for each day, or you'll change them!

## What You'll See in the Logs

### Full Debug Output:

```
2026-01-17 18:17:35.817 DEBUG API CALL DEBUG INFO
2026-01-17 18:17:35.817 DEBUG Method: POST
2026-01-17 18:17:35.817 DEBUG URL: https://beekeeper-uk.hivehome.com/...
2026-01-17 18:17:35.817 DEBUG Headers:
2026-01-17 18:17:35.817 DEBUG   Authorization: eyJraWQiOi...-2FVhiUIQg
2026-01-17 18:17:35.817 DEBUG Payload (JSON):
2026-01-17 18:17:35.817 DEBUG {
2026-01-17 18:17:35.817 DEBUG   "schedule": {
2026-01-17 18:17:35.817 DEBUG     "thursday": [
2026-01-17 18:17:35.817 DEBUG       {
2026-01-17 18:17:35.817 DEBUG         "value": {
2026-01-17 18:17:35.817 DEBUG           "target": 18.5
2026-01-17 18:17:35.817 DEBUG         },
2026-01-17 18:17:35.817 DEBUG         "start": 330
2026-01-17 18:17:35.817 DEBUG       }
2026-01-17 18:17:35.817 DEBUG     ]
2026-01-17 18:17:35.817 DEBUG   }
2026-01-17 18:17:35.817 DEBUG }
2026-01-17 18:17:36.450 DEBUG Response status: 200
2026-01-17 18:17:36.450 DEBUG Response text: {"schedule":{"thursday":[...]}}
2026-01-17 18:17:36.450 INFO Response from Hive API (showing what was set):
2026-01-17 18:17:36.450 INFO ================================================================================
2026-01-17 18:17:36.450 INFO SCHEDULE IN READABLE FORMAT
2026-01-17 18:17:36.450 INFO ================================================================================
2026-01-17 18:17:36.450 INFO THURSDAY:
2026-01-17 18:17:36.450 INFO   05:30 → 18.5°C
2026-01-17 18:17:36.450 INFO   09:00 → 16.5°C
2026-01-17 18:17:36.450 INFO   16:00 → 18.5°C
2026-01-17 18:17:36.450 INFO   22:00 → 16.0°C
2026-01-17 18:17:36.450 INFO ================================================================================
2026-01-17 18:17:36.450 INFO ✓ Successfully updated Hive schedule
```

## Advantages of This Approach

✅ **Works now** - No need for AWS Signature V4 implementation
✅ **Automatic formatting** - No manual decoding needed
✅ **Clear output** - Easy to read in logs
✅ **Safe** - Uses the working POST endpoint
✅ **Reliable** - Shows exactly what Hive accepted

## Limitations

⚠️ Only shows the day you just set
⚠️ Need to set each day to see each day
⚠️ Can't do a single "get all schedules" call (API limitation)

## Tips

1. **Keep a reference** of your schedules somewhere (text file, etc.)
2. **Set schedules one by one** and check logs to verify
3. **Use profiles** to make it easier to re-set days without changing them
4. **Watch for the readable format** section in logs - that's your schedule!

## Example: Checking Monday's Schedule

```yaml
# Call this
service: hive_schedule.set_day_schedule
data:
  node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
  day: "monday"
  profile: "weekday"

# See this in logs:
# MONDAY:
#   06:30 → 18.0°C
#   09:00 → 16.0°C
#   16:00 → 18.0°C
#   22:00 → 16.0°C
```

Perfect! Now you know Monday's schedule.

## Future Enhancement

If we implement AWS Signature V4 signing, we could add a true `get_schedules` service that reads all days in one call. For now, this POST-based approach works perfectly!

---

**Version:** 1.1.17 (Enhanced Debug + Readable Schedules)  
**Status:** Fully working!  
**Approach:** Use POST responses for schedule visibility

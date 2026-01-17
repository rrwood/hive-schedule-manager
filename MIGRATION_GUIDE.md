# Migration Guide: v2.0 → v3.0

## Overview of Changes

Version 3.0 represents a significant upgrade to the Hive Schedule Manager integration with the following major changes:

### Key Improvements
1. **UI Configuration Flow** - No more editing `configuration.yaml`
2. **Persistent 2FA** - Enter 2FA code once during setup, not every restart
3. **Fixed Schedule Updates** - `set_day_schedule` now only updates the specified day
4. **Schedule Profiles** - Pre-defined schedules for common scenarios
5. **Removed Services** - Removed `set_heating_schedule` and `update_from_calendar`

## Migration Steps

### 1. Backup Your Current Configuration

Before upgrading, save your current `configuration.yaml` settings:

```yaml
# Save these somewhere - you'll need them during setup
hive_schedule:
  username: "your-email@example.com"
  password: "your-password"
```

### 2. Remove Old Configuration

Delete the `hive_schedule` section from your `configuration.yaml`:

```yaml
# REMOVE THIS:
hive_schedule:
  username: "your-email@example.com"
  password: "your-password"
  scan_interval: 30
```

### 3. Install v3.0

#### Via HACS
1. HACS will notify you of the update
2. Click "Update"
3. Restart Home Assistant

#### Manual Installation
1. Replace the `custom_components/hive_schedule` folder with the new version
2. Restart Home Assistant

### 4. Configure via UI

After restart:

1. Go to **Settings** → **Devices & Services**
2. You'll see a "Configure" button on the Hive Schedule Manager card (or it may show as unconfigured)
3. Click **"Configure"** or **"+ Add Integration"** and search for "Hive Schedule Manager"
4. Enter your Hive credentials:
   - Email: `your-email@example.com`
   - Password: `your-password`
5. When prompted, enter the 2FA code sent to your phone
6. Click **Submit**

Your credentials are now securely stored and you won't need to enter 2FA again unless you remove and re-add the integration.

### 5. Update Your Automations

#### Old `set_heating_schedule` Service (REMOVED)

**Before (v2.0):**
```yaml
service: hive_schedule.set_heating_schedule
data:
  node_id: "abc123"
  schedule:
    monday:
      - time: "06:30"
        temp: 18.0
      - time: "22:00"
        temp: 16.0
    tuesday:
      - time: "06:30"
        temp: 18.0
```

**After (v3.0):**
```yaml
# Set Monday
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "monday"
  schedule:
    - time: "06:30"
      temp: 18.0
    - time: "22:00"
      temp: 16.0

# Set Tuesday (separate service call)
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "tuesday"
  profile: "weekday"  # Or use custom schedule
```

#### Old `update_from_calendar` Service (REMOVED)

**Before (v2.0):**
```yaml
service: hive_schedule.update_from_calendar
data:
  node_id: "abc123"
  is_workday: true
  wake_time: "06:30"
```

**After (v3.0):**
```yaml
# Use conditional profile selection
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "{{ (now() + timedelta(days=1)).strftime('%A').lower() }}"
  profile: "{{ 'weekday' if is_state('binary_sensor.workday', 'on') else 'weekend' }}"
```

#### Updated `set_day_schedule` Service

**Before (v2.0):**
```yaml
# This would update ALL days with defaults except Monday
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "monday"
  schedule:
    - time: "06:30"
      temp: 18.0
```

**After (v3.0):**
```yaml
# This ONLY updates Monday, leaves other days unchanged
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "monday"
  schedule:
    - time: "06:30"
      temp: 18.0

# Or use a profile
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "monday"
  profile: "weekday"
```

### 6. Verify MFA Service Removal

The `verify_mfa_code` service has been removed. If you have any automations or scripts using it, remove those calls:

```yaml
# REMOVE THIS - no longer needed
service: hive_schedule.verify_mfa_code
data:
  code: "123456"
```

## New Features to Explore

### Schedule Profiles

Instead of defining schedules in your automations, use built-in profiles:

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "abc123"
  day: "monday"
  profile: "weekday"  # Options: weekday, weekend, holiday, wfh, away, etc.
```

Available profiles:
- `weekday` - Standard workday
- `weekend` - Relaxed weekend
- `holiday` - Holiday schedule
- `weekday_early` - Early start (5:30 AM)
- `weekday_late` - Late return (6:30 PM)
- `wfh` - Work from home
- `away` - Frost protection only
- `all_day_comfort` - Constant temperature

### Customizing Profiles

Edit `custom_components/hive_schedule/schedule_profiles.py`:

```python
PROFILES = {
    "my_profile": [
        {"time": "06:00", "temp": 19.0},
        {"time": "22:00", "temp": 17.0},
    ],
}
```

## Common Issues

### "Integration not found" after upgrade

**Solution:** Restart Home Assistant twice. The first restart loads the new code, the second ensures all services are registered.

### Can't find the integration in UI

**Solution:** 
1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Hive"
4. Select "Hive Schedule Manager"

### 2FA keeps being requested

This shouldn't happen in v3.0. If it does:
1. Remove the integration completely
2. Restart Home Assistant
3. Re-add the integration
4. Enter 2FA code when prompted

### Node ID errors

Your node ID hasn't changed, but double-check it:
1. Developer Tools → States
2. Find `climate.heating` (or your Hive climate entity)
3. Check the `node_id` attribute

## Rolling Back (If Needed)

If you need to roll back to v2.0:

1. Remove the integration via UI (Settings → Devices & Services)
2. Delete `custom_components/hive_schedule`
3. Install v2.0 files
4. Restore your `configuration.yaml` settings
5. Restart Home Assistant
6. Call the `verify_mfa_code` service with your 2FA code

## Support

If you encounter issues during migration:

1. Check Home Assistant logs: Settings → System → Logs
2. Enable debug logging:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.hive_schedule: debug
   ```
3. Create an issue on GitHub with logs attached

## Questions?

Open an issue on GitHub: https://github.com/rrwood/hive-schedule-manager/issues

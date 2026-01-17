# Quick Installation Guide

## Installing the Enhanced Debug Version

### Option 1: Replace Files in Existing Installation

If you already have Hive Schedule Manager installed via HACS:

1. Navigate to your Home Assistant `custom_components` directory:
   ```
   /config/custom_components/hive_schedule/
   ```

2. **Backup your current files** (important!):
   ```bash
   cp __init__.py __init__.py.backup
   cp services.yaml services.yaml.backup
   ```

3. Replace these files with the enhanced versions:
   - `__init__.py` (contains all the debug enhancements)
   - `services.yaml` (adds get_schedule service documentation)

4. Restart Home Assistant

### Option 2: Fresh Installation

1. Copy the entire `custom_components/hive_schedule/` directory to:
   ```
   /config/custom_components/hive_schedule/
   ```

2. Restart Home Assistant

3. Set up the integration via UI (Settings > Integrations > Add Integration)

### Enable Debug Logging

Add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.hive_schedule: debug
```

Then restart Home Assistant or reload logger:
```yaml
service: logger.set_level
data:
  custom_components.hive_schedule: debug
```

## Verifying Installation

### Check Version

Look for this in your logs after restart:
```
Setting up Hive Schedule Manager v1.1.16 (Enhanced Debug)
Available services: set_day_schedule, get_schedule
```

### Test the New Service

Go to Developer Tools > Services and try:

```yaml
service: hive_schedule.get_schedule
data:
  node_id: "YOUR-NODE-ID-HERE"
```

You should see detailed logs including:
- API call debug information
- Current schedule in readable format
- Success confirmation

### Test Debug Logging

Run any existing service call and check your logs for:
```
================================================================================
API CALL DEBUG INFO
================================================================================
```

## What If Something Goes Wrong?

### Restore Original Files

If you need to revert:

```bash
cd /config/custom_components/hive_schedule/
cp __init__.py.backup __init__.py
cp services.yaml.backup services.yaml
```

Then restart Home Assistant.

### Get Help

When asking for help, please include:
1. Your Home Assistant version
2. Relevant log entries (with tokens redacted)
3. The exact service call you're trying
4. What you expected vs what happened

## Next Steps

Once installed:

1. **Read the documentation**: Check `DEBUG_ENHANCEMENTS.md` for full feature details
2. **Review the changes**: See `CHANGES_SUMMARY.md` for technical details
3. **Set up logging**: Enable debug logs to see all API calls
4. **Test thoroughly**: Try both services with your node ID

## File Locations

After installation, you should have:

```
/config/custom_components/hive_schedule/
├── __init__.py          (Enhanced with debug features)
├── services.yaml        (Updated with get_schedule)
├── config_flow.py       (Unchanged)
├── const.py             (Unchanged)
├── schedule_profiles.py (Unchanged)
├── manifest.json        (Unchanged)
├── strings.json         (Unchanged)
└── translations/        (Unchanged)
    └── en.json
```

## Troubleshooting

### Debug Logs Not Showing

Make sure you have:
1. Added the logger configuration to `configuration.yaml`
2. Restarted Home Assistant or reloaded logger config
3. Actually triggered a service call (logs appear on API calls, not on startup)

### Service Not Available

If you don't see `hive_schedule.get_schedule`:
1. Check Home Assistant logs for errors during setup
2. Verify files were copied correctly
3. Restart Home Assistant
4. Check Developer Tools > Services for the service

### Authentication Issues

If you get 401 errors:
1. Check if token refresh is working (look for "Successfully refreshed authentication token")
2. Try re-authenticating through the integration setup
3. Check the debug logs for detailed error information

---

**Need More Help?**
- Full documentation: `DEBUG_ENHANCEMENTS.md`
- Technical details: `CHANGES_SUMMARY.md`

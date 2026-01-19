# Quick Installation Guide

## Installation Steps

1. **Copy the integration files:**
   ```
   Copy custom_components/hive_schedule/ to /config/custom_components/hive_schedule/
   ```

2. **Restart Home Assistant**

3. **Add the integration:**
   - Go to Settings → Devices & Services
   - Click "+ ADD INTEGRATION"
   - Search for "Hive Schedule Manager"
   - Enter your Hive credentials
   - Complete MFA if prompted

4. **Find your node ID:**
   - Log into https://my.hivehome.com
   - Click your heating device
   - Copy the last part of the URL (e.g., `d2708e98-f22f-483e-b590-9ddbd642a3b7`)

5. **Optional: Customize profiles:**
   - The file `hive_schedule_profiles.yaml` will be created automatically in `/config/`
   - Edit it to customize your schedules
   - No restart needed - changes take effect on next service call!

## Files Included

```
hive_schedule_v1.1.17_production/
├── custom_components/
│   └── hive_schedule/
│       ├── __init__.py           # Main integration code
│       ├── const.py               # Constants and configuration
│       ├── services.yaml          # Service definitions
│       └── manifest.json          # Integration metadata
├── hive_schedule_profiles.yaml    # Example profiles (copy to /config/)
└── README.md                      # Full documentation
```

## First Use

After installation, try this service call:

```yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "YOUR-NODE-ID-HERE"
  day: "monday"
  profile: "weekday"
```

Check your Home Assistant logs to see the confirmation!

## Need Help?

See README.md for:
- Complete documentation
- Automation examples
- Troubleshooting guide
- Advanced usage tips

---

**Version:** 1.1.17 Production  
**Status:** Stable and tested

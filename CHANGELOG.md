# Changelog - v1.1.17 Production

## What's New

### ✨ YAML-Based Schedule Profiles
- Profiles are now stored in `/config/hive_schedule_profiles.yaml`
- Easy to edit without touching Python code
- Automatic profile file creation on first run
- Profiles reload automatically (no restart needed after editing)

### ✨ Improved User Experience
- Cleaner code structure
- Better error messages
- More readable log output
- Comprehensive documentation

### ✨ Production Ready
- Stable POST-based approach
- No experimental features
- Well-tested functionality
- Clear limitations documented

## Changes from Previous Versions

### Removed
- ❌ GET request attempts (not supported by Hive API)
- ❌ AWS SigV4 code (not needed)
- ❌ Hardcoded profiles in Python

### Added
- ✅ YAML profile loading
- ✅ Default profile file creation
- ✅ Better documentation
- ✅ Example profiles file
- ✅ Installation guide

### Improved
- ✅ Code organization
- ✅ Error handling
- ✅ Log messages
- ✅ User guidance

## Migration from Earlier Versions

If you're upgrading from v1.1.16 or earlier:

1. **No breaking changes** - service calls work the same way
2. **New feature**: Profiles are now in YAML
3. **Action needed**: None! Just upgrade and enjoy YAML profiles

### Optional: Convert Your Custom Profiles

If you had custom profiles in the old `schedule_profiles.py`:

1. The integration will create `hive_schedule_profiles.yaml` automatically
2. Edit this file to add your custom profiles
3. Delete the old `schedule_profiles.py` (no longer used)

## Known Limitations

### What Works ✅
- Setting heating schedules for any day
- Using predefined and custom profiles
- Automatic token management
- MFA support

### What Doesn't Work ❌
- **Reading current schedules** - Hive API restricts GET requests

This is an intentional API restriction by Hive, not a bug in the integration.

## Technical Details

### Dependencies
- `pycognito==2024.5.1` - AWS Cognito authentication
- `requests==2.32.3` - HTTP requests
- `PyYAML==6.0.1` - YAML parsing (**NEW**)

### Files Changed
- `__init__.py` - Complete rewrite with YAML support
- `const.py` - No changes
- `services.yaml` - No changes
- `manifest.json` - Updated version and dependencies

### Files Removed
- `schedule_profiles.py` - Replaced by YAML file

### Files Added
- `hive_schedule_profiles.yaml` - Example profiles file
- `README.md` - Comprehensive documentation
- `INSTALL.md` - Quick start guide
- `CHANGELOG.md` - This file

## Testing

This version has been tested with:
- ✅ Home Assistant 2024.1+
- ✅ Python 3.11+
- ✅ Standard Hive heating systems
- ✅ MFA authentication
- ✅ Multiple profiles
- ✅ Custom schedules

## Support

Issues? Questions?

1. Check README.md for troubleshooting
2. Enable debug logging to see detailed info
3. Check that `hive_schedule_profiles.yaml` exists in `/config/`
4. Verify your node ID is correct (from Hive website URL)

---

**Version:** 1.1.17 Production  
**Release Date:** January 2026  
**Status:** Stable

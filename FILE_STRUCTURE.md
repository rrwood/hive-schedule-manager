# Hive Schedule Manager v3.0 - File Structure

## Directory Structure

```
custom_components/hive_schedule/
├── __init__.py                 # Main integration setup and service handlers
├── config_flow.py             # UI configuration flow with 2FA
├── const.py                   # Constants and configuration
├── schedule_profiles.py       # Pre-defined heating schedule templates
├── manifest.json              # Integration metadata
├── services.yaml              # Service definitions
├── strings.json               # UI strings (English)
└── translations/
    └── en.json                # English translations
```

## File Descriptions

### `__init__.py` (Main Integration File)
- **Purpose**: Core integration logic
- **Key Components**:
  - `HiveAuth` class: Handles Cognito authentication
  - `HiveScheduleAPI` class: API client for Hive schedule operations
  - `async_setup_entry()`: Sets up the integration from config entry
  - Service handler: `handle_set_day()` for updating schedules
- **Key Changes from v2.0**:
  - Uses config entries instead of YAML configuration
  - Simplified authentication (no MFA service needed)
  - `set_day_schedule` now retrieves current schedule and only updates specified day
  - Removed `set_heating_schedule` and `update_from_calendar` services

### `config_flow.py` (UI Configuration)
- **Purpose**: Handles UI-based setup with username, password, and 2FA
- **Key Components**:
  - `HiveScheduleConfigFlow` class: Config flow handler
  - `async_step_user()`: Initial username/password entry
  - `async_step_mfa()`: 2FA code verification
  - `validate_auth()`: Authentication validation
- **Features**:
  - Persistent credentials (stored in config entry)
  - One-time 2FA during setup
  - Proper error handling for auth failures

### `const.py` (Constants)
- **Purpose**: Centralized constant definitions
- **Contents**:
  - Domain name
  - AWS Cognito configuration
  - Service names
  - Attribute names
  - Profile names
  - API URL

### `schedule_profiles.py` (Schedule Templates)
- **Purpose**: Pre-defined heating schedule templates
- **Key Components**:
  - `PROFILES` dictionary: All available schedule profiles
  - `get_profile()`: Retrieve a profile by name
  - `get_available_profiles()`: List all profile names
  - `validate_custom_schedule()`: Validate custom schedule format
- **Available Profiles**:
  - weekday: Standard workday schedule
  - weekend: Relaxed weekend schedule
  - holiday: Holiday schedule
  - weekday_early: Early start workday
  - weekday_late: Late return workday
  - wfh: Work from home schedule
  - away: Minimal heating (frost protection)
  - all_day_comfort: Constant comfortable temperature

### `manifest.json` (Integration Metadata)
- **Purpose**: Integration metadata for Home Assistant
- **Key Settings**:
  - `config_flow: true` - Enables UI configuration
  - Version: 3.0.0
  - Requirements: requests, pycognito

### `services.yaml` (Service Definitions)
- **Purpose**: Defines available services and their parameters
- **Services**:
  - `set_day_schedule`: Update a single day's schedule
  - `refresh_token`: Manually refresh authentication token

### `strings.json` & `translations/en.json` (UI Strings)
- **Purpose**: User-facing text for UI
- **Contents**:
  - Config flow step titles and descriptions
  - Error messages
  - Service descriptions

## Key Differences from v2.0

| Aspect | v2.0 | v3.0 |
|--------|------|------|
| Configuration | `configuration.yaml` | UI Config Flow |
| 2FA | Required each restart | One-time during setup |
| Credentials | In config file | Stored securely in config entry |
| `set_day_schedule` | Updated all days | Updates only specified day |
| Services | 4 services | 2 services (removed unused) |
| Profiles | Hardcoded | Defined in `schedule_profiles.py` |
| Files | 1 main file | 4 core files + translations |

## Installation to HACS

To install via HACS:

1. Ensure your GitHub repository has this structure:
   ```
   repository-root/
   └── custom_components/
       └── hive_schedule/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── schedule_profiles.py
           ├── manifest.json
           ├── services.yaml
           ├── strings.json
           └── translations/
               └── en.json
   ```

2. Tag a release (e.g., `v3.0.0`)

3. Users install via:
   - HACS → Integrations → Custom repositories
   - Add your repository URL
   - Install "Hive Schedule Manager"

## Editing in VS Code

Recommended VS Code extensions:
- Python (Microsoft)
- Home Assistant Config Helper
- YAML

To edit and test:
1. Clone repository
2. Edit files in `custom_components/hive_schedule/`
3. Commit and push to GitHub
4. Either:
   - Tag a new release for HACS users to update
   - Or manually copy to Home Assistant's `custom_components/` for testing

## File Dependencies

```
__init__.py
├── imports const.py
├── imports schedule_profiles.py
└── uses config_flow.py (indirectly via config entries)

config_flow.py
└── imports const.py

schedule_profiles.py
└── (no dependencies)

const.py
└── (no dependencies)
```

## Customization Points

### Adding New Schedule Profiles
Edit `schedule_profiles.py`:
```python
PROFILES["my_new_profile"] = [
    {"time": "06:00", "temp": 19.0},
    {"time": "22:00", "temp": 16.0},
]
```

### Changing Default Token Refresh Interval
Edit `__init__.py`:
```python
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)  # Change this
```

### Adding New Services
1. Add service definition to `services.yaml`
2. Add handler in `__init__.py` `async_setup_entry()`
3. Register with `hass.services.async_register()`
4. Update `strings.json` with service description

### Supporting Additional Languages
1. Create `translations/XX.json` (e.g., `fr.json` for French)
2. Copy structure from `en.json`
3. Translate all strings

## Testing Locally

To test without HACS:

1. Copy entire `custom_components/hive_schedule/` to your Home Assistant:
   ```bash
   scp -r custom_components/hive_schedule/ homeassistant@your-ha-ip:/config/custom_components/
   ```

2. Restart Home Assistant

3. Go to Settings → Devices & Services → Add Integration

4. Search for "Hive Schedule Manager"

5. Check logs for errors:
   ```yaml
   # configuration.yaml
   logger:
     default: info
     logs:
       custom_components.hive_schedule: debug
   ```

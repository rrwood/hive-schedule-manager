# Hive Schedule Manager v2.0 - Standalone Version

## 🎉 Complete Rewrite - Now Independent!

This version **does NOT depend** on the Hive integration. It handles its own authentication directly with the Hive API using AWS Cognito.

## Benefits

✅ **No token expiry issues** - Automatically refreshes tokens every 30 minutes  
✅ **Independent operation** - Doesn't rely on Hive integration's internal state  
✅ **Reliable authentication** - Direct control over the auth lifecycle  
✅ **Auto-retry** - Automatically retries with fresh token if auth fails  

## Installation

### Step 1: Install Files

Copy these files to `/config/custom_components/hive_schedule/`:
- `__init__.py` (v2.0 - NEW standalone version)
- `manifest.json` (v2.0 - updated dependencies)
- `services.yaml`
- `strings.json`

### Step 2: Add Configuration

Add this to your `/config/configuration.yaml`:

```yaml
hive_schedule:
  username: "your-hive-email@example.com"
  password: "your-hive-password"
  scan_interval: 00:30:00  # Optional: token refresh interval (default: 30 minutes)
```

**Important**: Use the same username and password you use to log into the Hive app!

### Step 3: Restart Home Assistant

After adding the configuration, restart Home Assistant.

## What to Expect

After restart, check the logs for:

```
INFO [custom_components.hive_schedule] Setting up Hive Schedule Manager (Standalone v2.0)
INFO [custom_components.hive_schedule] ✓ Successfully authenticated with Hive (token expires in ~55 minutes)
INFO [custom_components.hive_schedule] ✓ Hive Schedule Manager setup complete (Standalone v2.0)
```

## Testing

### Find Your Node ID

You'll still need your heating node ID. The easiest way is to check the Hive app or use the node ID we found earlier: `d2708e98-f22f-483e-b590-9ddbd642a3b7`

### Test Service Call

Go to **Developer Tools** → **Services**

**Service:** `hive_schedule.set_day_schedule`

**Service Data:**
```yaml
node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
day: "friday"
schedule:
  - time: "07:00"
    temp: 19.0
  - time: "09:00"
    temp: 16.0
  - time: "17:00"
    temp: 20.0
  - time: "22:00"
    temp: 16.0
```

Click "Call Service"

### Expected Result

In logs:
```
INFO [custom_components.hive_schedule] ✓ Successfully updated Hive schedule for node d2708e98-f22f-483e-b590-9ddbd642a3b7
```

In Hive app:
- Check Friday's schedule - it should be updated!

## Available Services

### 1. `hive_schedule.set_day_schedule`
Update a single day's heating schedule

```yaml
node_id: "your-node-id"
day: "monday"
schedule:
  - time: "06:30"
    temp: 18.0
  - time: "22:00"
    temp: 16.0
```

### 2. `hive_schedule.set_heating_schedule`
Update the complete weekly schedule

```yaml
node_id: "your-node-id"
schedule:
  monday:
    - time: "06:30"
      temp: 18.0
    - time: "22:00"
      temp: 16.0
  tuesday:
    - time: "06:30"
      temp: 18.0
  # ... other days
```

### 3. `hive_schedule.update_from_calendar`
Update tomorrow's schedule based on calendar

```yaml
node_id: "your-node-id"
is_workday: true
wake_time: "06:30"  # optional
```

### 4. `hive_schedule.refresh_token`
Manually refresh authentication token (usually not needed)

No parameters needed - just call it.

## Token Management

- Tokens are **automatically refreshed** every 30 minutes (configurable)
- If a token expires mid-request, it **automatically retries** with a fresh token
- No more "token expired" errors!

## Troubleshooting

### "Initial authentication failed"
- Check your username and password in `configuration.yaml`
- Make sure you're using your Hive app credentials
- Check that your Hive account is active

### "Invalid node ID" (404 error)
- The node ID is wrong
- Try the one we found: `d2708e98-f22f-483e-b590-9ddbd642a3b7`
- Or check your Hive devices in the app

### Integration doesn't load
- Check `/config/configuration.yaml` for syntax errors
- Make sure username and password are quoted strings
- Check logs for error messages

## Configuration Options

```yaml
hive_schedule:
  username: "required"              # Your Hive email
  password: "required"              # Your Hive password
  scan_interval: "00:30:00"         # Optional: How often to refresh tokens
                                    # Format: HH:MM:SS
                                    # Default: 30 minutes
                                    # Minimum: 5 minutes recommended
```

## Example Automation

Update heating schedule based on calendar events:

```yaml
automation:
  - alias: "Update heating from calendar"
    trigger:
      - platform: time
        at: "22:00:00"  # 10 PM each evening
    action:
      - service: hive_schedule.update_from_calendar
        data:
          node_id: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
          is_workday: "{{ is_state('binary_sensor.workday_sensor', 'on') }}"
```

## Security Note

Your Hive credentials are stored in `configuration.yaml`. Make sure:
- Your Home Assistant instance is secure
- You use secrets if sharing your config
- Your `configuration.yaml` is not publicly accessible

You can use secrets like this:

```yaml
# secrets.yaml
hive_username: "your-email@example.com"
hive_password: "your-password"

# configuration.yaml
hive_schedule:
  username: !secret hive_username
  password: !secret hive_password
```

## What Changed from v1.x

| Feature | v1.x (Dependent) | v2.0 (Standalone) |
|---------|------------------|-------------------|
| Depends on Hive integration | ✅ Required | ❌ Independent |
| Token expiry issues | ❌ Yes | ✅ No |
| Configuration needed | ❌ No | ✅ Yes (credentials) |
| Token refresh | ❌ Manual/unreliable | ✅ Automatic |
| Auto-retry on 401 | ❌ No | ✅ Yes |

## Support

If you have issues:
1. Check logs for error messages
2. Verify your credentials work in the Hive app
3. Try the `refresh_token` service
4. Check that your node ID is correct

This version should be rock-solid! 🎉
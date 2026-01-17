# Summary of Changes - Hive Schedule Manager v1.1.16

## Key Enhancements

### 1. Enhanced API Call Debugging (`_log_api_call` method)

**Added to HiveScheduleAPI class (lines ~210-228):**

```python
def _log_api_call(self, method: str, url: str, headers: dict, payload: dict | None = None) -> None:
    """Log detailed API call information for debugging."""
    _LOGGER.debug("=" * 80)
    _LOGGER.debug("API CALL DEBUG INFO")
    _LOGGER.debug("=" * 80)
    _LOGGER.debug("Method: %s", method)
    _LOGGER.debug("URL: %s", url)
    _LOGGER.debug("-" * 80)
    _LOGGER.debug("Headers:")
    # Sanitize authorization header for logging
    safe_headers = headers.copy()
    if "Authorization" in safe_headers:
        token = safe_headers["Authorization"]
        if len(token) > 20:
            safe_headers["Authorization"] = f"{token[:10]}...{token[-10:]}"
    for key, value in safe_headers.items():
        _LOGGER.debug("  %s: %s", key, value)
    _LOGGER.debug("-" * 80)
    if payload:
        _LOGGER.debug("Payload (JSON):")
        _LOGGER.debug("%s", json.dumps(payload, indent=2))
    _LOGGER.debug("=" * 80)
```

**Features:**
- Logs HTTP method, URL, headers, and payload
- Safely truncates authorization tokens for security
- Pretty-prints JSON payloads
- Clear visual separators for readability

### 2. Read Current Schedule Capability

**New `get_current_schedule` method (lines ~230-290):**

```python
def get_current_schedule(self, node_id: str) -> dict[str, Any] | None:
    """Retrieve the current schedule from Hive for a specific node."""
```

**Features:**
- Retrieves full schedule from Hive API
- Converts schedule to human-readable format
- Logs both raw and readable versions
- Handles authentication and errors
- Auto-retries on 401 errors after token refresh

**Helper method added:**
```python
@staticmethod
def minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to time string."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"
```

### 3. Read-Before-Write in Schedule Updates

**Modified `update_schedule` method (lines ~292-370):**

Added new parameter `read_before_write: bool = True`:

```python
def update_schedule(self, node_id: str, schedule_data: dict[str, Any], 
                   read_before_write: bool = True) -> bool:
    """Send schedule update to Hive using beekeeper-uk API."""
    
    # Read current schedule before writing if requested
    if read_before_write:
        _LOGGER.info("Reading current schedule before writing...")
        try:
            current_schedule = self.get_current_schedule(node_id)
            if current_schedule and "schedule" in current_schedule:
                _LOGGER.info("Current schedule retrieved successfully")
                _LOGGER.debug("Current full schedule: %s", 
                            json.dumps(current_schedule.get("schedule"), indent=2))
        except Exception as e:
            _LOGGER.warning("Failed to read current schedule before writing: %s", e)
            _LOGGER.info("Continuing with update anyway...")
```

**All API calls now logged:**
- Before GET requests: `self._log_api_call("GET", url, self.session.headers)`
- Before POST requests: `self._log_api_call("POST", url, self.session.headers, schedule_data)`

### 4. New `get_schedule` Service

**Added service handler (lines ~440-460):**

```python
async def handle_get_schedule(call: ServiceCall) -> None:
    """Handle get_schedule service call - retrieves current schedule."""
    node_id = call.data[ATTR_NODE_ID]
    
    _LOGGER.info("Getting current schedule for node %s", node_id)
    
    try:
        schedule_data = await hass.async_add_executor_job(
            api.get_current_schedule, node_id
        )
        
        if schedule_data:
            _LOGGER.info("Successfully retrieved schedule for node %s", node_id)
            # Fire an event with the schedule data
            hass.bus.async_fire(
                f"{DOMAIN}_schedule_retrieved",
                {
                    "node_id": node_id,
                    "schedule": schedule_data.get("schedule"),
                }
            )
```

**Registered service:**
```python
hass.services.async_register(
    DOMAIN,
    "get_schedule",
    handle_get_schedule,
    schema=GET_SCHEDULE_SCHEMA
)
```

### 5. Enhanced Logging Throughout

**Additional logging added:**
- Response status codes: `_LOGGER.debug("Response status: %s", response.status_code)`
- Response data: `_LOGGER.debug("Response data: %s", json.dumps(data, indent=2))`
- Current schedule in readable format with proper indentation
- More informative success/failure messages

### 6. Event System Integration

When `get_schedule` is called, it fires an event:
```python
hass.bus.async_fire(
    f"{DOMAIN}_schedule_retrieved",
    {
        "node_id": node_id,
        "schedule": schedule_data.get("schedule"),
    }
)
```

This allows automations to react to schedule retrieval.

## Files Modified

1. **`__init__.py`**
   - Added `_log_api_call` method
   - Added `get_current_schedule` method
   - Added `minutes_to_time` static method
   - Modified `update_schedule` to include read-before-write
   - Added `handle_get_schedule` service handler
   - Enhanced logging throughout
   - Version updated to 1.1.16 (Enhanced Debug)

2. **`services.yaml`** (new file)
   - Added documentation for `get_schedule` service
   - Kept existing service documentation

## Backward Compatibility

✅ **100% backward compatible**
- All existing services work unchanged
- Default behavior of `set_day_schedule` is identical
- New features are additive only
- No breaking changes to configuration

## Testing Checklist

When testing, verify:

1. ✅ Debug logs appear when `logger` is configured
2. ✅ API calls are fully logged with sanitized tokens
3. ✅ `get_schedule` service retrieves and logs current schedule
4. ✅ `set_day_schedule` reads current schedule before writing
5. ✅ `hive_schedule_schedule_retrieved` event is fired
6. ✅ Existing functionality continues to work
7. ✅ Error handling and retries still work correctly

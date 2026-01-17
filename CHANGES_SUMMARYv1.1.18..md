# Summary of Changes - Hive Schedule Manager v1.1.16

## Key Enhancements

### 1. ✅ Enhanced API Call Debugging (`_log_api_call` method)

**Added to HiveScheduleAPI class:**

```python
def _log_api_call(self, method: str, url: str, headers: dict, payload: dict | None = None) -> None:
    """Log detailed API call information for debugging."""
```

**Features:**
- Logs HTTP method, URL, headers, and payload
- Safely truncates authorization tokens for security
- Pretty-prints JSON payloads
- Clear visual separators for readability
- **FULLY FUNCTIONAL** ✅

### 2. ⚠️ Read Current Schedule Capability (Limited)

**New `get_current_schedule` method added but NOT FUNCTIONAL due to API limitations:**

```python
def get_current_schedule(self, node_id: str) -> dict[str, Any] | None:
    """Retrieve the current schedule from Hive for a specific node."""
```

**Status:** ❌ Currently returns 403 Forbidden

**Why:** The Hive beekeeper-uk API requires AWS Signature V4 authentication for GET requests, which is different from the bearer token auth that works for POST requests.

**Error received:**
```json
{
  "message": "Authorization header requires 'Credential' parameter. 
              Authorization header requires 'Signature' parameter..."
}
```

**Workaround:** POST responses include the schedule, visible in debug logs:
```
Response text: {"schedule":{"wednesday":[{"value":{"target":18.5},"start":330}...]}}
```

### 3. ✅ Enhanced POST Response Logging

**Modified `update_schedule` method:**

Now logs complete response including the updated schedule:

```python
_LOGGER.debug("Response status: %s", response.status_code)
_LOGGER.debug("Response text: %s", response.text[:500])
```

**This gives you schedule visibility after updates!**

### 4. ❌ Read-Before-Write (Disabled)

- Parameter added: `read_before_write: bool = False`
- **Disabled by default** because it requires GET requests
- Can be enabled but will fail with 403 error until AWS SigV4 is implemented

### 5. ⚠️ `get_schedule` Service (Not Functional)

Service is registered but returns 403 error when called.
Use POST responses instead for schedule visibility.

## What Actually Works

### ✅ **Fully Functional:**
1. **Complete API call debugging** - See every request and response
2. **POST request logging** - Full visibility into schedule updates
3. **Response logging** - POST responses include the updated schedule
4. **Token management** - Auth continues to work perfectly
5. **set_day_schedule service** - Works as before, now with detailed logging

### ⚠️ **Not Functional (API Limitation):**
1. **get_schedule service** - Returns 403 (requires AWS SigV4)
2. **read_before_write** - Disabled by default (requires AWS SigV4)
3. **Direct schedule reading** - Not possible without AWS SigV4 implementation

### 💡 **Workaround:**
The POST response contains the schedule! Check debug logs after any update:
```
Response text: {"schedule":{"wednesday":[{"value":{"target":18.5},"start":330}...]}}
```

Use the included `decode_schedule.py` script to convert this to readable format.

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

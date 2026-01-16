"""Enhanced Diagnostics for Hive Schedule Manager - Find the auth token location."""
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def inspect_hive_integration(hass) -> None:
    """Comprehensive inspection of Hive integration structure."""
    _LOGGER.info("=" * 80)
    _LOGGER.info("COMPREHENSIVE HIVE INTEGRATION INSPECTION")
    _LOGGER.info("=" * 80)
    
    # Section 1: Config Entries
    _LOGGER.info("")
    _LOGGER.info("SECTION 1: CONFIG ENTRIES")
    _LOGGER.info("-" * 80)
    
    hive_entries = hass.config_entries.async_entries("hive")
    _LOGGER.info("Number of Hive config entries: %d", len(hive_entries))
    
    for idx, entry in enumerate(hive_entries):
        _LOGGER.info("")
        _LOGGER.info("  Entry #%d:", idx + 1)
        _LOGGER.info("    Entry ID: %s", entry.entry_id)
        _LOGGER.info("    Title: %s", entry.title)
        _LOGGER.info("    State: %s", entry.state)
        _LOGGER.info("    Domain: %s", entry.domain)
        
        # Check data
        if entry.data:
            _LOGGER.info("    Data keys: %s", list(entry.data.keys()))
            for key in entry.data.keys():
                if 'token' in key.lower() or 'auth' in key.lower():
                    _LOGGER.info("      → %s: %s", key, type(entry.data[key]))
        
        # Check runtime_data
        _LOGGER.info("    Has runtime_data: %s", hasattr(entry, 'runtime_data') and entry.runtime_data is not None)
        
        if hasattr(entry, 'runtime_data') and entry.runtime_data:
            runtime = entry.runtime_data
            _LOGGER.info("    Runtime data type: %s", type(runtime).__name__)
            _LOGGER.info("    Runtime module: %s", type(runtime).__module__)
            
            # Get all attributes
            if hasattr(runtime, '__dict__'):
                all_attrs = vars(runtime)
                public_attrs = {k: v for k, v in all_attrs.items() if not k.startswith('_')}
                private_attrs = {k: v for k, v in all_attrs.items() if k.startswith('_')}
                
                _LOGGER.info("    Runtime public attributes:")
                for key, value in public_attrs.items():
                    _LOGGER.info("      → %s: %s", key, type(value).__name__)
                
                if private_attrs:
                    _LOGGER.info("    Runtime private attributes:")
                    for key in private_attrs.keys():
                        _LOGGER.info("      → %s: %s", key, type(private_attrs[key]).__name__)
                
                # Deep dive into promising attributes
                _inspect_object_for_token(runtime, "runtime_data", depth=0, max_depth=3)
    
    # Section 2: hass.data
    _LOGGER.info("")
    _LOGGER.info("SECTION 2: HASS.DATA")
    _LOGGER.info("-" * 80)
    
    # Check for 'hive' key
    if "hive" in hass.data:
        _LOGGER.info("✓ 'hive' found in hass.data")
        _inspect_object_for_token(hass.data["hive"], "hass.data['hive']", depth=0, max_depth=3)
    else:
        _LOGGER.info("✗ 'hive' NOT in hass.data")
    
    # Check for entry IDs
    for entry in hive_entries:
        entry_id = entry.entry_id
        if entry_id in hass.data:
            _LOGGER.info("✓ Entry ID '%s' found in hass.data", entry_id)
            _inspect_object_for_token(hass.data[entry_id], f"hass.data['{entry_id}']", depth=0, max_depth=3)
    
    # Section 3: Entity Registry
    _LOGGER.info("")
    _LOGGER.info("SECTION 3: HIVE ENTITIES")
    _LOGGER.info("-" * 80)
    
    # Look for Hive climate entities
    for state in hass.states.async_all():
        if state.entity_id.startswith(("climate.", "sensor.", "binary_sensor.")) and "hive" in state.entity_id.lower():
            _LOGGER.info("  Entity: %s", state.entity_id)
            _LOGGER.info("    State: %s", state.state)
            if state.attributes:
                interesting_attrs = {k: v for k, v in state.attributes.items() 
                                   if 'id' in k.lower() or 'node' in k.lower()}
                if interesting_attrs:
                    _LOGGER.info("    Interesting attributes: %s", interesting_attrs)
    
    # Section 4: Integration Details
    _LOGGER.info("")
    _LOGGER.info("SECTION 4: INTEGRATION DETAILS")
    _LOGGER.info("-" * 80)
    
    try:
        from homeassistant.loader import async_get_integration
        import asyncio
        
        async def get_integration_info():
            integration = await async_get_integration(hass, "hive")
            _LOGGER.info("  Integration name: %s", integration.name)
            _LOGGER.info("  Integration domain: %s", integration.domain)
            _LOGGER.info("  Integration version: %s", getattr(integration, 'version', 'unknown'))
            _LOGGER.info("  Integration path: %s", integration.file_path)
        
        # Run in event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(get_integration_info())
        else:
            loop.run_until_complete(get_integration_info())
            
    except Exception as e:
        _LOGGER.debug("Could not get integration details: %s", e)
    
    _LOGGER.info("")
    _LOGGER.info("=" * 80)
    _LOGGER.info("END OF INSPECTION")
    _LOGGER.info("=" * 80)


def _inspect_object_for_token(obj: Any, path: str, depth: int, max_depth: int) -> None:
    """Recursively inspect object for authentication tokens."""
    if depth >= max_depth:
        return
    
    indent = "    " * (depth + 1)
    
    if not hasattr(obj, '__dict__'):
        return
    
    attrs = vars(obj)
    
    # Look for session, api, auth attributes
    for attr_name in ['session', 'api', 'hive', 'client', '_session', '_api', '_hive', '_client']:
        if attr_name in attrs:
            attr_value = attrs[attr_name]
            _LOGGER.info("%s%s.%s:", indent, path, attr_name)
            _LOGGER.info("%s  Type: %s", indent, type(attr_value).__name__)
            _LOGGER.info("%s  Module: %s", indent, type(attr_value).__module__)
            
            # Check for auth
            if hasattr(attr_value, 'auth') or hasattr(attr_value, '_auth'):
                auth_attr = 'auth' if hasattr(attr_value, 'auth') else '_auth'
                auth_obj = getattr(attr_value, auth_attr)
                _LOGGER.info("%s  %s.%s.%s:", indent, path, attr_name, auth_attr)
                _LOGGER.info("%s    Type: %s", indent, type(auth_obj).__name__)
                
                # Check for token attributes
                for token_attr in ['tokenData', 'token', 'accessToken', '_token', 'access_token', 'id_token']:
                    if hasattr(auth_obj, token_attr):
                        token_value = getattr(auth_obj, token_attr)
                        _LOGGER.info("%s    HAS %s:", indent, token_attr)
                        _LOGGER.info("%s      Type: %s", indent, type(token_value).__name__)
                        
                        if isinstance(token_value, dict):
                            _LOGGER.info("%s      Dict keys: %s", indent, list(token_value.keys()))
                            if 'IdToken' in token_value:
                                token_str = token_value['IdToken']
                                _LOGGER.info("%s      ★★★ FOUND TOKEN in %s.%s.%s.%s['IdToken'] ★★★", 
                                           indent, path, attr_name, auth_attr, token_attr)
                                _LOGGER.info("%s      Token length: %d", indent, len(token_str) if token_str else 0)
                                _LOGGER.info("%s      Token preview: %s...", indent, str(token_str)[:20] if token_str else "None")
                        elif isinstance(token_value, str):
                            _LOGGER.info("%s      String length: %d", indent, len(token_value))
                            if len(token_value) > 50:
                                _LOGGER.info("%s      ★★★ FOUND TOKEN in %s.%s.%s.%s ★★★", 
                                           indent, path, attr_name, auth_attr, token_attr)
                                _LOGGER.info("%s      Token preview: %s...", indent, token_value[:20])
                
                # Show all auth attributes for context
                if hasattr(auth_obj, '__dict__'):
                    auth_attrs = [k for k in vars(auth_obj).keys()]
                    _LOGGER.info("%s    All auth attributes: %s", indent, auth_attrs)
            
            # Recurse
            _inspect_object_for_token(attr_value, f"{path}.{attr_name}", depth + 1, max_depth)


def create_diagnostic_service(hass):
    """Create a diagnostic service that can be called from Home Assistant."""
    async def handle_diagnose(call):
        """Handle the diagnostic service call."""
        _LOGGER.info("=" * 80)
        _LOGGER.info("DIAGNOSTIC SERVICE CALLED")
        _LOGGER.info("=" * 80)
        await hass.async_add_executor_job(inspect_hive_integration, hass)
    
    hass.services.async_register("hive_schedule", "diagnose_hive", handle_diagnose)
    _LOGGER.info("Diagnostic service 'hive_schedule.diagnose_hive' registered")
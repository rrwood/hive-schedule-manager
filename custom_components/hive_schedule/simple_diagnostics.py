"""Simple diagnostic - uses WARNING level so it shows up in logs."""
import logging

_LOGGER = logging.getLogger(__name__)


def simple_diagnostic(hass) -> None:
    """Simple diagnostic that uses WARNING level."""
    _LOGGER.warning("=" * 80)
    _LOGGER.warning("HIVE DIAGNOSTIC START")
    _LOGGER.warning("=" * 80)
    
    # Get Hive entries
    hive_entries = hass.config_entries.async_entries("hive")
    _LOGGER.warning("Found %d Hive config entries", len(hive_entries))
    
    if not hive_entries:
        _LOGGER.warning("NO HIVE ENTRIES FOUND - Is Hive integration configured?")
        return
    
    for idx, entry in enumerate(hive_entries):
        _LOGGER.warning("")
        _LOGGER.warning("ENTRY #%d: %s", idx + 1, entry.entry_id)
        _LOGGER.warning("  Title: %s", entry.title)
        _LOGGER.warning("  State: %s", entry.state)
        
        # Check data
        _LOGGER.warning("  entry.data keys: %s", list(entry.data.keys()) if entry.data else "None")
        
        # Check runtime_data
        has_runtime = hasattr(entry, 'runtime_data') and entry.runtime_data is not None
        _LOGGER.warning("  Has runtime_data: %s", has_runtime)
        
        if has_runtime:
            runtime = entry.runtime_data
            _LOGGER.warning("  runtime_data type: %s", type(runtime).__name__)
            _LOGGER.warning("  runtime_data module: %s", type(runtime).__module__)
            
            # Check if it has __dict__
            if hasattr(runtime, '__dict__'):
                attrs = list(vars(runtime).keys())
                _LOGGER.warning("  runtime_data attributes (%d): %s", len(attrs), attrs)
                
                # Check each attribute
                for attr_name in attrs:
                    try:
                        attr_value = getattr(runtime, attr_name)
                        _LOGGER.warning("    %s: type=%s", attr_name, type(attr_value).__name__)
                        
                        # If it's an object, check for auth-related stuff
                        if hasattr(attr_value, '__dict__'):
                            sub_attrs = list(vars(attr_value).keys())
                            _LOGGER.warning("      → has %d attributes: %s", len(sub_attrs), sub_attrs[:10])
                            
                            # Look for auth
                            for auth_attr in ['auth', '_auth', 'token', 'session']:
                                if hasattr(attr_value, auth_attr):
                                    auth_obj = getattr(attr_value, auth_attr)
                                    _LOGGER.warning("      → %s.%s exists (type: %s)", attr_name, auth_attr, type(auth_obj).__name__)
                                    
                                    if hasattr(auth_obj, '__dict__'):
                                        auth_sub_attrs = list(vars(auth_obj).keys())
                                        _LOGGER.warning("        → %s.%s has attributes: %s", attr_name, auth_attr, auth_sub_attrs)
                                        
                                        # Check for token attributes
                                        for token_attr in ['tokenData', 'token', '_token', 'access_token', 'id_token']:
                                            if hasattr(auth_obj, token_attr):
                                                token_val = getattr(auth_obj, token_attr)
                                                _LOGGER.warning("        → FOUND %s.%s.%s (type: %s)", 
                                                              attr_name, auth_attr, token_attr, type(token_val).__name__)
                                                
                                                if isinstance(token_val, dict):
                                                    _LOGGER.warning("          → Dict keys: %s", list(token_val.keys()))
                                                    if 'IdToken' in token_val:
                                                        token_str = token_val['IdToken']
                                                        _LOGGER.warning("          → ★★★ FOUND TOKEN at %s.%s.%s['IdToken'] ★★★", 
                                                                      attr_name, auth_attr, token_attr)
                                                        _LOGGER.warning("          → Token length: %d", len(token_str) if token_str else 0)
                                                elif isinstance(token_val, str) and len(token_val) > 50:
                                                    _LOGGER.warning("          → ★★★ FOUND TOKEN at %s.%s.%s ★★★", 
                                                                  attr_name, auth_attr, token_attr)
                                                    _LOGGER.warning("          → Token length: %d", len(token_val))
                    except Exception as e:
                        _LOGGER.warning("    Error checking %s: %s", attr_name, str(e))
            else:
                _LOGGER.warning("  runtime_data has no __dict__")
        else:
            _LOGGER.warning("  runtime_data is None or doesn't exist")
    
    # Also check hass.data
    _LOGGER.warning("")
    _LOGGER.warning("Checking hass.data...")
    
    if "hive" in hass.data:
        _LOGGER.warning("  'hive' found in hass.data (type: %s)", type(hass.data["hive"]).__name__)
    else:
        _LOGGER.warning("  'hive' NOT in hass.data")
    
    # Check for entry IDs
    for entry in hive_entries:
        if entry.entry_id in hass.data:
            _LOGGER.warning("  Entry ID '%s' found in hass.data (type: %s)", 
                          entry.entry_id[:8], type(hass.data[entry.entry_id]).__name__)
        else:
            _LOGGER.warning("  Entry ID '%s' NOT in hass.data", entry.entry_id[:8])
    
    _LOGGER.warning("")
    _LOGGER.warning("=" * 80)
    _LOGGER.warning("HIVE DIAGNOSTIC END")
    _LOGGER.warning("=" * 80)


def create_simple_diagnostic_service(hass):
    """Create simple diagnostic service."""
    async def handle_simple_diagnose(call):
        """Handle the simple diagnostic service call."""
        _LOGGER.warning("SIMPLE DIAGNOSTIC SERVICE CALLED - Output will use WARNING level")
        await hass.async_add_executor_job(simple_diagnostic, hass)
    
    hass.services.async_register("hive_schedule", "simple_diagnose", handle_simple_diagnose)
    _LOGGER.warning("Simple diagnostic service 'hive_schedule.simple_diagnose' registered")
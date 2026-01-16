"""Ultra-verbose diagnostics - dumps everything we can find about Hive."""
import logging
from typing import Any
import json

_LOGGER = logging.getLogger(__name__)


def dump_object(obj: Any, name: str, depth: int = 0, max_depth: int = 4, seen=None) -> None:
    """Recursively dump object structure."""
    if seen is None:
        seen = set()
    
    # Avoid infinite recursion
    obj_id = id(obj)
    if obj_id in seen or depth > max_depth:
        return
    seen.add(obj_id)
    
    indent = "  " * depth
    
    # Basic type info
    _LOGGER.info("%s%s:", indent, name)
    _LOGGER.info("%s  Type: %s", indent, type(obj).__name__)
    _LOGGER.info("%s  Module: %s", indent, getattr(type(obj), '__module__', 'unknown'))
    
    # For strings, show value if short
    if isinstance(obj, str):
        if len(obj) < 100:
            _LOGGER.info("%s  Value: %s", indent, obj)
        else:
            _LOGGER.info("%s  Value: %s... (length: %d)", indent, obj[:50], len(obj))
        return
    
    # For numbers, bools, None
    if obj is None or isinstance(obj, (int, float, bool)):
        _LOGGER.info("%s  Value: %s", indent, obj)
        return
    
    # For dicts
    if isinstance(obj, dict):
        _LOGGER.info("%s  Dict with %d keys: %s", indent, len(obj), list(obj.keys())[:10])
        for key, value in list(obj.items())[:5]:  # Only first 5
            dump_object(value, f"{name}['{key}']", depth + 1, max_depth, seen)
        return
    
    # For lists
    if isinstance(obj, (list, tuple)):
        _LOGGER.info("%s  List/Tuple with %d items", indent, len(obj))
        if len(obj) > 0:
            dump_object(obj[0], f"{name}[0]", depth + 1, max_depth, seen)
        return
    
    # For objects with __dict__
    if hasattr(obj, '__dict__'):
        attrs = vars(obj)
        _LOGGER.info("%s  Object with %d attributes", indent, len(attrs))
        
        # Show all attribute names
        attr_names = list(attrs.keys())
        _LOGGER.info("%s  Attributes: %s", indent, attr_names[:20])
        
        # Look for promising attributes
        priority_attrs = ['session', 'api', 'auth', 'token', 'hive', 'client',
                         '_session', '_api', '_auth', '_token', '_hive', '_client',
                         'tokenData', 'access_token', 'id_token', 'IdToken']
        
        for attr_name in priority_attrs:
            if attr_name in attrs:
                dump_object(attrs[attr_name], f"{name}.{attr_name}", depth + 1, max_depth, seen)


def ultra_verbose_diagnostic(hass) -> None:
    """Ultra-verbose diagnostic that dumps everything."""
    _LOGGER.info("=" * 100)
    _LOGGER.info("ULTRA-VERBOSE HIVE DIAGNOSTIC")
    _LOGGER.info("=" * 100)
    
    # Get Hive entries
    hive_entries = hass.config_entries.async_entries("hive")
    _LOGGER.info("Found %d Hive config entries", len(hive_entries))
    
    for idx, entry in enumerate(hive_entries):
        _LOGGER.info("")
        _LOGGER.info("=" * 100)
        _LOGGER.info("ENTRY #%d", idx + 1)
        _LOGGER.info("=" * 100)
        _LOGGER.info("Entry ID: %s", entry.entry_id)
        _LOGGER.info("Title: %s", entry.title)
        _LOGGER.info("State: %s", entry.state)
        _LOGGER.info("Domain: %s", entry.domain)
        
        # Dump entry.data
        _LOGGER.info("")
        _LOGGER.info("-" * 50)
        _LOGGER.info("ENTRY.DATA")
        _LOGGER.info("-" * 50)
        if entry.data:
            dump_object(entry.data, "entry.data", depth=0, max_depth=2)
        else:
            _LOGGER.info("entry.data is None or empty")
        
        # Dump entry.runtime_data
        _LOGGER.info("")
        _LOGGER.info("-" * 50)
        _LOGGER.info("ENTRY.RUNTIME_DATA")
        _LOGGER.info("-" * 50)
        if hasattr(entry, 'runtime_data') and entry.runtime_data:
            dump_object(entry.runtime_data, "entry.runtime_data", depth=0, max_depth=4)
        else:
            _LOGGER.info("entry.runtime_data is None or doesn't exist")
    
    # Check hass.data
    _LOGGER.info("")
    _LOGGER.info("=" * 100)
    _LOGGER.info("HASS.DATA")
    _LOGGER.info("=" * 100)
    
    # List all domains
    all_domains = [k for k in hass.data.keys() if not k.startswith('_')]
    _LOGGER.info("All domains in hass.data: %s", all_domains[:30])
    
    # Check for 'hive'
    if "hive" in hass.data:
        _LOGGER.info("")
        _LOGGER.info("-" * 50)
        _LOGGER.info("HASS.DATA['hive']")
        _LOGGER.info("-" * 50)
        dump_object(hass.data["hive"], "hass.data['hive']", depth=0, max_depth=4)
    
    # Check for entry IDs
    for entry in hive_entries:
        entry_id = entry.entry_id
        if entry_id in hass.data:
            _LOGGER.info("")
            _LOGGER.info("-" * 50)
            _LOGGER.info("HASS.DATA['%s']", entry_id)
            _LOGGER.info("-" * 50)
            dump_object(hass.data[entry_id], f"hass.data['{entry_id}']", depth=0, max_depth=4)
    
    # Check for any keys with 'hive' in the name
    hive_related_keys = [k for k in hass.data.keys() if 'hive' in str(k).lower()]
    if hive_related_keys:
        _LOGGER.info("")
        _LOGGER.info("-" * 50)
        _LOGGER.info("HIVE-RELATED KEYS IN HASS.DATA")
        _LOGGER.info("-" * 50)
        for key in hive_related_keys:
            _LOGGER.info("Key: %s", key)
            dump_object(hass.data[key], f"hass.data['{key}']", depth=0, max_depth=4)
    
    _LOGGER.info("")
    _LOGGER.info("=" * 100)
    _LOGGER.info("END OF ULTRA-VERBOSE DIAGNOSTIC")
    _LOGGER.info("=" * 100)


def create_ultra_diagnostic_service(hass):
    """Create ultra-verbose diagnostic service."""
    async def handle_ultra_diagnose(call):
        """Handle the ultra diagnostic service call."""
        _LOGGER.info("ULTRA-VERBOSE DIAGNOSTIC SERVICE CALLED")
        await hass.async_add_executor_job(ultra_verbose_diagnostic, hass)
    
    hass.services.async_register("hive_schedule", "ultra_diagnose", handle_ultra_diagnose)
    _LOGGER.info("Ultra diagnostic service 'hive_schedule.ultra_diagnose' registered")

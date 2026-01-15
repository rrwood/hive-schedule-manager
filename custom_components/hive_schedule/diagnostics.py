"""Diagnostics for Hive Schedule Manager - Find the auth token location."""
import logging

_LOGGER = logging.getLogger(__name__)


def inspect_hive_data(hass):
    """Inspect hass.data to find where the Hive auth token is stored."""
    _LOGGER.info("=" * 60)
    _LOGGER.info("HIVE DATA STRUCTURE INSPECTION")
    _LOGGER.info("=" * 60)
    
    # Check if hive exists
    if "hive" not in hass.data:
        _LOGGER.error("'hive' key not found in hass.data")
        _LOGGER.info("Available keys: %s", list(hass.data.keys()))
        return None
    
    hive_data = hass.data["hive"]
    _LOGGER.info("hive data type: %s", type(hive_data))
    
    # If it's a dict
    if isinstance(hive_data, dict):
        _LOGGER.info("hive is a dict with keys: %s", list(hive_data.keys()))
        for key, value in hive_data.items():
            _LOGGER.info("  hive['%s'] type: %s", key, type(value))
            if hasattr(value, "__dict__"):
                _LOGGER.info("    Attributes: %s", list(vars(value).keys()))
    
    # If it's an object
    else:
        _LOGGER.info("hive is an object of type: %s", type(hive_data))
        if hasattr(hive_data, "__dict__"):
            _LOGGER.info("hive attributes: %s", list(vars(hive_data).keys()))
        
        # Check common attribute names
        for attr in ["session", "api", "auth", "client", "_session", "_api", "hive"]:
            if hasattr(hive_data, attr):
                obj = getattr(hive_data, attr)
                _LOGGER.info("hive.%s exists, type: %s", attr, type(obj))
                if hasattr(obj, "__dict__"):
                    _LOGGER.info("  hive.%s attributes: %s", attr, list(vars(obj).keys()))
                
                # Go one level deeper
                if hasattr(obj, "auth"):
                    auth_obj = getattr(obj, "auth")
                    _LOGGER.info("    hive.%s.auth type: %s", attr, type(auth_obj))
                    if hasattr(auth_obj, "__dict__"):
                        _LOGGER.info("      hive.%s.auth attributes: %s", attr, list(vars(auth_obj).keys()))
                
                if hasattr(obj, "token"):
                    token = getattr(obj, "token")
                    _LOGGER.info("    hive.%s.token found! (length: %d)", attr, len(str(token)) if token else 0)
    
    # Check for entry data
    _LOGGER.info("Checking config entries...")
    for entry in hass.config_entries.async_entries("hive"):
        _LOGGER.info("Found Hive config entry: %s", entry.entry_id)
        if entry.data:
            _LOGGER.info("  Entry data keys: %s", list(entry.data.keys()))
        if entry.runtime_data:
            _LOGGER.info("  Entry runtime_data type: %s", type(entry.runtime_data))
            if hasattr(entry.runtime_data, "__dict__"):
                _LOGGER.info("  Entry runtime_data attrs: %s", list(vars(entry.runtime_data).keys()))
    
    _LOGGER.info("=" * 60)
    return None

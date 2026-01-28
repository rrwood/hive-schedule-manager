"""Schedule profiles for Hive heating schedules."""

from typing import Dict, List

# Each profile defines time/temperature pairs for a day
# Format: [{"time": "HH:MM", "temp": float}, ...]

PROFILES: Dict[str, List[Dict[str, any]]] = {
    "weekday": [
        {"time": "06:30", "temp": 18.0},  # Morning warmup
        {"time": "08:00", "temp": 16.0},  # Away during day
        {"time": "16:30", "temp": 19.5},  # Evening warmup
        {"time": "21:30", "temp": 16.0},  # Night setback
    ],
    
    "weekend": [
        {"time": "07:30", "temp": 18.0},  # Later morning warmup
        {"time": "09:00", "temp": 19.0},  # Comfortable day temperature
        {"time": "22:00", "temp": 16.0},  # Later night setback
    ],
    
    "holiday": [
        {"time": "08:00", "temp": 18.0},  # Relaxed morning
        {"time": "22:30", "temp": 16.0},  # Extended evening
    ],
    
    # Workday with early start
    "weekday_early": [
        {"time": "05:30", "temp": 18.0},
        {"time": "07:00", "temp": 16.0},
        {"time": "16:30", "temp": 19.5},
        {"time": "21:30", "temp": 16.0},
    ],
    
    # Workday with late return
    "weekday_late": [
        {"time": "06:30", "temp": 18.0},
        {"time": "08:00", "temp": 16.0},
        {"time": "18:30", "temp": 19.5},
        {"time": "23:00", "temp": 16.0},
    ],
    
    # Work from home
    "wfh": [
        {"time": "06:30", "temp": 18.0},
        {"time": "09:00", "temp": 19.0},
        {"time": "17:00", "temp": 19.5},
        {"time": "22:00", "temp": 16.0},
    ],
    
    # Minimal heating (away/vacation)
    "away": [
        {"time": "00:00", "temp": 12.0},  # Frost protection
    ],
    
    # All day comfort
    "all_day_comfort": [
        {"time": "00:00", "temp": 19.0},
    ],
}


def get_profile(profile_name: str) -> List[Dict[str, any]]:
    """Get a schedule profile by name.
    
    Args:
        profile_name: Name of the profile to retrieve
        
    Returns:
        List of time/temperature dictionaries
        
    Raises:
        ValueError: If profile_name doesn't exist
    """
    if profile_name not in PROFILES:
        raise ValueError(
            f"Unknown profile '{profile_name}'. "
            f"Available profiles: {', '.join(PROFILES.keys())}"
        )
    return PROFILES[profile_name]


def get_available_profiles() -> List[str]:
    """Get list of available profile names."""
    return list(PROFILES.keys())


def validate_custom_schedule(schedule: List[Dict[str, any]]) -> bool:
    """Validate a custom schedule format.
    
    Args:
        schedule: List of time/temp dictionaries
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If schedule format is invalid
    """
    if not isinstance(schedule, list):
        raise ValueError("Schedule must be a list")
    
    if len(schedule) == 0:
        raise ValueError("Schedule must have at least one entry")
    
    for entry in schedule:
        if not isinstance(entry, dict):
            raise ValueError("Each schedule entry must be a dictionary")
        
        if "time" not in entry or "temp" not in entry:
            raise ValueError("Each entry must have 'time' and 'temp' keys")
        
        # Validate time format (HH:MM)
        time_str = entry["time"]
        try:
            hours, minutes = time_str.split(":")
            if not (0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid time format: {time_str}. Must be HH:MM")
        
        # Validate temperature
        try:
            temp = float(entry["temp"])
            if not (5.0 <= temp <= 32.0):
                raise ValueError(f"Temperature {temp}°C out of range (5-32°C)")
        except (ValueError, TypeError):
            raise ValueError(f"Invalid temperature: {entry['temp']}")
    
    return True
#!/usr/bin/env python3
"""
Helper script to decode Hive schedule times from POST response logs.

Usage:
  python3 decode_schedule.py

Then paste the schedule JSON from your logs.
Example input:
  {"schedule":{"wednesday":[{"value":{"target":18.5},"start":330}]}}
"""

import json
import sys


def minutes_to_time(minutes):
    """Convert minutes from midnight to HH:MM format."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def decode_schedule(schedule_json):
    """Decode a schedule from Hive API format to readable format."""
    try:
        data = json.loads(schedule_json)
        
        if "schedule" not in data:
            print("Error: No 'schedule' key found in JSON")
            return
        
        schedule = data["schedule"]
        
        print("\n" + "=" * 60)
        print("DECODED SCHEDULE")
        print("=" * 60)
        
        for day, entries in schedule.items():
            print(f"\n{day.upper()}:")
            print("-" * 40)
            
            for entry in entries:
                time = minutes_to_time(entry["start"])
                temp = entry["value"]["target"]
                print(f"  {time} → {temp}°C")
        
        print("\n" + "=" * 60)
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {e}")
    except KeyError as e:
        print(f"Error: Missing key - {e}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    print("Hive Schedule Decoder")
    print("=" * 60)
    print("Paste your schedule JSON from the logs (Ctrl+D when done):")
    print("Example: {\"schedule\":{\"monday\":[{\"value\":{\"target\":18.5},\"start\":330}]}}")
    print("-" * 60)
    
    try:
        schedule_json = sys.stdin.read().strip()
        
        if not schedule_json:
            print("No input provided")
            return
        
        decode_schedule(schedule_json)
        
    except KeyboardInterrupt:
        print("\nCancelled")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Helper script to inject notifications into the Obsidian dashboard.

Usage:
    python3 send_notification.py --title "Title" --message "Message" [--sound]
"""

import argparse
import json
import time
from pathlib import Path

def send_notification(title: str, message: str, play_sound: bool = True) -> None:
    # Resolve Research root (two levels up from _scripts/cron/)
    root_dir = Path(__file__).resolve().parent.parent.parent
    noti_file = root_dir / "06_PLANNING" / "kpis" / "notifications.json"
    
    # Ensure directory exists
    noti_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing notifications
    notifications = []
    if noti_file.exists():
        try:
            with open(noti_file, "r", encoding="utf-8") as f:
                notifications = json.load(f)
                if not isinstance(notifications, list):
                    notifications = []
        except Exception:
            notifications = []
            
    # Create new notification
    noti_id = str(int(time.time() * 1000))
    new_noti = {
        "id": noti_id,
        "title": title,
        "message": message,
        "timestamp": int(time.time() * 1000),
        "read": False,
        "sound": play_sound
    }
    
    notifications.append(new_noti)
    
    # Keep only the last 20 notifications to prevent file bloating
    notifications = notifications[-20:]
    
    # Save back
    with open(noti_file, "w", encoding="utf-8") as f:
        json.dump(notifications, f, indent=2, ensure_ascii=False)
        
    print(f"Notification added: {title} - {message}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Send notification to Obsidian Dashboard")
    parser.add_argument("--title", required=True, help="Notification Title")
    parser.add_argument("--message", required=True, help="Notification Message")
    parser.add_argument("--no-sound", action="store_true", help="Do not play sound in dashboard")
    args = parser.parse_args()
    
    send_notification(args.title, args.message, not args.no_sound)

if __name__ == "__main__":
    main()

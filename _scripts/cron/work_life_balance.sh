#!/bin/bash
# Work-life balance reminder: Mon-Fri at 17:00
# Reminds you that in one hour it's time to go home.

# Vault internal notification
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/send_notification.py" --title "🕐 Work-Life Balance" --message "Time to wrap up — one hour left before heading home!"



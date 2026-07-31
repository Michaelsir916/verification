#!/data/data/com.termux/files/usr/bin/bash
#
# restart_bot.sh — Safely (re)starts paidchannelmanager.
# Kills any already-running "python bot.py" processes first, so you
# never get the "Conflict: terminated by other getUpdates request" error
# from having two instances polling with the same bot token.
#
# Usage:
#   cd ~/paidchannelmanager   # (your repo folder)
#   bash restart_bot.sh

echo "🔍 Checking for existing bot.py processes..."

# Find PIDs of any running "python bot.py" / "python3 bot.py", excluding this grep itself
PIDS=$(ps aux | grep '[b]ot.py')

if [ -n "$PIDS" ]; then
    echo "⚠️  Found running instance(s):"
    echo "$PIDS"
    echo "$PIDS" | awk '{print $2}' | xargs -r kill -9
    echo "🛑 Killed old process(es)."
    sleep 1
else
    echo "✅ No existing instance running."
fi

echo "🚀 Starting bot..."
cd "$(dirname "$0")" || exit 1
python bot.py

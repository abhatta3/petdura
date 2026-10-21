#!/usr/bin/env bash
set -e

# Find local non-loopback IP address on macOS / Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)
else
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ip addr show | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1 | head -n 1)
fi

if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="127.0.0.1"
fi

PORT=${APP_PORT:-5050}

echo "=================================================="
echo " Starting PETDURA for local network sharing..."
echo "=================================================="
echo " Local URL:    http://127.0.0.1:$PORT"
echo " Network URL:  http://$LOCAL_IP:$PORT"
echo " (Share the Network URL with collaborators on Wi-Fi)"
echo "=================================================="

# Ensure dependencies are installed
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run Flask app binding to all interfaces
export APP_HOST="0.0.0.0"
export APP_PORT="$PORT"
python3 app.py

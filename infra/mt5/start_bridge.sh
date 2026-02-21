#!/bin/bash
# Starts the Flask MT5 bridge inside Wine Python (where MetaTrader5 module lives)
# NO rpyc, NO mt5linux — direct MetaTrader5 API calls via Flask

echo "[JSR] Installing Flask in Wine Python..."
su -s /bin/bash abc -c 'WINEPREFIX=/config/.wine wine python.exe -m pip install -q flask 2>/dev/null'

echo "[JSR] Starting MT5 Flask bridge (Wine Python)..."
su -s /bin/bash abc -c 'WINEPREFIX=/config/.wine nohup wine python.exe /app/mt5_bridge_server.py > /var/log/mt5_bridge.log 2>&1 &'

echo "[JSR] Bridge PID started in background"

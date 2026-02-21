#!/bin/bash
# =============================================================================
# PURPOSE: Automatically enable AutoTrading in MT5 after terminal startup.
# MT5 starts with AutoTrading disabled by default. This script waits for the
# MT5 window to appear, closes any Login dialog, and sends Ctrl+E to toggle
# AutoTrading ON. Runs as a background process during container startup.
# =============================================================================

export DISPLAY=:1
MAX_WAIT=300  # 5 minutes max wait for MT5 window
POLL_INTERVAL=5

echo "[JSR-AutoTrade] Waiting for MT5 window to appear..."

elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    # Look for the main MT5 window (contains broker name or account number)
    MT5_WID=$(xdotool search --name "Monaxa\|MetaTrader\|Demo Account\|Real Account" 2>/dev/null | head -1)
    if [ -n "$MT5_WID" ]; then
        echo "[JSR-AutoTrade] MT5 window found (ID: $MT5_WID) after ${elapsed}s"
        break
    fi
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

if [ -z "$MT5_WID" ]; then
    echo "[JSR-AutoTrade] ERROR: MT5 window not found after ${MAX_WAIT}s. AutoTrading NOT enabled."
    exit 1
fi

# Give MT5 a moment to fully render
sleep 5

# Close any Login dialog that may have popped up
LOGIN_WID=$(xdotool search --name "Login" 2>/dev/null | head -1)
if [ -n "$LOGIN_WID" ]; then
    echo "[JSR-AutoTrade] Closing Login dialog..."
    xdotool windowactivate --sync "$LOGIN_WID" key Escape
    sleep 2
fi

# Focus the MT5 main window and send Ctrl+E to enable AutoTrading
echo "[JSR-AutoTrade] Sending Ctrl+E to enable AutoTrading..."
xdotool windowactivate --sync "$MT5_WID" key ctrl+e
sleep 2

# Verify by checking window title — when AutoTrading is ON, title doesn't change,
# but we can test with an order via the bridge (done externally)
echo "[JSR-AutoTrade] AutoTrading toggle sent. Done."

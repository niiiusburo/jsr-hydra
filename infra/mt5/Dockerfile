FROM gmag11/metatrader5_vnc:latest

# Install xdotool for GUI automation (enable AutoTrading via Ctrl+E)
# Note: Wine HQ repo has expired GPG key, so we skip it during update
RUN rm -f /etc/apt/sources.list.d/winehq.list 2>/dev/null; \
    apt-get update -qq || true && \
    apt-get install -y -qq --no-install-recommends xdotool && \
    rm -rf /var/lib/apt/lists/*

# Copy bridge server and AutoTrading enabler
COPY mt5_bridge_server.py /app/mt5_bridge_server.py
COPY enable_autotrading.sh /app/enable_autotrading.sh
RUN chmod +x /app/enable_autotrading.sh

# Patch start.sh:
# 1. Disable the broken rpyc/mt5linux server (replace with no-op echo)
# 2. Append Flask bridge startup at the END of start.sh
# 3. Append AutoTrading enabler (runs in background, waits for MT5 window)
#    (start.sh runs as the main service, so background processes survive)
RUN sed -i 's|python3 -m mt5linux.*python.exe.*|echo "[JSR] rpyc server disabled - using Flask bridge instead"|g' /Metatrader/start.sh && \
    echo '' >> /Metatrader/start.sh && \
    echo '# === JSR Flask Bridge ===' >> /Metatrader/start.sh && \
    echo 'echo "[JSR] Installing Flask in Wine Python..."' >> /Metatrader/start.sh && \
    echo '$wine_executable python.exe -m pip install -q flask 2>/dev/null' >> /Metatrader/start.sh && \
    echo 'echo "[JSR] Starting Flask MT5 bridge (90s startup delay built-in)..."' >> /Metatrader/start.sh && \
    echo '$wine_executable python.exe /app/mt5_bridge_server.py &' >> /Metatrader/start.sh && \
    echo 'echo "[JSR] Flask bridge PID: $!"' >> /Metatrader/start.sh && \
    echo '' >> /Metatrader/start.sh && \
    echo '# === JSR AutoTrading Enabler ===' >> /Metatrader/start.sh && \
    echo 'echo "[JSR] Launching AutoTrading enabler in background..."' >> /Metatrader/start.sh && \
    echo '/app/enable_autotrading.sh &' >> /Metatrader/start.sh && \
    echo "[JSR] Patched start.sh: disabled rpyc, added Flask bridge + AutoTrading enabler"

# Create an s6 service to run MT5 start.sh reliably on boot
# (openbox autostart is unreliable — this ensures MT5 always starts)
RUN mkdir -p /etc/s6-overlay/s6-rc.d/svc-mt5 && \
    echo "longrun" > /etc/s6-overlay/s6-rc.d/svc-mt5/type && \
    printf '#!/usr/bin/with-contenv bash\n\n# Wait for desktop (Xvnc + openbox) to be ready\nuntil xdpyinfo -display :1 >/dev/null 2>&1; do sleep 2; done\nsleep 5\n\ncd /Metatrader\nexec s6-setuidgid abc \\\n  env DISPLAY=:1 \\\n  bash /Metatrader/start.sh\n' > /etc/s6-overlay/s6-rc.d/svc-mt5/run && \
    chmod +x /etc/s6-overlay/s6-rc.d/svc-mt5/run && \
    mkdir -p /etc/s6-overlay/s6-rc.d/svc-mt5/dependencies.d && \
    touch /etc/s6-overlay/s6-rc.d/svc-mt5/dependencies.d/svc-de && \
    touch /etc/s6-overlay/s6-rc.d/user2/contents.d/svc-mt5 && \
    echo "[JSR] Created svc-mt5 s6 service (depends on svc-de)"

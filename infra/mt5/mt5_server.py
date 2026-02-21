"""
MT5 REST Bridge Server — Runs INSIDE the MT5 Docker container.

Wraps the Windows MetaTrader5 Python package (via Wine) in a simple
Flask HTTP API so the backend can access MT5 data without RPyC.

Endpoints:
    GET  /health          — Server health check
    GET  /account         — Account info (balance, equity, margin)
    GET  /symbols         — All available symbols
    GET  /candles/<symbol>/<tf>/<count> — OHLCV candle data
    GET  /tick/<symbol>   — Latest bid/ask tick
    GET  /positions       — Open positions
    POST /order           — Open a new position
    POST /close/<ticket>  — Close a position by ticket
"""

import json
import sys
import time
import traceback
from datetime import datetime

# Wine runs the Windows Python + MetaTrader5 package
# This script runs in the LINUX Python inside the container
# and communicates with MT5 via the mt5linux bridge
try:
    from mt5linux import MetaTrader5
    MT5_MODE = "mt5linux"
except ImportError:
    import MetaTrader5
    MT5_MODE = "native"

from flask import Flask, jsonify, request

app = Flask(__name__)

# Global MT5 instance
mt5 = None
connected = False
startup_time = time.time()


def init_mt5():
    """Initialize MT5 connection."""
    global mt5, connected
    try:
        if MT5_MODE == "mt5linux":
            mt5 = MetaTrader5(host="localhost", port=8001)
        else:
            mt5 = MetaTrader5

        if not mt5.initialize():
            print(f"[MT5] initialize() failed: {mt5.last_error()}", flush=True)
            connected = False
            return False

        # Try login with env credentials
        import os
        login = int(os.environ.get("MT5_LOGIN", "0"))
        password = os.environ.get("MT5_PASSWORD", "")
        server = os.environ.get("MT5_SERVER", "")

        if login > 0 and password:
            if not mt5.login(login, password=password, server=server):
                print(f"[MT5] login failed: {mt5.last_error()}", flush=True)
                # Still try to continue — MT5 may already be logged in via GUI
            else:
                print(f"[MT5] Logged in: account {login} on {server}", flush=True)

        info = mt5.account_info()
        if info:
            print(f"[MT5] Connected: {info.server}, Account {info.login}, "
                  f"Balance: ${info.balance:.2f}, Equity: ${info.equity:.2f}", flush=True)
            connected = True
            return True
        else:
            print(f"[MT5] account_info() returned None: {mt5.last_error()}", flush=True)
            connected = False
            return False

    except Exception as e:
        print(f"[MT5] init error: {e}", flush=True)
        traceback.print_exc()
        connected = False
        return False


def ensure_connected():
    """Ensure MT5 is connected, reconnect if needed."""
    global connected
    if not connected:
        init_mt5()
    return connected


# ──── Timeframe mapping ────
TF_MAP = {
    "M1": 1,    # TIMEFRAME_M1
    "M5": 5,    # TIMEFRAME_M5
    "M15": 15,  # TIMEFRAME_M15
    "M30": 30,  # TIMEFRAME_M30
    "H1": 16385,   # TIMEFRAME_H1
    "H4": 16388,   # TIMEFRAME_H4
    "D1": 16408,   # TIMEFRAME_D1
    "W1": 32769,   # TIMEFRAME_W1
    "MN1": 49153,  # TIMEFRAME_MN1
}


@app.route("/health")
def health():
    ensure_connected()
    return jsonify({
        "status": "ok" if connected else "disconnected",
        "mt5_mode": MT5_MODE,
        "uptime": round(time.time() - startup_time),
        "connected": connected,
    })


@app.route("/account")
def account():
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        info = mt5.account_info()
        if info is None:
            return jsonify({"error": f"account_info failed: {mt5.last_error()}"}), 500

        return jsonify({
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level if info.margin_level else 0.0,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
            "name": info.name,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/symbols")
def symbols():
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        syms = mt5.symbols_get()
        if syms is None:
            return jsonify([])

        result = []
        for s in syms:
            if s.visible:
                result.append({
                    "name": s.name,
                    "description": s.description,
                    "point": s.point,
                    "digits": s.digits,
                    "spread": s.spread,
                    "trade_mode": s.trade_mode,
                    "volume_min": s.volume_min,
                    "volume_max": s.volume_max,
                    "volume_step": s.volume_step,
                })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/candles/<symbol>/<timeframe>/<int:count>")
def candles(symbol, timeframe, count):
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        tf = TF_MAP.get(timeframe)
        if tf is None:
            return jsonify({"error": f"Unknown timeframe: {timeframe}"}), 400

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            return jsonify({"error": f"No candles: {err}", "symbol": symbol}), 404

        result = []
        for r in rates:
            result.append({
                "time": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "tick_volume": int(r[5]),
                "spread": int(r[6]) if len(r) > 6 else 0,
                "real_volume": int(r[7]) if len(r) > 7 else 0,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tick/<symbol>")
def tick(symbol):
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            return jsonify({"error": f"No tick for {symbol}: {mt5.last_error()}"}), 404

        point = 0.0001  # default for forex
        sym_info = mt5.symbol_info(symbol)
        if sym_info:
            point = sym_info.point

        return jsonify({
            "bid": t.bid,
            "ask": t.ask,
            "last": t.last,
            "time": t.time,
            "spread": round((t.ask - t.bid) / point) if point > 0 else 0,
            "spread_raw": round(t.ask - t.bid, 6),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/positions")
def positions():
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        pos = mt5.positions_get()
        if pos is None:
            return jsonify([])

        result = []
        for p in pos:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "lots": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "commission": getattr(p, "commission", 0.0),
                "comment": p.comment,
                "magic": p.magic,
                "time_setup": p.time,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/order", methods=["POST"])
def order():
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        data = request.json
        symbol = data["symbol"]
        direction = data["direction"]  # "BUY" or "SELL"
        lots = float(data["lots"])
        sl = float(data.get("sl", 0.0))
        tp = float(data.get("tp", 0.0))
        comment = data.get("comment", "JSR_Hydra")

        # Get current price
        tick_info = mt5.symbol_info_tick(symbol)
        if tick_info is None:
            return jsonify({"error": f"Cannot get tick for {symbol}"}), 400

        if direction == "BUY":
            order_type = 0  # ORDER_TYPE_BUY
            price = tick_info.ask
        else:
            order_type = 1  # ORDER_TYPE_SELL
            price = tick_info.bid

        # Get filling mode
        sym_info = mt5.symbol_info(symbol)
        filling = 2  # ORDER_FILLING_IOC default
        if sym_info:
            if sym_info.filling_mode & 1:
                filling = 0  # FOK
            elif sym_info.filling_mode & 2:
                filling = 1  # IOC

        req = {
            "action": 1,      # TRADE_ACTION_DEAL
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": comment,
            "type_time": 0,    # ORDER_TIME_GTC
            "type_filling": filling,
        }

        print(f"[MT5] Sending order: {json.dumps(req)}", flush=True)
        result = mt5.order_send(req)

        if result is None:
            return jsonify({"error": f"order_send returned None: {mt5.last_error()}"}), 500

        response = {
            "retcode": result.retcode,
            "comment": result.comment,
            "ticket": result.order if result.retcode == 10009 else None,  # TRADE_RETCODE_DONE
            "price": result.price if hasattr(result, "price") else price,
            "volume": result.volume if hasattr(result, "volume") else lots,
        }

        print(f"[MT5] Order result: {json.dumps(response)}", flush=True)
        return jsonify(response)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/close/<int:ticket>", methods=["POST"])
def close(ticket):
    if not ensure_connected():
        return jsonify({"error": "MT5 not connected"}), 503

    try:
        pos = mt5.positions_get(ticket=ticket)
        if not pos or len(pos) == 0:
            return jsonify({"error": f"Position {ticket} not found"}), 404

        p = pos[0]
        close_type = 1 if p.type == 0 else 0  # Opposite direction
        tick_info = mt5.symbol_info_tick(p.symbol)
        if tick_info is None:
            return jsonify({"error": f"Cannot get tick for {p.symbol}"}), 400

        price = tick_info.bid if p.type == 0 else tick_info.ask

        # Get filling mode
        sym_info = mt5.symbol_info(p.symbol)
        filling = 2
        if sym_info:
            if sym_info.filling_mode & 1:
                filling = 0
            elif sym_info.filling_mode & 2:
                filling = 1

        req = {
            "action": 1,      # TRADE_ACTION_DEAL
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "JSR_close",
            "type_time": 0,
            "type_filling": filling,
        }

        print(f"[MT5] Closing position {ticket}: {json.dumps(req)}", flush=True)
        result = mt5.order_send(req)

        if result is None:
            return jsonify({"error": f"close failed: {mt5.last_error()}"}), 500

        response = {
            "retcode": result.retcode,
            "comment": result.comment,
        }
        print(f"[MT5] Close result: {json.dumps(response)}", flush=True)
        return jsonify(response)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("  JSR HYDRA — MT5 REST Bridge Server", flush=True)
    print("=" * 60, flush=True)

    # Wait for MT5 terminal to start
    import os
    wait = int(os.environ.get("MT5_INIT_WAIT", "30"))
    print(f"[MT5] Waiting {wait}s for MT5 terminal to start...", flush=True)
    time.sleep(wait)

    # Initialize MT5
    success = init_mt5()
    if not success:
        print("[MT5] WARNING: Initial connection failed. Will retry on requests.", flush=True)

    # Start Flask server
    print("[MT5] Starting REST bridge on port 18812...", flush=True)
    app.run(host="0.0.0.0", port=18812, debug=False)

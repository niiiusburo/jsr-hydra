"""
MT5 REST Bridge Server — Runs INSIDE Wine Python in the MT5 Docker container.
MetaTrader5 pip package works natively here (Wine = Windows Python).
NO rpyc, NO mt5linux — direct MetaTrader5 API calls.
"""
import json
import os
import time
import logging
from datetime import datetime
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BRIDGE] %(message)s')
log = logging.getLogger('mt5_bridge')

app = Flask(__name__)
mt5 = None
connected = False


def ensure_mt5():
    """Initialize MT5 connection. Retry until it works."""
    global mt5, connected
    if connected:
        return True
    try:
        import MetaTrader5 as _mt5
        mt5 = _mt5
        login = int(os.environ.get("MT5_LOGIN", 0))
        password = os.environ.get("MT5_PASSWORD", "")
        server = os.environ.get("MT5_SERVER", "")
        if not mt5.initialize(login=login, password=password, server=server):
            log.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False
        info = mt5.account_info()
        log.info(f"MT5 connected: {info.server}, account {info.login}, balance ${info.balance}")
        connected = True
        return True
    except Exception as e:
        log.error(f"MT5 init error: {e}")
        return False


@app.route('/health')
def health():
    ok = ensure_mt5()
    return jsonify({"status": "ok" if ok else "error", "connected": ok})


@app.route('/account')
def account():
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    info = mt5.account_info()
    return jsonify({
        "login": info.login, "server": info.server, "broker": info.company,
        "balance": info.balance, "equity": info.equity, "margin": info.margin,
        "free_margin": info.margin_free,
        "margin_level": info.margin_level if info.margin_level else 0,
        "currency": info.currency, "leverage": info.leverage, "profit": info.profit
    })


@app.route('/symbols')
def symbols():
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    syms = mt5.symbols_get()
    if syms is None:
        return jsonify([])
    visible = [s.name for s in syms if s.visible]
    return jsonify(visible)


@app.route('/candles/<symbol>/<timeframe>/<int:count>')
def candles(symbol, timeframe, count):
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    tf_map = {
        'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15, 'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1, 'W1': mt5.TIMEFRAME_W1
    }
    tf = tf_map.get(timeframe)
    if tf is None:
        return jsonify({"error": f"Unknown timeframe: {timeframe}"}), 400
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return jsonify({"error": f"No data for {symbol} {timeframe}", "mt5_error": str(mt5.last_error())}), 404
    result = []
    for r in rates:
        result.append({
            "time": int(r[0]), "open": float(r[1]), "high": float(r[2]),
            "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])
        })
    log.info(f"Candles: {symbol} {timeframe} x{len(result)}")
    return jsonify(result)


@app.route('/tick/<symbol>')
def tick(symbol):
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    t = mt5.symbol_info_tick(symbol)
    if t is None:
        return jsonify({"error": f"No tick for {symbol}"}), 404
    si = mt5.symbol_info(symbol)
    spread = round((t.ask - t.bid) / si.point, 1) if si and si.point else 0
    return jsonify({"bid": t.bid, "ask": t.ask, "last": t.last, "time": t.time, "spread": spread})


@app.route('/positions')
def positions():
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    pos = mt5.positions_get()
    if pos is None or len(pos) == 0:
        return jsonify([])
    return jsonify([{
        "ticket": p.ticket, "symbol": p.symbol,
        "type": "BUY" if p.type == 0 else "SELL",
        "lots": p.volume, "price_open": p.price_open,
        "price_current": p.price_current,
        "sl": p.sl, "tp": p.tp, "profit": p.profit,
        "swap": p.swap, "commission": 0.0, "comment": p.comment,
        "time": p.time, "magic": p.magic
    } for p in pos])


@app.route('/order', methods=['POST'])
def order():
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    data = request.json
    symbol = data['symbol']
    direction = data['direction']
    lots = float(data.get('lots', 0.01))
    sl = float(data.get('sl', 0.0))
    tp = float(data.get('tp', 0.0))
    comment = data.get('comment', 'JSR_Hydra')
    # Ensure symbol is selected/visible in Market Watch
    si = mt5.symbol_info(symbol)
    if si is None:
        return jsonify({"error": f"Symbol {symbol} not found"}), 400
    if not si.visible:
        if not mt5.symbol_select(symbol, True):
            return jsonify({"error": f"Failed to select {symbol}"}), 400
    tick_data = mt5.symbol_info_tick(symbol)
    if tick_data is None:
        return jsonify({"error": f"Cannot get tick for {symbol}"}), 400
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick_data.ask if direction == "BUY" else tick_data.bid
    last_result = None
    for filling in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
            "volume": lots, "type": order_type, "price": price,
            "sl": sl, "tp": tp, "deviation": 20, "magic": 777777,
            "comment": comment, "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(req)
        if result is None:
            err = mt5.last_error()
            log.error(f"ORDER order_send returned None for {symbol} filling={filling} | last_error={err}")
            continue
        last_result = result
        log.info(f"ORDER {direction} {symbol} {lots} @ {price} | filling={filling} | retcode={result.retcode} | {result.comment}")
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return jsonify({"success": True, "ticket": result.order, "price": result.price, "lots": lots, "retcode": result.retcode, "comment": result.comment})
    if last_result:
        return jsonify({"success": False, "ticket": None, "retcode": last_result.retcode, "comment": last_result.comment, "error": f"Order rejected: {last_result.comment}"}), 400
    return jsonify({"success": False, "ticket": None, "retcode": -1, "comment": "order_send returned None for all fill modes", "error": str(mt5.last_error())}), 400


@app.route('/close/<int:ticket>', methods=['POST'])
def close(ticket):
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    pos = mt5.positions_get(ticket=ticket)
    if pos is None or len(pos) == 0:
        return jsonify({"error": f"Position {ticket} not found"}), 404
    p = pos[0]
    close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
    tick_data = mt5.symbol_info_tick(p.symbol)
    price = tick_data.bid if p.type == 0 else tick_data.ask
    # Get symbol's supported filling mode
    si = mt5.symbol_info(p.symbol)
    fill_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
    if si and si.filling_mode == 2:
        # Symbol only supports IOC — try IOC first
        fill_modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
    last_result = None
    for filling in fill_modes:
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol,
            "volume": p.volume, "type": close_type, "position": ticket,
            "price": price, "deviation": 50, "magic": 777777,
            "comment": "JSR_close", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(req)
        last_result = result
        log.info(f"CLOSE ticket={ticket} {p.symbol} {p.volume} @ {price} | filling={filling} | retcode={result.retcode} | {result.comment}")
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return jsonify({"success": True, "retcode": result.retcode, "profit": p.profit})
    return jsonify({"success": False, "retcode": last_result.retcode if last_result else -1, "comment": last_result.comment if last_result else "order_send failed"}), 400


@app.route('/close_all', methods=['POST'])
def close_all():
    if not ensure_mt5():
        return jsonify({"error": "MT5 not connected"}), 503
    pos = mt5.positions_get()
    if pos is None or len(pos) == 0:
        return jsonify({"closed": 0})
    closed = 0
    for p in pos:
        close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        tick_data = mt5.symbol_info_tick(p.symbol)
        price = tick_data.bid if p.type == 0 else tick_data.ask
        si = mt5.symbol_info(p.symbol)
        fill_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
        if si and si.filling_mode == 2:
            fill_modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
        for filling in fill_modes:
            req = {
                "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol,
                "volume": p.volume, "type": close_type, "position": p.ticket,
                "price": price, "deviation": 50, "magic": 777777,
                "comment": "JSR_killswitch", "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }
            result = mt5.order_send(req)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
                break
    log.info(f"KILL SWITCH: closed {closed}/{len(pos)} positions")
    return jsonify({"closed": closed, "total": len(pos)})


if __name__ == '__main__':
    log.info("Waiting 90s for MT5 terminal to initialize...")
    time.sleep(90)
    log.info("Starting MT5 REST bridge on port 18812...")
    ensure_mt5()
    app.run(host='0.0.0.0', port=18812, debug=False)

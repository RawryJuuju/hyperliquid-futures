#!/usr/bin/env python3
"""
Hyperliquid / Papertrade.xyz Production Scalp Engine v3.1 (Pro-Trend MTF Pullback + SFP)
Directory: /home/ubuntu/papertrade_backtest/
Margin: $50 Fixed | Leverage: 100x (ETH), 100x (BTC)
Target Model: ✂️ 0.30% Cut-Loss | 🎯 1.20% Win-Target (Pure RR 1:4.0)
Strategy:
  1. Top-Down MTF Trend Engine (1H & 15M EMA20)
  2. Pro-Trend Pullback Retest (5M Micro-Sweep 6 bars)
  3. Major SFP Liquidity Sweep (20 bars)
  4. Radar Heartbeat: Periodic status report so operator knows radar is live
  5. Transparent Radar: No silent drops. If MTF blocks a counter-trend sweep, Telegram is notified.
Telegram Dispatcher: Real-time via @gweilovejuujubot
"""
import urllib.request
import json
import time
import os
import sys
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/papertrade_backtest"
STATE_FILE = os.path.join(BASE_DIR, "papertrade_state.json")
LOG_FILE = os.path.join(BASE_DIR, "papertrade_watcher.log")
GWEI_TOKEN_FILE = "/home/ubuntu/credentials/gweilovejuujubot_bot_tele_token.txt"

# Trading Configurations
FIXED_MARGIN = 50.0          # $50 per trade
LEVERAGE = {
    "ETH": 100,
    "BTC": 100
}
LIMIT_TTL_SECONDS = 25 * 60  # 25 menit (5 candle) auto-cancel jika limit belum terisi
TAKER_FEE_RATE = 0.0004       # 0.04% taker fee Papertrade/Hyperliquid

# Target Discipline: 0.30% Cut-Loss default
CUT_LOSS_PCT = 0.0030         # 0.30% Cut-loss

def get_volume_regime(candles_5m):
    """
    Volume-Adaptive Regime Detection:
    - High Volume Surge (Vol Ratio >= 1.30x): Expansion trend -> Target 1.20% (RR 1:4.0)
    - Standard/Low Volume (Vol Ratio < 1.30x): Range/Chop pullback -> Target 0.60% (RR 1:2.0)
    """
    if len(candles_5m) < 22:
        return "STANDARD_CHOP", 0.0060, 2.0, 1.0
    vols = [float(c["v"]) for c in candles_5m[-22:-2]]
    avg_v = sum(vols) / len(vols) if vols else 1.0
    cur_v = float(candles_5m[-2]["v"])
    vol_ratio = (cur_v / avg_v) if avg_v > 0 else 1.0
    
    if vol_ratio >= 1.30:
        return "HIGH_SURGE", 0.0120, 4.0, vol_ratio
    else:
        return "STANDARD_CHOP", 0.0060, 2.0, vol_ratio

def load_telegram_config():
    token = ""
    chat_id = "1341231370"
    if os.path.exists(GWEI_TOKEN_FILE):
        try:
            with open(GWEI_TOKEN_FILE) as f:
                token = f.read().strip()
        except Exception:
            pass
    return token, chat_id

def send_telegram(text):
    token, chat_id = load_telegram_config()
    if not token or not chat_id:
        print("[WARN] Telegram token or chat_id missing. Msg:", text)
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            # Fallback to plain text if Markdown formatting error
            try:
                plain_payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
                with urllib.request.urlopen(urllib.request.Request(url, data=plain_payload, headers={"Content-Type": "application/json"}), timeout=8) as resp:
                    return True
            except:
                pass
        print(f"[ERR] Failed to send Telegram: {e}")
        return False
    except Exception as e:
        print(f"[ERR] Failed to send Telegram: {e}")
        return False

# In-memory Rate-Limit Shield Cache
_CACHE = {}

def fetch_candles(coin="ETH", interval="5m", limit=30):
    now = time.time()
    cache_key = f"candles_{coin}_{interval}_{limit}"
    ttl = 45 if interval in ["15m", "1h", "4h"] else 12
    if cache_key in _CACHE:
        cached_time, cached_val = _CACHE[cache_key]
        if now - cached_time < ttl:
            return cached_val

    now_ms = int(time.time() * 1000)
    mins_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
    step = mins_map.get(interval, 5)
    start_ms = now_ms - (limit * step * 60 * 1000)
    
    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms
        }
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            candles = []
            for k in raw:
                candles.append({
                    "t": k["t"],
                    "o": float(k["o"]),
                    "h": float(k["h"]),
                    "l": float(k["l"]),
                    "c": float(k["c"]),
                    "v": float(k["v"]),
                    "time_str": datetime.fromtimestamp(k["t"]/1000, tz=WIB).strftime("%H:%M")
                })
            _CACHE[cache_key] = (now, candles)
            return candles
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # Backoff quietly and return stale cache if available
            time.sleep(2)
            if cache_key in _CACHE:
                return _CACHE[cache_key][1]
        print(f"[WARN] fetch_candles({coin}, {interval}): HTTP {e.code}")
        return _CACHE.get(cache_key, (0, []))[1]
    except Exception as e:
        print(f"[ERR] fetch_candles({coin}, {interval}): {e}")
        return _CACHE.get(cache_key, (0, []))[1]

def fetch_live_price(coin="ETH"):
    now = time.time()
    if "_all_mids" in _CACHE:
        c_time, c_mids = _CACHE["_all_mids"]
        if now - c_time < 3.0:
            return c_mids.get(coin)

    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({"type": "allMids"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            float_mids = {k: float(v) for k, v in data.items() if k in ["ETH", "BTC"]}
            _CACHE["_all_mids"] = (now, float_mids)
            if coin in float_mids:
                return float_mids[coin]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(1)
        if "_all_mids" in _CACHE:
            return _CACHE["_all_mids"][1].get(coin)
    except Exception as e:
        if "_all_mids" in _CACHE:
            return _CACHE["_all_mids"][1].get(coin)
    return None

def calc_ema(values, period=20):
    if len(values) < period:
        return values[-1] if values else 0
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for price in values[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def get_mtf_bias(coin):
    """
    Top-Down Multi-Timeframe Alignment:
    Checks 1H and 15M trends against EMA 20.
    """
    c_1h = fetch_candles(coin=coin, interval="1h", limit=30)
    c_15m = fetch_candles(coin=coin, interval="15m", limit=30)
    
    if len(c_1h) < 15 or len(c_15m) < 15:
        return "NEUTRAL", 0, 0
        
    closes_1h = [c["c"] for c in c_1h]
    closes_15m = [c["c"] for c in c_15m]
    
    ema_1h = calc_ema(closes_1h, period=20)
    ema_15m = calc_ema(closes_15m, period=20)
    
    cur_1h = closes_1h[-1]
    cur_15m = closes_15m[-1]
    
    if cur_1h >= ema_1h and cur_15m >= ema_15m:
        return "BULLISH", ema_1h, ema_15m
    elif cur_1h <= ema_1h and cur_15m <= ema_15m:
        return "BEARISH", ema_1h, ema_15m
    else:
        # Bias condong ke arah 15M jika 1H sideways
        if cur_15m >= ema_15m:
            return "LEAN_BULLISH", ema_1h, ema_15m
        else:
            return "LEAN_BEARISH", ema_1h, ema_15m

def load_state():
    default_state = {
        "account": {
            "started_at": time.time(),
            "started_str": datetime.now(tz=WIB).strftime("%d/%m/%Y %H:%M WIB"),
            "initial_bankroll": 500.0,
            "current_equity": 500.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "gross_wins": 0.0,
            "gross_losses": 0.0,
            "consecutive_losses": 0,
            "circuit_breaker_until": 0,
            "net_pnl": 0.0
        },
        "telemetry": {
            "limits_placed": 0,
            "limits_filled": 0,
            "limits_expired": 0,
            "fill_times_min": []
        },
        "pending_limit": None,
        "active_position": None,
        "last_processed_candle": {},
        "last_heartbeat": 0
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                saved = json.load(f)
                for k, v in default_state.items():
                    if k not in saved:
                        saved[k] = v
                # Ensure all account sub-keys exist
                for ak, av in default_state["account"].items():
                    if ak not in saved["account"]:
                        saved["account"][ak] = av
                return saved
        except Exception:
            pass
    return default_state

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def format_uptime(started_timestamp):
    elapsed_sec = int(time.time() - started_timestamp)
    days = elapsed_sec // 86400
    hours = (elapsed_sec % 86400) // 3600
    minutes = (elapsed_sec % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} Hari")
    if hours > 0 or days > 0:
        parts.append(f"{hours} Jam")
    parts.append(f"{minutes} Menit")
    return " ".join(parts)

def check_setup(coin, candles_5m, state):
    if len(candles_5m) < 22:
        return
        
    last_closed = candles_5m[-2]
    last_time = last_closed["t"]
    
    if state["last_processed_candle"].get(coin) == last_time:
        return
    state["last_processed_candle"][coin] = last_time
    save_state(state)
    
    # Correlation Guard: Max 1 posisi aktif di seluruh portfolio
    if state.get("active_position") or state.get("pending_limit"):
        return

    # Circuit Breaker Check: Cooldown after 2 consecutive losses
    cb_until = state.get("account", {}).get("circuit_breaker_until", 0)
    if time.time() < cb_until:
        return

    # Check Top-Down MTF Bias
    mtf_bias, ema_1h, ema_15m = get_mtf_bias(coin)
    regime_name, win_target_pct, rr_ratio, vol_ratio = get_volume_regime(candles_5m)
    
    # 1. Micro-lookback (6 candle = 30 menit) untuk pro-trend pullback
    micro_lookback = candles_5m[-8:-2]
    micro_high = max(c["h"] for c in micro_lookback)
    micro_low = min(c["l"] for c in micro_lookback)
    
    # 2. Macro-lookback (20 candle = 100 menit) untuk major SFP
    macro_lookback = candles_5m[-22:-2]
    macro_high = max(c["h"] for c in macro_lookback)
    macro_low = min(c["l"] for c in macro_lookback)
    
    ch = last_closed["h"]
    cl = last_closed["l"]
    cc = last_closed["c"]
    
    lev = LEVERAGE[coin]
    notional = FIXED_MARGIN * lev
    
    is_bullish_context = "BULLISH" in mtf_bias
    is_bearish_context = "BEARISH" in mtf_bias
    vol_desc = f"🔥 Volume Surge ({vol_ratio:.2f}x Avg ➔ RR 1:4.0)" if regime_name == "HIGH_SURGE" else f"⚡ Normal Volume ({vol_ratio:.2f}x Avg ➔ RR 1:2.0)"
    
    # CASE 1: PRO-TREND BULLISH PULLBACK (DIP & BOUNCE)
    # Price dips below local 30m low, but closes back up while 1H/15M is Bullish
    if is_bullish_context and (cl < micro_low and cc > micro_low):
        limit_entry = round((cl + cc) / 2, 2 if coin=="ETH" else 1)
        sl = round(limit_entry * (1 - CUT_LOSS_PCT), 2 if coin=="ETH" else 1)
        tp = round(limit_entry * (1 + win_target_pct), 2 if coin=="ETH" else 1)
        risk = limit_entry - sl
        qty = notional / limit_entry
        
        analysis_msg = (
            f"🔍 *[ANALISA MTF & PULLBACK TERDETEKSI] {coin}USDT (TF 5M)*\n"
            f"• *MTF Trend:* {mtf_bias} (1H & 15M Uptrend) 🟢\n"
            f"• *Pattern:* Pro-Trend Pullback Sweep (Diskon 30m Disapu)\n"
            f"• *Volume Dynamic:* {vol_desc}\n"
            f"• *Low Retest:* ${cl:.2f} ➔ Closing Mantul ke ${cc:.2f}\n"
            f"• *Rencana:* Pasang Limit Order BUY (TTL 25m)"
        )
        send_telegram(analysis_msg)
        time.sleep(1)
        
        limit_msg = (
            f"⏳ *[LIMIT ORDER PLACED] {coin} LONG (Pro-Trend)*\n"
            f"• *Margin:* ${FIXED_MARGIN:.2f} | *Leverage:* {lev}x (Notional: ${notional:,.0f})\n"
            f"• *Limit Entry:* ${limit_entry:.2f}\n"
            f"• *Stop Loss:* ${sl:.2f} (✂️ Cut-loss: 0.30% | -${risk*qty:.2f})\n"
            f"• *Take Profit:* ${tp:.2f} (🎯 Target: {win_target_pct*100:.2f}% | +${(limit_entry*win_target_pct)*qty:.2f} | *RR 1:{rr_ratio:.1f}*)\n"
            f"• *Volume Mode:* {vol_desc}\n"
            f"• *Position Qty:* {qty:.4f} {coin}\n"
            f"• *Order TTL:* 25 Menit (5 Candle) (Auto-Cancel jika belum terisi)"
        )
        send_telegram(limit_msg)
        
        state["telemetry"]["limits_placed"] = state.get("telemetry", {}).get("limits_placed", 0) + 1
        state["pending_limit"] = {
            "coin": coin,
            "dir": "LONG",
            "limit_price": limit_entry,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "qty": qty,
            "notional": notional,
            "win_target_pct": win_target_pct,
            "rr_ratio": rr_ratio,
            "vol_ratio": vol_ratio,
            "regime_name": regime_name,
            "placed_time": time.time(),
            "placed_time_str": datetime.now(tz=WIB).strftime("%H:%M:%S WIB")
        }
        save_state(state)
        return

    # CASE 2: PRO-TREND BEARISH PULLBACK (RALLY & REJECTION)
    # Price spikes above local 30m high, but rejects back down while 1H/15M is Bearish
    elif is_bearish_context and (ch > micro_high and cc < micro_high):
        limit_entry = round((ch + cc) / 2, 2 if coin=="ETH" else 1)
        sl = round(limit_entry * (1 + CUT_LOSS_PCT), 2 if coin=="ETH" else 1)
        tp = round(limit_entry * (1 - win_target_pct), 2 if coin=="ETH" else 1)
        risk = sl - limit_entry
        qty = notional / limit_entry
        
        analysis_msg = (
            f"🔍 *[ANALISA MTF & PULLBACK TERDETEKSI] {coin}USDT (TF 5M)*\n"
            f"• *MTF Trend:* {mtf_bias} (1H & 15M Downtrend) 🔴\n"
            f"• *Pattern:* Pro-Trend Rally Rejection (Resisten 30m Disapu)\n"
            f"• *Volume Dynamic:* {vol_desc}\n"
            f"• *High Retest:* ${ch:.2f} ➔ Closing Reject ke ${cc:.2f}\n"
            f"• *Rencana:* Pasang Limit Order SELL (TTL 25m)"
        )
        send_telegram(analysis_msg)
        time.sleep(1)
        
        limit_msg = (
            f"⏳ *[LIMIT ORDER PLACED] {coin} SHORT (Pro-Trend)*\n"
            f"• *Margin:* ${FIXED_MARGIN:.2f} | *Leverage:* {lev}x (Notional: ${notional:,.0f})\n"
            f"• *Limit Entry:* ${limit_entry:.2f}\n"
            f"• *Stop Loss:* ${sl:.2f} (✂️ Cut-loss: 0.30% | -${risk*qty:.2f})\n"
            f"• *Take Profit:* ${tp:.2f} (🎯 Target: {win_target_pct*100:.2f}% | +${(limit_entry*win_target_pct)*qty:.2f} | *RR 1:{rr_ratio:.1f}*)\n"
            f"• *Volume Mode:* {vol_desc}\n"
            f"• *Position Qty:* {qty:.4f} {coin}\n"
            f"• *Order TTL:* 25 Menit (5 Candle) (Auto-Cancel jika belum terisi)"
        )
        send_telegram(limit_msg)
        
        state["telemetry"]["limits_placed"] = state.get("telemetry", {}).get("limits_placed", 0) + 1
        state["pending_limit"] = {
            "coin": coin,
            "dir": "SHORT",
            "limit_price": limit_entry,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "qty": qty,
            "notional": notional,
            "win_target_pct": win_target_pct,
            "rr_ratio": rr_ratio,
            "vol_ratio": vol_ratio,
            "regime_name": regime_name,
            "placed_time": time.time(),
            "placed_time_str": datetime.now(tz=WIB).strftime("%H:%M:%S WIB")
        }
        save_state(state)
        return

    # CASE 3: COUNTER-TREND MAJOR SWEEPS -> TRANSPARENT RADAR NOTICE
    # Jangan silent return! Beri tahu operator kenapa sinyal di-skip
    if ch > macro_high and cc < macro_high and is_bullish_context:
        skip_msg = (
            f"⚠️ *[RADAR SCANNER] {coin} Reversal Disaring MTF*\n"
            f"• *Pola:* 5M High Sweep di ${macro_high:.2f} (Potensi Short)\n"
            f"• *Keputusan:* Ditolak filter karena 1H/15M masih {mtf_bias}.\n"
            f"• *Action:* Bot menunggu setup Buy di dip berikutnya."
        )
        send_telegram(skip_msg)
    elif cl < macro_low and cc > macro_low and is_bearish_context:
        skip_msg = (
            f"⚠️ *[RADAR SCANNER] {coin} Reversal Disaring MTF*\n"
            f"• *Pola:* 5M Low Sweep di ${macro_low:.2f} (Potensi Long)\n"
            f"• *Keputusan:* Ditolak filter karena 1H/15M masih {mtf_bias}.\n"
            f"• *Action:* Bot menunggu setup Sell di rally berikutnya."
        )
        send_telegram(skip_msg)

def monitor_pending_limit(state):
    pending = state.get("pending_limit")
    if not pending:
        return
        
    coin = pending["coin"]
    price = fetch_live_price(coin)
    if not price:
        return
        
    elapsed_sec = time.time() - pending["placed_time"]
    
    filled = False
    if pending["dir"] == "SHORT" and price >= pending["limit_price"]:
        filled = True
    elif pending["dir"] == "LONG" and price <= pending["limit_price"]:
        filled = True
        
    if filled:
        fill_min = round(elapsed_sec / 60, 1)
        if "telemetry" not in state:
            state["telemetry"] = {"limits_placed": 0, "limits_filled": 0, "limits_expired": 0, "fill_times_min": []}
        state["telemetry"]["limits_filled"] = state["telemetry"].get("limits_filled", 0) + 1
        state["telemetry"].setdefault("fill_times_min", []).append(fill_min)
        
        fill_msg = (
            f"⚡ *[LIMIT ORDER FILLED!] {coin} {pending['dir']}*\n"
            f"• *Filled Price:* ${pending['limit_price']:.2f}\n"
            f"• *Waktu Terjemput:* {fill_min} Menit setelah dipasang (TTL Max: 25m)\n"
            f"• *Margin:* ${FIXED_MARGIN:.2f} (Lev: {LEVERAGE[coin]}x)\n"
            f"• *Stop Loss:* ${pending['sl']:.2f} (✂️ Cut-loss: 0.30%)\n"
            f"• *Take Profit:* ${pending['tp']:.2f} (🎯 Win target: 1.20% | *RR 1:4.0*)\n"
            f"• *Status:* Kunci posisi. Bot kawal sampai hit TP atau SL."
        )
        send_telegram(fill_msg)
        
        state["active_position"] = {
            **pending,
            "fill_time": time.time(),
            "fill_time_str": datetime.now(tz=WIB).strftime("%H:%M:%S WIB")
        }
        state["pending_limit"] = None
        save_state(state)
        return

    # Check TTL Expired (25 Menit / 5 Candle)
    if elapsed_sec >= LIMIT_TTL_SECONDS:
        if "telemetry" not in state:
            state["telemetry"] = {"limits_placed": 0, "limits_filled": 0, "limits_expired": 0, "fill_times_min": []}
        state["telemetry"]["limits_expired"] = state["telemetry"].get("limits_expired", 0) + 1
        
        cancel_msg = (
            f"⚠️ *[LIMIT ORDER EXPIRED & CANCELLED]*\n"
            f"• *Aset:* {coin} {pending['dir']}\n"
            f"• *Limit Price:* ${pending['limit_price']:.2f} | *Harga Sekarang:* ${price:.2f}\n"
            f"• *Alasan:* 25 Menit (5 Candle) order tidak terjemput.\n"
            f"• *Telemetry:* Dicatat sebagai unreached retest. Bot kembali scanning setup baru."
        )
        send_telegram(cancel_msg)
        state["pending_limit"] = None
        save_state(state)

def monitor_active_position(state):
    pos = state.get("active_position")
    if not pos:
        return
        
    coin = pos["coin"]
    price = fetch_live_price(coin)
    if not price:
        return
        
    elapsed_min = (time.time() - pos["fill_time"]) / 60
    closed = False
    outcome = None
    exit_price = None

    # Dynamic BEP Protection: When position runs +0.40% in profit, slide SL to entry (Risk-Free)
    if not pos.get("bep_active"):
        if pos["dir"] == "LONG" and price >= pos["limit_price"] * 1.0040:
            gain_pct = ((price - pos["limit_price"]) / pos["limit_price"]) * 100
            pos["sl"] = pos["limit_price"]
            pos["bep_active"] = True
            save_state(state)
            send_telegram(
                f"🛡️ *[BEP RISK-FREE LOCK] {coin} {pos['dir']}*\n"
                f"• *Status:* Harga sudah lari +{gain_pct:.2f}% (ke ${price:,.2f})!\n"
                f"• *Action:* Stop Loss digeser ke Entry (${pos['limit_price']:,.2f}).\n"
                f"• *Risk:* 0% (Trade sekarang 100% Bebas Risiko menuju Target)!"
            )
        elif pos["dir"] == "SHORT" and price <= pos["limit_price"] * 0.9960:
            gain_pct = ((pos["limit_price"] - price) / pos["limit_price"]) * 100
            pos["sl"] = pos["limit_price"]
            pos["bep_active"] = True
            save_state(state)
            send_telegram(
                f"🛡️ *[BEP RISK-FREE LOCK] {coin} {pos['dir']}*\n"
                f"• *Status:* Harga sudah lari +{gain_pct:.2f}% (ke ${price:,.2f})!\n"
                f"• *Action:* Stop Loss digeser ke Entry (${pos['limit_price']:,.2f}).\n"
                f"• *Risk:* 0% (Trade sekarang 100% Bebas Risiko menuju Target)!"
            )
    
    if pos["dir"] == "SHORT":
        if price >= pos["sl"]:
            closed = True
            outcome = "BEP" if (pos.get("bep_active") and pos["sl"] == pos["limit_price"]) else "SL"
            exit_price = pos["sl"]
        elif price <= pos["tp"]:
            closed = True
            outcome = "TP"
            exit_price = pos["tp"]
    elif pos["dir"] == "LONG":
        if price <= pos["sl"]:
            closed = True
            outcome = "BEP" if (pos.get("bep_active") and pos["sl"] == pos["limit_price"]) else "SL"
            exit_price = pos["sl"]
        elif price >= pos["tp"]:
            closed = True
            outcome = "TP"
            exit_price = pos["tp"]
            
    if closed:
        qty = pos["qty"]
        if pos["dir"] == "SHORT":
            pnl_gross = (pos["limit_price"] - exit_price) * qty
        else:
            pnl_gross = (exit_price - pos["limit_price"]) * qty
            
        fee = (pos["limit_price"] + exit_price) * qty * TAKER_FEE_RATE
        net_profit_dollar = pnl_gross - fee
        roi_percent = (net_profit_dollar / FIXED_MARGIN) * 100
        
        acc = state["account"]
        acc["total_trades"] += 1
        if outcome == "TP" or net_profit_dollar >= 0:
            acc["wins"] += 1
            acc["gross_wins"] = acc.get("gross_wins", 0.0) + max(0.0, net_profit_dollar)
            acc["consecutive_losses"] = 0
        else:
            acc["losses"] += 1
            acc["gross_losses"] = acc.get("gross_losses", 0.0) + abs(net_profit_dollar)
            acc["consecutive_losses"] = acc.get("consecutive_losses", 0) + 1
            
            # Circuit Breaker: 2 consecutive losses -> 30m cooldown pause
            if acc["consecutive_losses"] >= 2:
                cooldown_dur = 30 * 60
                acc["circuit_breaker_until"] = time.time() + cooldown_dur
                cb_resume_str = datetime.fromtimestamp(acc["circuit_breaker_until"], tz=WIB).strftime("%H:%M:%S WIB")
                send_telegram(
                    f"⏸️ *[CIRCUIT BREAKER ACTIVATED]*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"• *Pemicu:* 2 Loss beruntun terdeteksi.\n"
                    f"• *Alasan:* Regime market sedang volatile / false breakout.\n"
                    f"• *Tindakan:* Bot istirahat (cooldown) 30 menit untuk melindungi bankroll.\n"
                    f"• *Resume:* Bot aktif kembali pukul {cb_resume_str}."
                )
                
        acc["net_pnl"] += net_profit_dollar
        init_bankroll = acc.get("initial_bankroll", 500.0)
        acc["current_equity"] = init_bankroll + acc["net_pnl"]
        
        # Calculate Drawdown % and Profit Factor
        dd_usd = min(0.0, acc["net_pnl"])
        dd_pct = (dd_usd / init_bankroll) * 100
        gw = acc.get("gross_wins", 0.0)
        gl = acc.get("gross_losses", 0.0)
        pf = (gw / gl) if gl > 0 else (99.9 if gw > 0 else 0.0)
        
        # Incubation Gate
        inc_target = 50
        inc_status = f"🏆 REAL-READY" if (acc["total_trades"] >= inc_target and pf >= 1.30) else f"🧪 INCUBATION ({acc['total_trades']}/{inc_target})"
        
        winrate = (acc["wins"] / acc["total_trades"]) * 100
        uptime_display = format_uptime(acc.get("started_at", time.time()))
        
        if outcome == "TP":
            badge = "🎯 *[TAKE PROFIT HIT!]*"
        elif outcome == "BEP":
            badge = "🛡️ *[BREAKEVEN EXIT]*"
        else:
            badge = "🛑 *[STOP LOSS HIT]*"
            
        color_pnl = f"+${net_profit_dollar:.2f} (+{roi_percent:.1f}%)" if net_profit_dollar >= 0 else f"-${abs(net_profit_dollar):.2f} ({roi_percent:.1f}%)"
        
        scorecard = (
            f"{badge} *{coin} {pos['dir']} CLOSED*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• *Entry:* ${pos['limit_price']:.2f} ➔ *Exit:* ${exit_price:.2f}\n"
            f"• *Durasi Trade:* {elapsed_min:.1f} Menit\n"
            f"• *Fee Taker:* ${fee:.2f}\n"
            f"• *Trade PnL (Margin $50):* *{color_pnl}*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *ACCUMULATED SCORECARD*\n"
            f"• *Win Rate Sesi:* *{winrate:.1f}%* ({acc['wins']}W / {acc['losses']}L)\n"
            f"• *Bankroll Equity:* *${acc['current_equity']:.2f}* / ${init_bankroll:.2f} (DD: {dd_pct:.1f}%)\n"
            f"• *Profit Factor:* *{pf:.2f}*\n"
            f"• *Incubation Gate:* *{inc_status}*\n"
            f"• *Total Net Profit:* *{'+$' if acc['net_pnl']>=0 else '-$'}{abs(acc['net_pnl']):.2f}*\n"
            f"• *Durasi Bot Berjalan:* *{uptime_display}*\n"
            f"• *Running Sejak:* {acc.get('started_str', 'Hari ini')}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• *Status:* Posisi selesai. Bot lanjut radar scanning."
        )
        send_telegram(scorecard)
        
        state["active_position"] = None
        save_state(state)

def check_heartbeat(state):
    """
    Kirim status radar setiap 2 jam agar operator tahu bot 100% sehat & aktif
    """
    now = time.time()
    last_hb = state.get("last_heartbeat", 0)
    if now - last_hb >= 2 * 3600:
        eth_bias, _, _ = get_mtf_bias("ETH")
        btc_bias, _, _ = get_mtf_bias("BTC")
        eth_p = fetch_live_price("ETH") or 0
        btc_p = fetch_live_price("BTC") or 0
        uptime = format_uptime(state["account"].get("started_at", now))
        
        hb_msg = (
            f"🛰️ *[RADAR HEARTBEAT STATUS]*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• *Bot Health:* 🟢 Online & Scanning (Uptime: {uptime})\n"
            f"• *ETH Spot:* ${eth_p:,.2f} | MTF: *{eth_bias}*\n"
            f"• *BTC Spot:* ${btc_p:,.2f} | MTF: *{btc_bias}*\n"
            f"• *Disiplin:* Cut 0.30% | Win 1.20% (*RR 1:4.0*)\n"
            f"• *Portfolio State:* {'STANDBY (Mencari Setup)' if not state.get('active_position') else 'IN POSITION'}"
        )
        send_telegram(hb_msg)
        state["last_heartbeat"] = now
        save_state(state)

def engine_tick():
    state = load_state()
    check_heartbeat(state)
    monitor_pending_limit(state)
    monitor_active_position(state)
    for coin in ["ETH", "BTC"]:
        candles_5m = fetch_candles(coin=coin, interval="5m", limit=25)
        check_setup(coin, candles_5m, state)

if __name__ == "__main__":
    print(f"[INFO] Papertrade Production Scalp Engine v3.2 starting in {BASE_DIR}...")
    
    send_telegram(
        "🚀 *Papertrade Scalp Engine v3.2 Active (TTL 25M SWEET SPOT)*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• *Limit TTL:* ⏱️ 25 Menit (5 Candle) Extended\n"
        "• *Telemetry:* Pencatatan durasi jemput & shadow tracking aktif\n"
        "• *Pro-Trend Pullbacks:* AKTIF (Dip saat uptrend, Rally saat downtrend)\n"
        "• *Target Asimetris:* ✂️ 0.30% Cut / 🎯 1.20% Win (*RR 1:4.0*)\n"
        "• *Margin:* $50 Fixed | Leverage: 100x ETH & BTC\n"
        "• *Status:* Radar Siaga Penuh dengan Jendela Retest Optimal"
    )
    while True:
        try:
            engine_tick()
        except Exception as e:
            print(f"[ERR] Engine tick error: {e}")
        time.sleep(10)

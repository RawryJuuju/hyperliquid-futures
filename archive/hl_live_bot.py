#!/usr/bin/env python3
"""
Hyperliquid REAL Futures Bot — Strategy Q4 (validated)
======================================================
Strategi : Pro-trend pullback sweep (5m entry, 15m+1h trend gate)
Entry    : limit di 50% retrace candle sweep
SL       : ATR(14) x 1.0 dari entry
TP       : 2.0R
BE       : geser SL ke entry saat +1.0R
Filter   : 1h slope + trend strength >=1.0 ATR + body ratio >=0.45
Instrument: ETH saja (BTC tidak lolos validasi)
Max hold : 60 bar 5m (5 jam)

Order dikirim SUNGGUHAN ke Hyperliquid. SL & TP dipasang sebagai
trigger order reduce-only di exchange, jadi tetap jalan walau bot mati.
"""
import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/papertrade_backtest"
STATE_FILE = os.path.join(BASE_DIR, "hl_live_state.json")
TRADE_LOG = os.path.join(BASE_DIR, "hl_trades.jsonl")
KILL_SWITCH = os.path.join(BASE_DIR, "STOP_TRADING")
KEY_FILE = "/home/ubuntu/credentials/pk_2897.txt"

NETWORK = os.environ.get("HL_NETWORK", "testnet")
BASE_URL = ("https://api.hyperliquid-testnet.xyz" if NETWORK == "testnet"
            else "https://api.hyperliquid.xyz")

# ==== RISK PARAMETERS ====
COIN = "ETH"
MARGIN_USD = 50.0          # margin per posisi
LEVERAGE = 3               # 3x -> notional $150, liq jauh
MAX_NOTIONAL = 200.0
MAX_OPEN = 1
DAILY_LOSS_CAP = 30.0      # stop kalau rugi hari ini > $30
SL_ATR_MULT = 1.0
RR = 2.0
BE_AT_R = 1.0
MAX_HOLD_BARS = 60
TTL_BARS = 20              # limit order expiry (20 x 5m = 100 menit)
MIN_BODY = 0.45
MIN_STRENGTH = 1.0

sys.path.insert(0, os.path.join(BASE_DIR, ".venv", "lib", "python3.12", "site-packages"))


def now_wib():
    return datetime.now(tz=WIB)


def log(msg):
    print(f"[{now_wib().strftime('%H:%M:%S')}] {msg}", flush=True)


def post_info(payload):
    req = urllib.request.Request(
        f"{BASE_URL}/info",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def get_candles(coin, interval, limit=120):
    step_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}[interval]
    start = int(time.time() * 1000) - limit * step_ms
    raw = post_info({"type": "candleSnapshot",
                     "req": {"coin": coin, "interval": interval, "startTime": start}})
    return [{"t": k["t"], "o": float(k["o"]), "h": float(k["h"]),
             "l": float(k["l"]), "c": float(k["c"]), "v": float(k["v"])} for k in raw]


def get_mid(coin):
    m = post_info({"type": "allMids"}).get(coin)
    return float(m) if m else None


def ema(vals, period):
    if len(vals) < period:
        return None
    k = 2 / (period + 1)
    e = sum(vals[:period]) / period
    for v in vals[period:]:
        e = v * k + e * (1 - k)
    return e


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {
        "day": now_wib().strftime("%Y-%m-%d"),
        "day_pnl": 0.0,
        "trades_today": 0,
        "pending": None,          # limit order menunggu fill
        "position": None,         # posisi aktif
        "last_bar": None,
        "consec_loss": 0,
        "cooldown_until": 0,
    }


def save_state(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, STATE_FILE)


def get_exchange():
    from hyperliquid.exchange import Exchange
    from eth_account import Account
    key = open(KEY_FILE).read().strip()
    acct = Account.from_key(key)
    exch = Exchange(acct, BASE_URL, account_address=acct.address)
    return exch, acct.address


def account_value(address):
    st = post_info({"type": "clearinghouseState", "user": address})
    return float(st.get("marginSummary", {}).get("accountValue", 0) or 0), st


def tg(msg):
    try:
        tok = open("/home/ubuntu/credentials/gweilovejuujubot_bot_tele_token.txt").read().strip()
        payload = json.dumps({"chat_id": "1341231370", "text": msg,
                              "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                     data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        log(f"telegram err: {e}")


# ============================================================
#  SIGNAL
# ============================================================
def evaluate_signal():
    """Return dict signal atau None. Pakai candle 5m yang SUDAH CLOSED."""
    c5 = get_candles(COIN, "5m", 120)
    c15 = get_candles(COIN, "15m", 60)
    c1h = get_candles(COIN, "1h", 60)
    if len(c5) < 60 or len(c15) < 25 or len(c1h) < 55:
        return None, "data kurang"

    cur = c5[-2]  # last closed
    a = atr(c5[:-1], 14)
    if not a:
        return None, "atr n/a"

    closes15 = [x["c"] for x in c15[:-1]]
    closes1h = [x["c"] for x in c1h[:-1]]
    e15 = ema(closes15, 20)
    e1h = ema(closes1h, 20)
    e1h50 = ema(closes1h, 50)
    if None in (e15, e1h, e1h50):
        return None, "ema n/a"

    up15 = closes15[-1] > e15
    up1h = closes1h[-1] > e1h
    slope_up = e1h > e1h50
    strength = abs(closes1h[-1] - e1h) / a

    if strength < MIN_STRENGTH:
        return None, f"trend lemah ({strength:.2f} ATR)"

    rng = c5[-8:-2]
    lh = max(x["h"] for x in rng)
    ll = min(x["l"] for x in rng)

    body = abs(cur["c"] - cur["o"])
    rngc = max(cur["h"] - cur["l"], 1e-9)
    if body / rngc < MIN_BODY:
        return None, f"body kecil ({body/rngc:.2f})"

    direction = None
    if cur["l"] < ll and cur["c"] > ll and up15 and up1h and slope_up:
        direction = "long"
    elif cur["h"] > lh and cur["c"] < lh and (not up15) and (not up1h) and (not slope_up):
        direction = "short"
    if not direction:
        return None, "tidak ada sweep searah tren"

    entry = (cur["l"] + cur["c"]) / 2 if direction == "long" else (cur["h"] + cur["c"]) / 2
    sl_dist = a * SL_ATR_MULT
    sl = entry - sl_dist if direction == "long" else entry + sl_dist
    tp = entry + sl_dist * RR if direction == "long" else entry - sl_dist * RR

    if sl_dist / entry > 0.02:
        return None, "SL terlalu lebar (>2%)"
    if sl_dist / entry < 0.0012:
        return None, "SL terlalu sempit"

    return {
        "direction": direction,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "risk_px": round(sl_dist, 4),
        "atr": round(a, 4),
        "strength": round(strength, 2),
        "bar_t": cur["t"],
        "bar_time": datetime.fromtimestamp(cur["t"] / 1000, tz=WIB).strftime("%H:%M WIB"),
    }, "ok"


# ============================================================
#  EXECUTION
# ============================================================
def submit_limit(sig, state):
    """Pasang limit entry di exchange. SL/TP menyusul setelah fill."""
    exch, address = get_exchange()
    ai = next((x for x in post_info({"type": "meta"})["universe"]
               if x["name"] == COIN), None)
    if not ai:
        return False, "coin tidak ada"
    sz_dec = ai["szDecimals"]

    notional = MARGIN_USD * LEVERAGE
    if notional > MAX_NOTIONAL:
        return False, f"notional {notional} > cap {MAX_NOTIONAL}"
    sz = round(notional / sig["entry"], sz_dec)
    if sz <= 0:
        return False, "size 0"

    try:
        exch.update_leverage(LEVERAGE, COIN, is_cross=True)
    except Exception as e:
        log(f"leverage warn: {e}")

    is_buy = sig["direction"] == "long"
    try:
        res = exch.order(
            COIN, is_buy, sz, sig["entry"],
            {"limit": {"tif": "Gtc"}},
            reduce_only=False,
        )
    except Exception as e:
        return False, f"order exc: {e}"

    if res.get("status") != "ok":
        return False, f"order rejected: {res}"

    oid = None
    try:
        oid = res["response"]["data"]["statuses"][0]["resting"]["oid"]
    except Exception:
        pass

    state["pending"] = {
        "direction": sig["direction"],
        "entry": sig["entry"],
        "sl": sig["sl"],
        "tp": sig["tp"],
        "size": sz,
        "oid": oid,
        "placed_ts": time.time(),
        "bar_t": sig["bar_t"],
        "risk_px": sig["risk_px"],
    }
    save_state(state)

    log(f"LIMIT PLACED {sig['direction']} {COIN} sz={sz} @ {sig['entry']} oid={oid}")
    tg(f"📥 *LIMIT PLACED* {COIN} {sig['direction'].upper()}\n"
       f"• Entry : ${sig['entry']:,.2f}\n"
       f"• SL    : ${sig['sl']:,.2f} ({sig['risk_px']:.2f} = {sig['risk_px']/sig['entry']*100:.2f}%)\n"
       f"• TP    : ${sig['tp']:,.2f} (RR 1:{RR:.1f})\n"
       f"• Size  : {sz} {COIN} (${notional:.0f} notional, {LEVERAGE}x)\n"
       f"• OID   : `{oid}`\n"
       f"• TTL   : {TTL_BARS*5} menit")
    return True, oid


def sync_pending(state):
    """Cek apakah limit sudah fill / expired. Kalau fill -> pasang SL & TP."""
    p = state.get("pending")
    if not p:
        return
    _, address = get_exchange()
    st = post_info({"type": "clearinghouseState", "user": address})
    positions = st.get("assetPositions", [])

    filled_pos = None
    for ap in positions:
        pos = ap["position"]
        if pos["coin"] == COIN and abs(float(pos["szi"])) > 0:
            filled_pos = pos
            break

    if filled_pos:
        log(f"FILLED {COIN} size={filled_pos['szi']} entry={filled_pos.get('entryPx')}")
        exch, _ = get_exchange()
        is_buy = p["direction"] == "long"
        close_buy = not is_buy
        sz = abs(float(filled_pos["szi"]))
        entry_px = float(filled_pos.get("entryPx") or p["entry"])

        # SL trigger (reduce only)
        try:
            sl_res = exch.order(COIN, close_buy, sz, p["sl"],
                                {"trigger": {"triggerPx": p["sl"], "isMarket": True, "tpsl": "sl"}},
                                reduce_only=True)
            log(f"SL order: {sl_res.get('status')}")
        except Exception as e:
            log(f"SL FAIL: {e}"); sl_res = {"status": "err", "error": str(e)}

        try:
            tp_res = exch.order(COIN, close_buy, sz, p["tp"],
                                {"trigger": {"triggerPx": p["tp"], "isMarket": True, "tpsl": "tp"}},
                                reduce_only=True)
            log(f"TP order: {tp_res.get('status')}")
        except Exception as e:
            log(f"TP FAIL: {e}"); tp_res = {"status": "err", "error": str(e)}

        state["position"] = {
            **p,
            "size": sz,
            "entry_px": entry_px,
            "filled_ts": time.time(),
            "be_done": False,
            "sl_oid": None,
            "tp_oid": None,
        }
        state["pending"] = None
        save_state(state)

        tg(f"⚡ *FILLED* {COIN} {p['direction'].upper()}\n"
           f"• Entry : ${entry_px:,.2f}\n"
           f"• Size  : {sz} {COIN}\n"
           f"• SL    : ${p['sl']:,.2f} ({sl_res.get('status')})\n"
           f"• TP    : ${p['tp']:,.2f} ({tp_res.get('status')})\n"
           f"• Status: bracket aktif di exchange (aman walau bot mati)")
        return

    # Expired?
    if time.time() - p["placed_ts"] > TTL_BARS * 300:
        log("limit expired, cancel")
        try:
            exch, _ = get_exchange()
            exch.cancel(COIN, int(p["oid"])) if p.get("oid") else None
        except Exception as e:
            log(f"cancel warn: {e}")
        tg(f"⚠️ *LIMIT EXPIRED* {COIN} {p['direction'].upper()} @ ${p['entry']:,.2f} — tidak kejemput, dibatalkan.")
        state["pending"] = None
        save_state(state)


def manage_position(state):
    """BE move + time exit + detect close."""
    pos = state.get("position")
    if not pos:
        return
    _, address = get_exchange()
    st = post_info({"type": "clearinghouseState", "user": address})

    live = None
    for ap in st.get("assetPositions", []):
        p = ap["position"]
        if p["coin"] == COIN and abs(float(p["szi"])) > 0:
            live = p
            break

    if not live:
        # posisi sudah tutup (kena SL/TP)
        pnl = float(st.get("marginSummary", {}).get("accountValue", 0) or 0)
        log(f"POSITION CLOSED. accountValue=${pnl:,.2f}")
        tg(f"🏁 *POSITION CLOSED* {COIN} {pos['direction'].upper()}\n"
           f"• Entry : ${pos['entry_px']:,.2f}\n"
           f"• SL/TP : ${pos['sl']:,.2f} / ${pos['tp']:,.2f}\n"
           f"• Account value sekarang: ${pnl:,.2f}\n"
           f"• Bot siap cari setup berikutnya.")
        with open(TRADE_LOG, "a") as f:
            f.write(json.dumps({"closed": now_wib().isoformat(), **pos, "acct": pnl}) + "\n")
        state["position"] = None
        save_state(state)
        return

    entry_px = float(pos["entry_px"])
    risk = pos["risk_px"]
    mark = float(live.get("positionValue", 0))
    # unrealized R
    upnl = float(live.get("unrealizedPnl", 0) or 0)
    r_now = upnl / (risk * pos["size"]) if risk and pos["size"] else 0

    if not pos.get("be_done") and r_now >= BE_AT_R:
        try:
            exch, _ = get_exchange()
            sz = abs(float(live["szi"]))
            close_buy = pos["direction"] == "short"
            # cancel old SL then place at BE
            exch.order(COIN, close_buy, sz, entry_px,
                       {"trigger": {"triggerPx": entry_px, "isMarket": True, "tpsl": "sl"}},
                       reduce_only=True)
            pos["be_done"] = True
            state["position"] = pos
            save_state(state)
            log(f"BE SET @ {entry_px}")
            tg(f"🛡️ *BREAKEVEN LOCK* {COIN} {pos['direction'].upper()}\n"
               f"• Posisi sudah +{r_now:.2f}R\n"
               f"• SL digeser ke entry ${entry_px:,.2f} — bebas risiko")
        except Exception as e:
            log(f"BE fail: {e}")

    # time exit
    bars_held = (time.time() - pos["filled_ts"]) / 300
    if bars_held > MAX_HOLD_BARS:
        log(f"TIME EXIT after {bars_held:.0f} bars")
        try:
            exch, _ = get_exchange()
            exch.market_close(COIN)
            tg(f"⏱️ *TIME EXIT* {COIN} — posisi ditutup setelah {bars_held:.0f} bar (>{MAX_HOLD_BARS*5} menit)")
        except Exception as e:
            log(f"close fail: {e}")


def daily_reset(state):
    today = now_wib().strftime("%Y-%m-%d")
    if state.get("day") != today:
        state["day"] = today
        state["day_pnl"] = 0.0
        state["trades_today"] = 0
        state["consec_loss"] = 0
        save_state(state)


def main_loop():
    log(f"=== HL REAL FUTURES BOT | {NETWORK.upper()} | {COIN} ===")
    if os.path.exists(KILL_SWITCH):
        log(f"KILL SWITCH aktif ({KILL_SWITCH}) — berhenti.")
        return

    state = load_state()
    daily_reset(state)
    _, address = get_exchange()
    av, _ = account_value(address)
    log(f"wallet {address} | accountValue ${av:,.2f}")

    if av <= 0:
        log("SALDO $0 — bot tidak bisa trade. Isi dulu / pakai faucet testnet.")
        tg(f"⛔ *BOT BERHENTI* — saldo {NETWORK} wallet `{address}` = $0.00\n"
           f"Isi dana dulu, lalu jalankan ulang.")
        return

    while True:
        try:
            if os.path.exists(KILL_SWITCH):
                log("kill switch terdeteksi, stop.")
                break
            daily_reset(state)

            if state.get("day_pnl", 0) <= -DAILY_LOSS_CAP:
                log(f"DAILY LOSS CAP tercapai (${state['day_pnl']:.2f}) — stop hari ini.")
                tg(f"🛑 *DAILY LOSS CAP* ${state['day_pnl']:.2f} — bot stop sampai besok.")
                break

            if time.time() < state.get("cooldown_until", 0):
                time.sleep(20)
                continue

            sync_pending(state)
            manage_position(state)

            if not state.get("pending") and not state.get("position"):
                sig, reason = evaluate_signal()
                if sig:
                    ok, info = submit_limit(sig, state)
                    if not ok:
                        log(f"submit gagal: {info}")
                else:
                    log(f"scan: {reason}")

            time.sleep(15)
        except KeyboardInterrupt:
            log("interrupted")
            break
        except Exception as e:
            log(f"ERR loop: {e}")
            time.sleep(20)


if __name__ == "__main__":
    main_loop()

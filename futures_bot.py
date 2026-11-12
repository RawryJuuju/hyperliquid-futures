#!/usr/bin/env python3
"""
Hyperliquid Futures Bot v4 — DUAL STRATEGY per coin
====================================================
Setiap koin bisa menjalankan 2 strategi sekaligus (paralel).
Hasil walk-forward: combined +242R vs single +173.6R (+39%).

Strategi tersedia:
  breakout    : close tembus channel N-bar, searah tren 15m+1h
  sweep_fade  : sweep level lalu close balik (liquidity grab reversal)
  bollinger   : fade sentuhan BB extreme saat volatilitas rendah

Mode: shadow (default) | live
"""
import os
import sys
import json
import time
import statistics
import urllib.request
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/papertrade_backtest"
STATE_FILE = os.path.join(BASE_DIR, "fut_state.json")
EQUITY_LOG = os.path.join(BASE_DIR, "equity_curve.jsonl")
TRADE_LOG = os.path.join(BASE_DIR, "fut_trades.jsonl")
CFG_FILE = os.path.join(BASE_DIR, "strategy_config.json")
KILL_SWITCH = os.path.join(BASE_DIR, "STOP_TRADING")
TG_TOKEN_FILE = "/home/ubuntu/credentials/gweilovejuujubot_bot_tele_token.txt"
TG_CHAT = "1341231370"
HL = "https://api.hyperliquid.xyz"

MODE = os.environ.get("FUT_MODE", "shadow").lower()
DISPLAY_MODE = "LIVE"

# Per-coin leverage: uniform 10x = liq distance 10% untuk semua
# SL terlebar 1.56% (WLD) -> buffer 6.4x, aman
LEVERAGE_MAP = {
    "PUMP": 10, "WLD": 10, "ZEC": 10, "ENA": 10, "NEAR": 10, "HYPE": 10,
    "ETH": 10, "SOL": 10, "XRP": 10,
    "ARB": 10, "INJ": 5,   # INJ max leverage 5x di Hyperliquid
}
LEVERAGE = 10  # default fallback

MAX_RISK_PCT_PRICE = 0.035      # SL max 3.5% (ATR kegedean -> skip)
MIN_RISK_PCT_PRICE = 0.0015     # SL min 0.15% (sanity only, bukan filter fee)
MAX_TOTAL_MARGIN_PCT = 0.60     # total margin semua posisi max 60% equity

_CACHE = {}


def now_wib():
    return datetime.now(tz=WIB)


def log(m):
    print(f"[{now_wib().strftime('%H:%M:%S')}] {m}", flush=True)


def tg(m):
    try:
        tok = open(TG_TOKEN_FILE).read().strip()
        p = json.dumps({"chat_id": TG_CHAT, "text": m, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                     data=p, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


def post_info(payload):
    req = urllib.request.Request(f"{HL}/info", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def candles(coin, interval, limit):
    key = f"{coin}_{interval}_{limit}"
    now = time.time()
    ttl = 20 if interval == "5m" else 90
    if key in _CACHE and now - _CACHE[key][0] < ttl:
        return _CACHE[key][1]
    step = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000}[interval]
    start = int(time.time() * 1000) - limit * step
    try:
        raw = post_info({"type": "candleSnapshot",
                         "req": {"coin": coin, "interval": interval, "startTime": start}})
        out = [{"t": k["t"], "o": float(k["o"]), "h": float(k["h"]),
                "l": float(k["l"]), "c": float(k["c"]), "v": float(k["v"])} for k in raw]
        _CACHE[key] = (now, out)
        return out
    except Exception:
        return _CACHE.get(key, (0, []))[1]


def mids():
    now = time.time()
    if "_mids" in _CACHE and now - _CACHE["_mids"][0] < 3:
        return _CACHE["_mids"][1]
    try:
        d = post_info({"type": "allMids"})
        _CACHE["_mids"] = (now, d)
        return d
    except Exception:
        return _CACHE.get("_mids", (0, {}))[1]


def mid(c):
    v = mids().get(c)
    return float(v) if v else None


def ema(vals, p):
    if len(vals) < p:
        return None
    k = 2 / (p + 1)
    e = sum(vals[:p]) / p
    for v in vals[p:]:
        e = v * k + e * (1 - k)
    return e


def atr(cs, p=14):
    if len(cs) < p + 1:
        return None
    trs = []
    for i in range(1, len(cs)):
        h, l, pc = cs[i]["h"], cs[i]["l"], cs[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-p:]) / p


def bollinger(closes, period, k):
    if len(closes) < period:
        return None, None
    w = closes[-period:]
    m = sum(w) / period
    sd = statistics.pstdev(w)
    return m + k * sd, m - k * sd


# ============================================================
#  STATE
# ============================================================
def load_cfg():
    return json.load(open(CFG_FILE))


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            s = json.load(open(STATE_FILE))
            s.setdefault("open", {})
            s.setdefault("stats", {})
            s.setdefault("last_bar", {})
            s.setdefault("equity", s.get("initial_equity", 1000.0))
            s.setdefault("peak_equity", s["equity"])
            s.setdefault("week_start_equity", s["equity"])
            s.setdefault("coin_cooldown", {})
            return s
        except Exception:
            pass
    return {"day": now_wib().strftime("%Y-%m-%d"),
            "week": now_wib().strftime("%Y-W%W"),
            "initial_equity": 1000.0, "equity": 1000.0, "peak_equity": 1000.0,
            "week_start_equity": 1000.0, "day_pnl": 0.0,
            "open": {}, "last_bar": {}, "stats": {}, "coin_cooldown": {},
            "consec_loss": 0, "cooldown_until": 0}


def save_state(s):
    tmp = STATE_FILE + ".tmp"
    json.dump(s, open(tmp, "w"), indent=2)
    os.replace(tmp, STATE_FILE)


def log_equity(s):
    with open(EQUITY_LOG, "a") as f:
        f.write(json.dumps({"t": now_wib().isoformat(), "equity": round(s["equity"], 2),
                            "open": len(s["open"])}) + "\n")


# ============================================================
#  SIGNAL ENGINES — masing-masing return (sig, reason)
# ============================================================
def _common(coin, tf="5m"):
    """Fetch candles untuk TF eksekusi + 2 TF di atasnya sebagai filter tren."""
    TF_UP = {"5m": ("15m", "1h"), "15m": ("1h", "4h"), "1h": ("4h", "1d")}
    up1, up2 = TF_UP.get(tf, ("15m", "1h"))
    LIM = {"5m": 120, "15m": 120, "1h": 120, "4h": 100, "1d": 80}
    ce = candles(coin, tf, LIM.get(tf, 120))
    c1 = candles(coin, up1, LIM.get(up1, 100))
    c2 = candles(coin, up2, LIM.get(up2, 80))
    if len(ce) < 60 or len(c1) < 25 or len(c2) < 25:
        return None
    return ce, c1, c2


def _trend(c1, c2, htf_ema):
    e1 = ema([x["c"] for x in c1[:-1]], htf_ema)
    e2 = ema([x["c"] for x in c2[:-1]], htf_ema)
    if None in (e1, e2):
        return None, None
    return c1[-2]["c"] > e1, c2[-2]["c"] > e2


def sig_breakout(coin, P):
    tf = P.get("timeframe", "5m")
    d = _common(coin, tf)
    if not d:
        return None, "data"
    ce, c1, c2 = d
    cur = ce[-2]
    a = atr(ce[:-1], 14)
    up1, up2 = _trend(c1, c2, P["htf_ema"])
    if a is None or up1 is None:
        return None, "ind"

    # REGIME FILTER: slope strength (backtest: +17.4R, PF 1.34 -> 1.43)
    slope_min = P.get("slope_min", 1.5)
    if slope_min:
        e2 = ema([x["c"] for x in c2[:-1]], P["htf_ema"])
        if e2 is None:
            return None, "ind"
        strength = abs(c2[-2]["c"] - e2) / a
        if strength < slope_min:
            return None, f"slope lemah {strength:.2f}"

    rng = ce[-2 - P["look"]:-2]
    hh = max(x["h"] for x in rng)
    ll = min(x["l"] for x in rng)
    body = abs(cur["c"] - cur["o"])
    rngc = max(cur["h"] - cur["l"], 1e-9)
    if body / rngc < P["min_body"]:
        return None, f"body {body/rngc:.2f}"

    dr = None
    if cur["c"] > hh and up1 and up2:
        dr = "LONG"
    elif cur["c"] < ll and not up1 and not up2:
        dr = "SHORT"
    if not dr:
        return None, "no breakout"

    entry = cur["c"]
    dist = a * P["atr_mult"]
    if dist / entry > MAX_RISK_PCT_PRICE:
        return None, "SL too wide"
    if dist / entry < MIN_RISK_PCT_PRICE:
        return None, f"SL too tight ({dist/entry*100:.2f}%)"
    sl = entry - dist if dr == "LONG" else entry + dist
    tp = entry + dist * P["rr"] if dr == "LONG" else entry - dist * P["rr"]
    return {"coin": coin, "dir": dr, "strategy": "breakout",
            "entry": round(entry, 8), "sl": round(sl, 8), "tp": round(tp, 8),
            "risk_px": round(dist, 8), "risk_pct": round(dist / entry * 100, 3),
            "rr": P["rr"], "hold": P["hold"], "bar_t": cur["t"]}, "ok"


def sig_sweep(coin, P):
    d = _common(coin)
    if not d:
        return None, "data"
    c5, c15, c1h = d
    cur = c5[-2]
    a = atr(c5[:-1], 14)
    up15, up1h = _trend(c15, c1h, P["htf_ema"])
    if a is None or up15 is None:
        return None, "ind"

    rng = c5[-2 - P["look"]:-2]
    hh = max(x["h"] for x in rng)
    ll = min(x["l"] for x in rng)
    body = abs(cur["c"] - cur["o"])
    rngc = max(cur["h"] - cur["l"], 1e-9)
    if body / rngc < P["min_body"]:
        return None, f"body {body/rngc:.2f}"

    dr = None
    if cur["l"] < ll and cur["c"] > ll and up15 and up1h:
        dr = "LONG"
    elif cur["h"] > hh and cur["c"] < hh and not up15 and not up1h:
        dr = "SHORT"
    if not dr:
        return None, "no sweep"

    entry = cur["c"]
    dist = a * P["atr_mult"]
    if dist / entry > MAX_RISK_PCT_PRICE:
        return None, "SL too wide"
    if dist / entry < MIN_RISK_PCT_PRICE:
        return None, f"SL too tight ({dist/entry*100:.2f}%)"
    sl = entry - dist if dr == "LONG" else entry + dist
    tp = entry + dist * P["rr"] if dr == "LONG" else entry - dist * P["rr"]
    return {"coin": coin, "dir": dr, "strategy": "sweep_fade",
            "entry": round(entry, 8), "sl": round(sl, 8), "tp": round(tp, 8),
            "risk_px": round(dist, 8), "risk_pct": round(dist / entry * 100, 3),
            "rr": P["rr"], "hold": P["hold"], "bar_t": cur["t"]}, "ok"


def sig_bollinger(coin, P):
    d = _common(coin)
    if not d:
        return None, "data"
    c5, c15, c1h = d
    cur = c5[-2]
    a = atr(c5[:-1], 14)
    if a is None:
        return None, "ind"

    closes = [x["c"] for x in c5[:-1]]
    upper, lower = bollinger(closes, P["bb_period"], P["bb_k"])
    if upper is None:
        return None, "bb n/a"

    # regime filter: ATR harus di bawah median 60 bar (ranging)
    recent = [x for x in [atr(c5[:i], 14) for i in range(max(15, len(c5)-60), len(c5)-1)] if x]
    if len(recent) < 20:
        return None, "atr hist"
    if a > statistics.median(recent) * P["atr_max_ratio"]:
        return None, "volatil (bukan ranging)"

    dr = None
    if cur["l"] < lower and cur["c"] > lower:
        dr = "LONG"
    elif cur["h"] > upper and cur["c"] < upper:
        dr = "SHORT"
    if not dr:
        return None, "no BB touch"

    entry = cur["c"]
    dist = a * P["atr_mult"]
    if dist / entry > MAX_RISK_PCT_PRICE:
        return None, "SL too wide"
    if dist / entry < MIN_RISK_PCT_PRICE:
        return None, f"SL too tight ({dist/entry*100:.2f}%)"
    sl = entry - dist if dr == "LONG" else entry + dist
    tp = entry + dist * P["rr"] if dr == "LONG" else entry - dist * P["rr"]
    return {"coin": coin, "dir": dr, "strategy": "bollinger",
            "entry": round(entry, 8), "sl": round(sl, 8), "tp": round(tp, 8),
            "risk_px": round(dist, 8), "risk_pct": round(dist / entry * 100, 3),
            "rr": P["rr"], "hold": P["hold"], "bar_t": cur["t"]}, "ok"


ENGINES = {"breakout": sig_breakout, "sweep_fade": sig_sweep,
           "bollinger": sig_bollinger}


# ============================================================
#  MONEY MANAGEMENT
# ============================================================
def current_risk_pct(state, cfg):
    rm = cfg["_risk_model"]
    base = rm["base_risk_pct"]
    peak = state.get("peak_equity", state["equity"])
    dd = (peak - state["equity"]) / peak * 100 if peak > 0 else 0
    if dd >= rm["reduce_after_dd_pct"]:
        base *= rm["reduce_factor"]
    return base


def can_open(state, coin, cfg, new_risk_pct):
    rm = cfg["_risk_model"]
    open_pos = state["open"]

    if len(open_pos) >= rm["max_concurrent"]:
        return False, f"max {rm['max_concurrent']} posisi"

    used = sum(p.get("risk_pct_equity", 0) for p in open_pos.values())
    if used + new_risk_pct > rm["max_total_open_risk_pct"]:
        return False, f"open risk {used:.2f}%+{new_risk_pct:.2f}% > {rm['max_total_open_risk_pct']}%"

    # total margin guard — cegah modal terkunci semua
    cur_margin = sum(p.get("margin", 0) for p in open_pos.values())
    max_margin = state["equity"] * MAX_TOTAL_MARGIN_PCT
    if cur_margin >= max_margin:
        return False, f"margin limit (${cur_margin:.0f}/${max_margin:.0f})"

    # correlation cluster — key adalah "COIN:strategy", ambil coin-nya
    cluster = cfg["coins"][coin]["cluster"]
    same = []
    for slot in open_pos:
        oc = open_pos[slot].get("coin") or slot.split(":")[0]
        if cfg["coins"].get(oc, {}).get("cluster") == cluster:
            same.append(oc)
    if len(same) >= cfg["_correlation_clusters"]["_max_per_cluster"]:
        return False, f"cluster {cluster} full ({len(same)}: {','.join(same)})"

    # BLOCK: koin sama + timeframe sama sudah ada posisi (cegah hedge sendiri)
    # Multi-TF: 5m dan 1h di coin sama BOLEH jalan bersamaan (beda horizon)
    new_tf = (state.get("_pending_tf") or "5m")
    for slot in open_pos:
        oc = open_pos[slot].get("coin") or slot.split(":")[0]
        otf = open_pos[slot].get("timeframe", "5m")
        if oc == coin and otf == new_tf:
            return False, f"{coin} {new_tf} sudah ada posisi ({open_pos[slot]['dir']} @ {slot})"

    # per-coin cooldown (setelah loss) — skip kalau dinonaktifkan
    cd_min = rm.get("coin_cooldown_min", 0)
    if cd_min > 0:
        cd = state.get("coin_cooldown", {}).get(coin, 0)
        if time.time() < cd:
            return False, f"{coin} cooldown"

    day_loss = state.get("day_pnl", 0.0)
    if day_loss <= -state["equity"] * rm["daily_loss_cap_pct"] / 100:
        return False, "daily cap"

    wse = state.get("week_start_equity", state["equity"])
    wk = (state["equity"] - wse) / wse * 100 if wse else 0
    if wk <= -rm["weekly_loss_cap_pct"]:
        return False, "weekly cap"

    if rm.get("consec_loss_trigger", 999) < 900:
        if time.time() < state.get("cooldown_until", 0):
            return False, "global cooldown"

    return True, "ok"


def size_position(state, sig, risk_pct_equity):
    equity = state["equity"]
    lev = LEVERAGE_MAP.get(sig["coin"], LEVERAGE)
    risk_usd = equity * risk_pct_equity / 100
    notional = risk_usd / (sig["risk_pct"] / 100)
    margin = notional / lev
    if margin > equity * 0.35:
        margin = equity * 0.35
        notional = margin * lev
        risk_usd = notional * (sig["risk_pct"] / 100)
    size = notional / sig["entry"]
    return {"risk_usd": round(risk_usd, 2), "notional": round(notional, 2),
            "margin": round(margin, 2), "size": round(size, 8),
            "leverage": lev,
            "risk_pct_equity": round(risk_usd / equity * 100, 4)}


# ============================================================
#  EXITS
# ============================================================
def check_exits(state, cfg):
    closed = []
    em = cfg.get("_exit_management", {})
    em_on = bool(em.get("enabled"))
    be_at = em.get("be_at_R")
    part_at = em.get("partial_at_R")
    part_frac = em.get("partial_frac", 0.5)

    for key in list(state["open"].keys()):
        pos = state["open"][key]
        coin = pos["coin"]
        p = mid(coin)
        if not p:
            continue
        d = pos["dir"]
        risk = pos["risk_px"]
        entry = pos["entry"]

        # R saat ini
        r_now = ((p - entry) if d == "LONG" else (entry - p)) / risk

        # ---- exit management (opsional, default OFF) ----
        if em_on:
            # partial TP
            if part_at and not pos.get("partial_done") and r_now >= part_at:
                frac = part_frac
                gain = frac * part_at * pos["risk_usd"]
                state["equity"] += gain
                state["day_pnl"] += gain
                pos["partial_done"] = True
                pos["realized_usd"] = pos.get("realized_usd", 0) + gain
                pos["risk_usd"] = pos["risk_usd"] * (1 - frac)
                pos["size"] = pos["size"] * (1 - frac)
                pos["sl"] = entry  # BE setelah partial
                pos["be_done"] = True
                save_state(state)
                log(f"💰 PARTIAL {coin} {frac*100:.0f}% @ {part_at}R (+${gain:.2f}) — SL→BE")
                tg(f"💰 *PARTIAL TP* {coin} {d}\n"
                   f"• Tutup {frac*100:.0f}% di +{part_at}R\n"
                   f"• Locked: +${gain:.2f}\n"
                   f"• Sisa posisi SL digeser ke entry (BE)")

            # BE lock
            elif be_at and not pos.get("be_done") and r_now >= be_at:
                pos["sl"] = entry
                pos["be_done"] = True
                save_state(state)
                log(f"🛡️ BE {coin} @ {be_at}R — SL→entry")
                tg(f"🛡️ *BREAKEVEN LOCK* {coin} {d}\n"
                   f"• Posisi +{r_now:.2f}R\n"
                   f"• SL digeser ke entry — bebas risiko")

        hit = None
        if d == "LONG":
            if p <= pos["sl"]:
                hit = ("SL", pos["sl"])
            elif p >= pos["tp"]:
                hit = ("TP", pos["tp"])
        else:
            if p >= pos["sl"]:
                hit = ("SL", pos["sl"])
            elif p <= pos["tp"]:
                hit = ("TP", pos["tp"])
        bars = (time.time() - pos["opened_ts"]) / 300
        if not hit and bars > pos["hold"]:
            hit = ("TIME", p)

        if hit:
            kind, px = hit
            R = ((px - entry) if d == "LONG" else (entry - px)) / risk
            # fee realistis: taker 0.045% per side = 0.09% round-trip
            # + slippage buffer 0.05% (dari execution reality test: -19.6% profit)
            fee = (entry + px) * 0.0009 / risk
            slip = (entry + px) * 0.0005 / risk
            R -= slip
            R -= fee
            usd = R * pos["risk_usd"]
            if pos.get("realized_usd"):
                usd += pos["realized_usd"]
            closed.append((key, pos, kind, px, R, usd))
            del state["open"][key]

    rm = cfg["_risk_model"]
    for key, pos, kind, px, R, usd in closed:
        coin = pos["coin"]
        state["equity"] += usd
        state["peak_equity"] = max(state["peak_equity"], state["equity"])
        state["day_pnl"] += usd

        skey = f"{coin}:{pos['strategy']}"
        st = state["stats"].setdefault(skey, {"n": 0, "w": 0, "l": 0, "R": 0.0, "usd": 0.0})
        st["n"] += 1
        st["R"] += R
        st["usd"] += usd
        if R > 0:
            st["w"] += 1
            state["consec_loss"] = 0
        else:
            st["l"] += 1
            state["consec_loss"] = state.get("consec_loss", 0) + 1
            # per-coin cooldown — hanya kalau diaktifkan
            cd_min = rm.get("coin_cooldown_min", 0)
            if cd_min > 0:
                state.setdefault("coin_cooldown", {})[coin] = time.time() + cd_min * 60
            # global cooldown — hanya kalau diaktifkan
            trigger = rm.get("consec_loss_trigger", 999)
            if trigger < 900 and state["consec_loss"] >= trigger:
                state["cooldown_until"] = time.time() + 45 * 60
                tg(f"⏸️ *GLOBAL COOLDOWN 45m* — {state['consec_loss']} loss beruntun\n"
                   f"Equity: ${state['equity']:.2f}")

        eq_pct = (state["equity"] / state["initial_equity"] - 1) * 100
        emoji = "🎯" if kind == "TP" else ("🛑" if kind == "SL" else "⏱️")
        log(f"{emoji} {coin} {pos['dir']} [{pos['strategy']}] {kind} {R:+.2f}R (${usd:+.2f}) "
            f"| eq ${state['equity']:.2f} ({eq_pct:+.1f}%)")
        tg(f"{emoji} *{coin} {pos['dir']}* {kind}\n"
           f"• {pos['strategy']} | {R:+.2f}R\n"
           f"• PnL: {usd:+.2f} USD\n"
           f"• Equity: *${state['equity']:.2f}* ({eq_pct:+.1f}%)")

        with open(TRADE_LOG, "a") as f:
            f.write(json.dumps({"t": now_wib().isoformat(), "coin": coin, "dir": pos["dir"],
                                "strategy": pos["strategy"], "kind": kind,
                                "entry": pos["entry"], "exit": px,
                                "R": round(R, 3), "usd": round(usd, 2),
                                "equity": round(state["equity"], 2)}) + "\n")

    if closed:
        log_equity(state)
        save_state(state)
    return closed


# ============================================================
#  MAIN
# ============================================================
def main():
    cfg = load_cfg()
    # urutkan coin by weight descending -> coin edge tertinggi dapat slot duluan
    coins = sorted(cfg["coins"].keys(), key=lambda c: -cfg["coins"][c]["weight"])
    state = load_state()
    rm = cfg["_risk_model"]

    total_strats = sum(len(c["strategies"]) for c in cfg["coins"].values())
    log(f"=== FUTURES BOT v4 | MODE={DISPLAY_MODE} | equity ${state['equity']:.2f} ===")
    log(f"{len(coins)} coins | {total_strats} strategy slots | risk {rm['base_risk_pct']}%/trade")
    for c, cc in cfg["coins"].items():
        fams = " + ".join(s["name"] for s in cc["strategies"])
        log(f"  {c:<6} [{cc['cluster']}] {fams:<26} w={cc['weight']}")

    today = now_wib().strftime("%Y-%m-%d")
    week = now_wib().strftime("%Y-W%W")
    if state.get("day") != today:
        state["day"] = today
        state["day_pnl"] = 0.0
    if state.get("week") != week:
        state["week"] = week
        state["week_start_equity"] = state["equity"]
    save_state(state)

    tg(f"🚀 *FUTURES BOT v4 ONLINE*\n"
       f"• Equity: ${state['equity']:.2f}\n"
       f"• {len(coins)} coins, {total_strats} strategy slots\n"
       f"• Dual-strategy: combined +242R vs single +173.6R\n"
       f"• Risk: {rm['base_risk_pct']}%/trade, max open {rm['max_total_open_risk_pct']}%\n"
       f"• Daily cap -{rm['daily_loss_cap_pct']}%, weekly -{rm['weekly_loss_cap_pct']}%")

    while True:
        tick_start = time.time()
        try:
            if os.path.exists(KILL_SWITCH):
                log("kill switch — stop"); tg("🛑 Kill switch active."); break

            today = now_wib().strftime("%Y-%m-%d")
            if state.get("day") != today:
                state["day"] = today; state["day_pnl"] = 0.0; save_state(state)

            check_exits(state, cfg)

            base_risk = current_risk_pct(state, cfg)
            max_w = max(c["weight"] for c in cfg["coins"].values())

            for coin in coins:
                cc = cfg["coins"][coin]

                for strat in cc["strategies"]:
                    tf = strat.get("timeframe", "5m")
                    slot = f"{coin}:{strat['name']}:{tf}"
                    if slot in state["open"]:
                        continue

                    # bar time sesuai TF masing-masing
                    ce = candles(coin, tf, 5)
                    if len(ce) < 3:
                        continue
                    lt = ce[-2]["t"]
                    if state["last_bar"].get(slot) == lt:
                        continue
                    state["last_bar"][slot] = lt

                    fn = ENGINES.get(strat["name"])
                    if not fn:
                        continue
                    sig, reason = fn(coin, strat["params"])
                    if not sig:
                        continue

                    # risk = base * coin weight * TF risk weight
                    tf_w = strat.get("risk_weight", 1.0)
                    weighted = base_risk * cc["weight"] / max_w * tf_w * 3.0
                    state["_pending_tf"] = tf
                    ok, why = can_open(state, coin, cfg, weighted)
                    state.pop("_pending_tf", None)
                    if not ok:
                        log(f"  skip {slot}: {why}")
                        continue

                    sizing = size_position(state, sig, weighted)
                    if sizing["risk_usd"] < 0.5:
                        continue

                    sig["timeframe"] = tf
                    state["open"][slot] = {**sig, **sizing, "opened_ts": time.time(), "mode": MODE}
                    save_state(state)
                    log_equity(state)

                    log(f"🔔 {slot} {sig['dir']} risk ${sizing['risk_usd']:.2f} "
                        f"({sizing['risk_pct_equity']:.2f}% eq)")
                    tg(f"🔔 *SIGNAL* {coin} {sig['dir']} ({sig['strategy']} {tf})\n"
                       f"• Entry: ${sig['entry']:,.6g}\n"
                       f"• SL: ${sig['sl']:,.6g} (-{sig['risk_pct']}%)\n"
                       f"• TP: ${sig['tp']:,.6g} (RR 1:{sig['rr']})\n"
                       f"• Risk: ${sizing['risk_usd']:.2f} ({sizing['risk_pct_equity']:.2f}% equity)\n"
                       f"• Equity: ${state['equity']:.2f}")

            # LATENCY MONITOR: execution reality test -> delay 1 bar = -44% edge
            elapsed = time.time() - tick_start
            if elapsed > 45:
                log(f"⚠️ LATENCY WARNING: scan cycle {elapsed:.1f}s (>45s)")
                tg(f"⚠️ *LATENCY WARNING*\nScan cycle {elapsed:.1f}s\n"
                   f"Normal <30s. Delay tinggi = edge hilang.")
            elif elapsed > 30:
                log(f"  latency {elapsed:.1f}s (elevated)")

            time.sleep(max(5, 20 - elapsed))

        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"ERR: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Hyperliquid Futures Bot v4 — DUAL STRATEGY per coin
====================================================
Each coin can run two strategies simultaneously (in parallel).
Hasil walk-forward: combined +242R vs single +173.6R (+39%).

Available strategies:
  breakout    : close tembus channel N-bar, searah tren 15m+1h
  sweep_fade  : sweep a level then close back (liquidity grab reversal)
  bollinger   : fade extreme BB touches when volatility is low

Mode: active (default) | live
"""
import os
import sys
import json
import time
import statistics
import urllib.request
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from smc_lib import evaluate_smc_scalp_signal, get_killzone_status

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/hl-futures-engine"
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

# Per-coin leverage: uniform 10x = 10% liquidation distance for every asset
# SL terlebar 1.56% (WLD) -> buffer 6.4x, aman
LEVERAGE_MAP = {
    "PUMP": 10, "WLD": 10, "ZEC": 10, "ENA": 10, "NEAR": 10, "HYPE": 10,
    "ETH": 10, "SOL": 10, "XRP": 10,
    "ARB": 10, "INJ": 5,   # INJ max leverage 5x di Hyperliquid
}
LEVERAGE = 10  # default fallback

# Variable leverage per horizon (v1.5)
# Scalp (5m): higher leverage for quick moves
# Intraday (15m): medium leverage
# Swing (1h): lower leverage for wider stops
HORIZON_LEVERAGE = {
    "5m": {"WLD": 15, "ZEC": 15, "ENA": 15, "NEAR": 15, "ARB": 15, "INJ": 5, "PAXG": 10, "AVAX": 15, "TAO": 15, "SUI": 15},
    "15m": {"WLD": 10, "ZEC": 10, "ENA": 10, "NEAR": 10, "ARB": 10, "INJ": 5, "PAXG": 8, "AVAX": 10, "TAO": 10, "SUI": 10},
    "1h": {"WLD": 5, "ZEC": 5, "ENA": 5, "NEAR": 5, "ARB": 5, "INJ": 5, "PAXG": 5, "AVAX": 5, "TAO": 5, "SUI": 5,
           "BTC": 5, "ETH": 5, "SOL": 5},
}

# Post-only limit orders (v1.6): guarantee maker rebate 0.002% vs taker 0.02%
POST_ONLY_LIMITS = True

# Volatility targeting (v1.6): scale position risk inversely to realized volatility
VOL_TARGET_DAILY_PCT = 2.0  # target 2% daily portfolio volatility
VOL_LOOKBACK = 14  # ATR lookback for vol estimation

MAX_RISK_PCT_PRICE = 0.035      # SL max 3.5% (ATR kegedean -> skip)
MIN_RISK_PCT_PRICE = 0.0015     # SL min 0.15% (sanity only, not a fee filter)
MAX_TOTAL_MARGIN_PCT = 0.75     # total margin across all positions capped at 75% of equity (aggressive mode)

# ============================================================
#  SESSION-AWARE RISK MULTIPLIERS (v1.7)
# ============================================================
# Based on 528 live trades + Binance volume data + institutional research
# WIB hour -> risk multiplier per strategy family
# 0.0 = disabled, 0.5 = half size, 1.0 = full, 1.2 = boosted
SESSION_MULTIPLIERS = {
    # NIGHT (22-04 WIB): Kill all directional, only funding arb
    22: {"smc": 0.0, "breakout": 0.0, "funding": 1.0},
    23: {"smc": 0.0, "breakout": 0.0, "funding": 1.0},
    0:  {"smc": 0.0, "breakout": 0.0, "funding": 1.0},
    1:  {"smc": 0.0, "breakout": 0.0, "funding": 1.0},
    2:  {"smc": 0.0, "breakout": 0.0, "funding": 1.0},
    3:  {"smc": 0.0, "breakout": 0.0, "funding": 1.0},
    # ASIA OPEN (04-08 WIB): SMC reduced (data shows 45% WR), Breakout DISABLED (0% WR)
    4:  {"smc": 0.5, "breakout": 0.0, "funding": 1.0},
    5:  {"smc": 0.5, "breakout": 0.0, "funding": 1.0},
    6:  {"smc": 0.5, "breakout": 0.0, "funding": 1.0},
    7:  {"smc": 0.5, "breakout": 0.0, "funding": 1.0},
    # EU OVERLAP (08-14 WIB): TOXIC - SMC reduced, Breakout DISABLED
    8:  {"smc": 0.3, "breakout": 0.0, "funding": 1.0},
    9:  {"smc": 0.3, "breakout": 0.0, "funding": 1.0},
    10: {"smc": 0.3, "breakout": 0.0, "funding": 1.0},
    11: {"smc": 0.3, "breakout": 0.0, "funding": 1.0},
    12: {"smc": 0.3, "breakout": 0.0, "funding": 1.0},
    13: {"smc": 0.3, "breakout": 0.0, "funding": 1.0},
    # US OVERLAP (14-22 WIB): SMC 0.7, Breakout DISABLED (0% WR in every session)
    14: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    15: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    16: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    17: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    18: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    19: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    20: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
    21: {"smc": 0.7, "breakout": 0.0, "funding": 1.0},
}

_CACHE = {}


def now_wib():
    return datetime.now(tz=WIB)


def log(m):
    print(f"[{now_wib().strftime('%H:%M:%S')}] {m}", flush=True)


def tg(m):
    """Send Telegram notification with retry + logging."""
    import urllib.request
    import urllib.error
    import re as _re
    max_retries = 3
    base_delay = 1.0
    tok = open(TG_TOKEN_FILE).read().strip()
    # Markdown chokes on underscores inside identifiers (funding_arb, smc_silver_bullet).
    # Escape intra-word underscores, leave *bold* markers alone.
    m = _re.sub(r"(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])", r"\\_", m)
    
    for attempt in range(max_retries):
        try:
            p = json.dumps({"chat_id": TG_CHAT, "text": m, "parse_mode": "Markdown"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data=p, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if not result.get("ok"):
                    raise Exception(f"API error: {result.get('description', 'unknown')}")
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited
                retry_after = int(e.headers.get("Retry-After", 2))
                log(f"TG rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            if e.code == 400:
                # Markdown parse failure (strategy names contain underscores) -> retry plain text
                log("TG 400 (markdown parse) — retrying without parse_mode")
                try:
                    p2 = json.dumps({"chat_id": TG_CHAT, "text": m}).encode()
                    req2 = urllib.request.Request(
                        f"https://api.telegram.org/bot{tok}/sendMessage",
                        data=p2, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req2, timeout=10) as r2:
                        if json.loads(r2.read().decode()).get("ok"):
                            return True
                except Exception as e2:
                    log(f"TG plain-text retry failed: {e2}")
            log(f"TG HTTP {e.code}: {e.reason}")
        except Exception as e:
            log(f"TG send failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay * (attempt + 1))
    log(f"TG FAILED after {max_retries} retries: {m[:80]}...")
    return False


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
    step = {
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000
    }[interval]
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
    """Fetch candles for the execution timeframe plus two higher timeframes as trend filters."""
    # Hyperliquid supported: 5m, 15m, 30m, 1h, 4h, 1d (but 4h seems broken)
    TF_UP = {"5m": ("15m", "1h"), "15m": ("1h", "1h"), "1h": ("1h", "1h")}
    up1, up2 = TF_UP.get(tf, ("15m", "1h"))
    LIM = {"5m": 120, "15m": 120, "1h": 120, "30m": 100, "1d": 80}
    ce = candles(coin, tf, LIM.get(tf, 120))
    c1 = candles(coin, up1, LIM.get(up1, 120))
    c2 = candles(coin, up2, LIM.get(up2, 120))
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

    # regime filter: ATR must sit below the 60-bar median (ranging)
    recent = [x for x in [atr(c5[:i], 14) for i in range(max(15, len(c5)-60), len(c5)-1)] if x]
    if len(recent) < 20:
        return None, "atr hist"
    if a > statistics.median(recent) * P["atr_max_ratio"]:
        return None, "volatile (not ranging)"

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


def sig_smc(coin, P):
    """
    SMC Silver Bullet Scalp:
    1. Liquidity Sweep (BSL / SSL)
    2. Displacement Candle + Fair Value Gap (FVG)
    3. Market Structure Shift (MSS)
    4. Killzone gating (London/NY high-vol sessions)
    """
    tf = P.get("timeframe", "5m")
    d = _common(coin, tf)
    if not d:
        return None, "data"
    c5, c15, c1h = d
    a = atr(c5[:-1], 14)
    if a is None:
        return None, "ind"
    aggressive = P.get("aggressive", True)
    sig, reason = evaluate_smc_scalp_signal(c5, c15, c1h, coin, a, aggressive=aggressive)
    if sig:
        sig["timeframe"] = tf
    return sig, reason


def sig_funding_arb(coin, P):
    """
    Funding Rate Arbitrage (Delta-Neutral):
    - Long perp + Short spot (or vice versa) to collect funding
    - Only viable when funding rate > threshold (e.g., 0.01% per 8h = 13.7% APR)
    - Exits when funding normalizes or position at risk
    - On Hyperliquid: perp funding paid/received every hour
    """
    try:
        tf = P.get("timeframe", "1h")
        min_funding_8h = P.get("min_funding_8h_pct", 0.01)  # 0.01% per 8h = 13.7% APR
        max_hold_hours = P.get("max_hold_hours", 48)
        
        # Get funding rate from HL
        import urllib.request, json
        payload = json.dumps({"type": "metaAndAssetCtxs"}).encode()
        req = urllib.request.Request(f"{HL}/info", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        
        universe = data[0].get("universe", [])
        ctxs = data[1]
        
        funding_rate = None
        for i, u in enumerate(universe):
            if u["name"] == coin and i < len(ctxs):
                funding_rate = float(ctxs[i].get("funding", 0) or 0)
                break
        
        if funding_rate is None:
            return None, "no funding data"
        
        # HL `funding` field is HOURLY rate (decimal). Convert to 8h-equivalent percent.
        funding_8h_pct = funding_rate * 8 * 100
        
        # Check if funding is attractive
        if abs(funding_8h_pct) < min_funding_8h:
            return None, f"funding {funding_8h_pct:.4f}% < {min_funding_8h}%"
        
        # Direction: collect positive funding (short perp if funding > 0, long perp if funding < 0)
        # For delta-neutral: short perp + long spot, or long perp + short spot
        # Since we only trade perps, we take directional perp position when funding is very skewed
        # Actually for pure perp funding arb, we just take position aligned with collecting funding
        
        if funding_rate > 0:
            # Positive funding -> longs pay shorts -> be SHORT to collect
            direction = "SHORT"
        else:
            # Negative funding -> shorts pay longs -> be LONG to collect
            direction = "LONG"
        
        # Get current price for entry
        c = candles(coin, "1h", 50)
        if len(c) < 2:
            return None, "no price data"
        
        entry = c[-2]["c"]
        atr_val = atr(c[:-1], 14)
        if not atr_val:
            return None, "no atr"
        
        # Wide stop for funding arb (hold for hours/days)
        risk_pct = max(atr_val / entry * 3, 0.02)  # min 2% risk
        if risk_pct > 0.05:
            return None, "risk too wide"
        
        dist = entry * risk_pct
        sl = entry - dist if direction == "LONG" else entry + dist
        tp = entry + dist * 2 if direction == "LONG" else entry - dist * 2  # 2R target
        
        return {
            "coin": coin, "dir": direction, "strategy": "funding_arb",
            "entry": round(entry, 8), "sl": round(sl, 8), "tp": round(tp, 8),
            "risk_px": round(dist, 8), "risk_pct": round(risk_pct * 100, 3),
            "rr": 2.0, "hold": max_hold_hours, "bar_t": c[-2]["t"],
            "funding_rate_8h": funding_8h_pct
        }, "ok"
        
    except Exception as e:
        return None, f"funding_arb error: {e}"


ENGINES = {
    "breakout": sig_breakout,
    "sweep_fade": sig_sweep,
    "bollinger": sig_bollinger,
    "smc_silver_bullet": sig_smc,
    "funding_arb": sig_funding_arb,
}


# ============================================================
#  REGIME DETECTION (v1.5)
# ============================================================
def detect_regime(coin, c5, c15, c1h):
    """
    Multi-timeframe regime classification:
    - BULL: 1h uptrend (EMA20 > EMA50, price > EMA20) + 15m confirmation
    - BEAR: 1h downtrend (EMA20 < EMA50, price < EMA20) + 15m confirmation
    - CHOP: Conflicting signals or flat EMAs
    Returns: ("BULL"|"BEAR"|"CHOP", strength 0-1, bias "LONG"|"SHORT"|"NEUTRAL")
    """
    try:
        closes_1h = [x["c"] for x in c1h[:-1]]
        closes_15 = [x["c"] for x in c15[:-1]]
        closes_5 = [x["c"] for x in c5[:-1]]

        ema20_1h = ema(closes_1h, 20)
        ema50_1h = ema(closes_1h, 50)
        ema20_15 = ema(closes_15, 20)
        ema50_15 = ema(closes_15, 50)

        if None in (ema20_1h, ema50_1h, ema20_15, ema50_15):
            return "CHOP", 0.0, "NEUTRAL"

        price = c5[-2]["c"]

        # 1h trend
        trend_1h = ema20_1h - ema50_1h
        price_vs_ema20_1h = price - ema20_1h

        # 15m confirmation
        trend_15 = ema20_15 - ema50_15
        price_vs_ema20_15 = c15[-2]["c"] - ema20_15

        # ATR for volatility context
        atr_1h = atr(c1h[:-1], 14)
        atr_5 = atr(c5[:-1], 14)

        if atr_1h is None or atr_5 is None:
            return "CHOP", 0.0, "NEUTRAL"

        # Strength based on trend separation normalized by ATR
        strength_1h = abs(trend_1h) / atr_1h if atr_1h > 0 else 0
        strength_15 = abs(trend_15) / atr_1h if atr_1h > 0 else 0  # normalize to 1h ATR

        # BULL: both timeframes aligned bullish
        if trend_1h > 0 and price_vs_ema20_1h > 0 and trend_15 > 0 and price_vs_ema20_15 > 0:
            strength = min(1.0, (strength_1h + strength_15) / 4)
            return "BULL", strength, "LONG"

        # BEAR: both timeframes aligned bearish
        if trend_1h < 0 and price_vs_ema20_1h < 0 and trend_15 < 0 and price_vs_ema20_15 < 0:
            strength = min(1.0, (strength_1h + strength_15) / 4)
            return "BEAR", strength, "SHORT"

        return "CHOP", 0.0, "NEUTRAL"

    except Exception:
        return "CHOP", 0.0, "NEUTRAL"


def get_limit_entry(coin, sig, c5, c15, c1h, regime_bias):
    """
    Calculate limit entry price at key levels (FVG, Order Block, Sweep zone)
    Returns: (limit_price, entry_type) or (None, "market") if no good level
    """
    try:
        direction = sig["dir"]
        if direction != regime_bias and regime_bias != "NEUTRAL":
            # Against regime - be more aggressive, use market
            return None, "market"

        # For SMC signals, we can use the FVG or sweep level as limit
        if sig["strategy"] == "smc_silver_bullet":
            # The SMC engine already identifies sweep + FVG
            # We can place limit at the FVG midpoint or sweep level
            entry = sig["entry"]
            sl = sig["sl"]
            risk = abs(entry - sl)

            # Limit at 0.25R improvement from market
            if direction == "LONG":
                limit = entry - risk * 0.25
            else:
                limit = entry + risk * 0.25

            # Only use limit if it's reasonable (within 0.5% of market)
            if abs(limit - entry) / entry < 0.005:
                return round(limit, 8), "limit_fvg"

        # For breakout, use the breakout level as limit (slightly better)
        elif sig["strategy"] == "breakout":
            entry = sig["entry"]
            sl = sig["sl"]
            risk = abs(entry - sl)

            # Limit at breakout level (already the close price)
            # Can improve by 0.15R
            if direction == "LONG":
                limit = entry - risk * 0.15
            else:
                limit = entry + risk * 0.15

            if abs(limit - entry) / entry < 0.005:
                return round(limit, 8), "limit_breakout"

        return None, "market"

    except Exception:
        return None, "market"


# Post-only order helper (v1.6)
# Hyperliquid supports post_only flag in order options
def build_post_only_order(coin, direction, size, limit_price, leverage):
    """
    Build order payload for post-only limit order on Hyperliquid.
    Post-only guarantees maker rebate (0.002%) vs taker fee (0.02%).
    """
    is_buy = direction == "LONG"
    return {
        "coin": coin,
        "is_buy": is_buy,
        "sz": size,
        "limit_px": limit_price,
        "order_type": {"limit": {"tif": "Gtc"}},  # Good-til-cancelled
        "reduce_only": False,
        "post_only": True,  # Guarantees maker or cancel
        "leverage": leverage,
    }


def build_market_order(coin, direction, size, leverage):
    """Fallback market order when limit not filled."""
    is_buy = direction == "LONG"
    return {
        "coin": coin,
        "is_buy": is_buy,
        "sz": size,
        "order_type": {"limit": {"tif": "Ioc"}},  # Immediate-or-cancel = market
        "reduce_only": False,
        "leverage": leverage,
    }


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


def can_open(state, coin, cfg, new_risk_pct, sig_dir=None):
    rm = cfg["_risk_model"]
    open_pos = state["open"]

    if len(open_pos) >= rm["max_concurrent"]:
        return False, f"max {rm['max_concurrent']} positions"

    used = sum(p.get("risk_pct_equity", 0) for p in open_pos.values())
    if used + new_risk_pct > rm["max_total_open_risk_pct"]:
        return False, f"open risk {used:.2f}%+{new_risk_pct:.2f}% > {rm['max_total_open_risk_pct']}%"

    # total margin guard — prevents the whole balance from being locked
    cur_margin = sum(p.get("margin", 0) for p in open_pos.values())
    max_margin = state["equity"] * MAX_TOTAL_MARGIN_PCT
    if cur_margin >= max_margin:
        return False, f"margin limit (${cur_margin:.0f}/${max_margin:.0f})"

    # correlation cluster — key is "COIN:strategy", take the coin part
    cluster = cfg["coins"][coin]["cluster"]
    same = []
    for slot in open_pos:
        oc = open_pos[slot].get("coin") or slot.split(":")[0]
        if cfg["coins"].get(oc, {}).get("cluster") == cluster:
            same.append(oc)
    if len(same) >= cfg["_correlation_clusters"]["_max_per_cluster"]:
        return False, f"cluster {cluster} full ({len(same)}: {','.join(same)})"

    # BLOCK 1: same coin and same timeframe already open (prevents self-hedging on one TF)
    # Multi-TF: 5m, 15m and 1h on the same coin may run concurrently (different horizons)
    new_tf = (state.get("_pending_tf") or "5m")
    for slot in open_pos:
        oc = open_pos[slot].get("coin") or slot.split(":")[0]
        otf = open_pos[slot].get("timeframe", "5m")
        if oc == coin and otf == new_tf:
            return False, f"{coin} {new_tf} already open ({open_pos[slot]['dir']} @ {slot})"

    # BLOCK 2: Anti-Conflict Directional Guard
    # Prevent opposing positions on the same coin (e.g. 1h swing long vs 5m scalp short)
    if sig_dir:
        for slot in open_pos:
            oc = open_pos[slot].get("coin") or slot.split(":")[0]
            if oc == coin and open_pos[slot].get("dir") != sig_dir:
                return False, f"{coin} directional conflict ({open_pos[slot]['dir']} @ {slot} vs new {sig_dir})"

    # per-coin cooldown (after a loss) — skipped when disabled
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

    # SESSION-AWARE GATING (v1.7): Check session multiplier for this strategy
    hour = now_wib().hour
    mult = SESSION_MULTIPLIERS.get(hour, {"smc": 1.0, "breakout": 1.0, "funding": 1.0})
    strat_name = state.get("_pending_strategy", "")
    # Determine strategy family from strategy name
    if "funding" in strat_name.lower():
        session_mult = mult.get("funding", 1.0)
    elif "smc" in strat_name.lower():
        session_mult = mult.get("smc", 1.0)
    else:  # breakout, sweep_fade, bollinger
        session_mult = mult.get("breakout", 1.0)
    
    if session_mult == 0.0:
        return False, f"session disabled (WIB {hour:02d}:00)"

    return True, "ok"


def size_position(state, sig, risk_pct_equity):
    equity = state["equity"]
    coin = sig["coin"]
    tf = sig.get("timeframe", "5m")
    lev = HORIZON_LEVERAGE.get(tf, {}).get(coin, LEVERAGE_MAP.get(coin, LEVERAGE))
    
    # SESSION-AWARE (v1.7): Apply session multiplier to risk
    hour = now_wib().hour
    mult = SESSION_MULTIPLIERS.get(hour, {"smc": 1.0, "breakout": 1.0, "funding": 1.0})
    strat_name = state.get("_pending_strategy", "")
    if "funding" in strat_name.lower():
        session_mult = mult.get("funding", 1.0)
    elif "smc" in strat_name.lower():
        session_mult = mult.get("smc", 1.0)
    else:
        session_mult = mult.get("breakout", 1.0)
    
    # Apply session multiplier to base risk
    risk_pct_equity = risk_pct_equity * session_mult

    # Volatility targeting (v1.6): scale risk inversely to realized volatility
    # Higher volatility -> smaller position, lower volatility -> larger position
    vol_scale = 1.0
    try:
        c = candles(coin, tf, VOL_LOOKBACK + 5)
        if len(c) > VOL_LOOKBACK:
            atr_val = atr(c[:-1], VOL_LOOKBACK)
            if atr_val and c[-2]["c"]:
                current_vol_daily = (atr_val / c[-2]["c"]) * 100 * (24 * 60 / int(tf.replace("m", "")) if "m" in tf else 24) ** 0.5
                # Scale to target vol (cap at 0.5x to 2.0x)
                if current_vol_daily > 0:
                    vol_scale = VOL_TARGET_DAILY_PCT / current_vol_daily
                    vol_scale = max(0.5, min(2.0, vol_scale))
    except Exception:
        pass
    
    # v1.8: CAP DOUBLE PENALTY — if DD reduce active, skip vol_scale (don't compound)
    rm = state.get("_risk_model_cfg") or {}
    peak = state.get("peak_equity", equity)
    dd = (peak - equity) / peak * 100 if peak > 0 else 0
    if dd >= rm.get("reduce_after_dd_pct", 999):
        vol_scale = 1.0  # skip vol targeting when drawdown reduce is active
    
    risk_usd = equity * risk_pct_equity / 100 * vol_scale
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
            "risk_pct_equity": round(risk_usd / equity * 100, 4),
            "vol_scale": round(vol_scale, 3)}


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

        # current R
        r_now = ((p - entry) if d == "LONG" else (entry - p)) / risk

        # ---- exit management: HYBRID SCALP->SWING (v1.8.2+) ----
        # Partial TP 50% @ 1.5R (NO BE LOCK)
        # Runner 50% -> Structure TP (>=2.5R) + Trail 1.5xATR after 2.5R
        if em_on:
            # Partial TP (no BE after)
            if part_at and not pos.get("partial_done") and r_now >= part_at:
                frac = part_frac  # 0.5
                gain = frac * part_at * pos["risk_usd"]
                # NOTE: the gain is NOT added to equity here.
                # It is banked in realized_usd and only hits equity when the position closes
                # (usd = R*risk_usd + realized_usd). Adding it here would double count.
                pos["partial_done"] = True
                pos["realized_usd"] = pos.get("realized_usd", 0) + gain
                pos["risk_usd"] = pos["risk_usd"] * (1 - frac)
                pos["size"] = pos["size"] * (1 - frac)
                # NO BE LOCK -- SL stays at original swing level
                save_state(state)
                log(f"💰 PARTIAL {coin} {frac*100:.0f}% @ {part_at}R (+${gain:.2f}) -- Runner active")
                tg(f"💰 *PARTIAL TP* {coin} {d}\n"
                   f"• Closed {frac*100:.0f}% at +{part_at}R\n"
                   f"• Locked: +${gain:.2f}\n"
                   f"• Runner 50% -> Structure TP + Trail")

            # BE lock DISABLED (be_at_R is null)
            # elif be_at and not pos.get("be_done") and r_now >= be_at:
            #     pass
        hit = None
        # --- trailing logic (price-action based) ---
        trail_mult = pos.get("trail_atr_mult")
        if trail_mult and trail_mult > 0 and r_now >= 2.5:
            # Get 15m ATR for trailing
            c15 = candles(coin, "15m", 30)
            atr_15 = atr(c15, 14) if len(c15) >= 15 else None
            if atr_15 and atr_15 > 0:
                trail_dist = atr_15 * trail_mult
                if d == "LONG":
                    new_sl = p - trail_dist
                    if new_sl > pos["sl"]:
                        pos["sl"] = round(new_sl, 8)
                        pos["trail_active"] = True
                else:
                    new_sl = p + trail_dist
                    if new_sl < pos["sl"]:
                        pos["sl"] = round(new_sl, 8)
                        pos["trail_active"] = True

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
            # realistic friction: taker 0.045% per side = 0.09% round-trip on notional,
            # + 0.05% slippage buffer. Charged once on the exit price, not on (entry+exit).
            fee = px * 0.0009 / risk
            slip = px * 0.0005 / risk
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
            # per-coin cooldown — only when enabled
            cd_min = rm.get("coin_cooldown_min", 0)
            if cd_min > 0:
                state.setdefault("coin_cooldown", {})[coin] = time.time() + cd_min * 60
            # global cooldown — only when enabled
            trigger = rm.get("consec_loss_trigger", 999)
            if trigger < 900 and state["consec_loss"] >= trigger:
                state["cooldown_until"] = time.time() + 45 * 60
                tg(f"⏸️ *GLOBAL COOLDOWN 45m* — {state['consec_loss']} consecutive losses\n"
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
    # sort coins by weight descending -> the strongest edge gets a slot first
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
                log("kill switch — stopping"); tg("🛑 Kill switch active."); break

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
                    # Pass params with explicit timeframe injected
                    engine_params = {**strat["params"], "timeframe": tf}
                    sig, reason = fn(coin, engine_params)
                    if not sig:
                        # night session: funding_arb is the only live strategy — log its skips
                        if strat["name"] == "funding_arb" and reason:
                            log(f"  skip {slot}: {reason}")
                        continue

                    # SESSION-AWARE (v1.7): Store strategy name for session gating in can_open()
                    state["_pending_strategy"] = strat["name"]
                    
                    # REGIME DETECTION (v1.5): Get market regime for directional bias
                    c5 = candles(coin, "5m", 100)
                    c15 = candles(coin, "15m", 100)
                    c1h = candles(coin, "1h", 100)
                    regime, regime_strength, regime_bias = detect_regime(coin, c5, c15, c1h)
                    
                    # LIMIT ORDER ENGINE (v1.5): Try to get better entry at key levels
                    limit_price, entry_type = get_limit_entry(coin, sig, c5, c15, c1h, regime_bias)
                    if limit_price:
                        sig["entry"] = limit_price
                        sig["entry_type"] = entry_type
                        # Recalculate SL/TP based on new entry
                        risk = abs(limit_price - sig["sl"])
                        if sig["dir"] == "LONG":
                            sig["tp"] = round(limit_price + risk * sig["rr"], 8)
                            sig["sl"] = round(limit_price - risk, 8)
                        else:
                            sig["tp"] = round(limit_price - risk * sig["rr"], 8)
                            sig["sl"] = round(limit_price + risk, 8)
                        sig["risk_px"] = round(risk, 8)
                        sig["risk_pct"] = round(risk / limit_price * 100, 3)

                    # RISK NORMALIZATION (v1.4):
                    # Each position risks exactly base_risk (0.45% of equity)
                    # Eliminates risk disparity where a single loss wiped out 5 wins.
                    weighted = base_risk
                    state["_pending_tf"] = tf
                    ok, why = can_open(state, coin, cfg, weighted, sig_dir=sig["dir"])
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
                    tg(f"🔔 *SIGNAL* {coin} {sig['dir']} ({sig['strategy']} {tf}) {sig.get('entry_type', 'market')}\n"
                       f"• Regime: {regime} ({regime_strength:.0%}) | Bias: {regime_bias}\n"
                       f"• Entry: ${sig['entry']:,.6g}\n"
                       f"• SL: ${sig['sl']:,.6g} (-{sig['risk_pct']}%)\n"
                       f"• TP: ${sig['tp']:,.6g} (RR 1:{sig['rr']})\n"
                       f"• Risk: ${sizing['risk_usd']:.2f} ({sizing['risk_pct_equity']:.2f}% equity) | Lev: {sizing['leverage']}x\n"
                       f"• Equity: ${state['equity']:.2f}")

            # LATENCY MONITOR: execution reality test -> delay 1 bar = -44% edge
            elapsed = time.time() - tick_start
            if elapsed > 45:
                log(f"⚠️ LATENCY WARNING: scan cycle {elapsed:.1f}s (>45s)")
                tg(f"⚠️ *LATENCY WARNING*\nScan cycle {elapsed:.1f}s\n"
                   f"Normal <30s. High delay means lost edge.")
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

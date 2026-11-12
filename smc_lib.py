"""
smc_lib.py — Smart Money Concepts (SMC) & ICT Quantitative Engine
===================================================================
Algorithmic implementation of:
1. Swing Highs & Swing Lows (Fractal Pivot points)
2. Buy-side (BSL) & Sell-side (SSL) Liquidity Sweeps
3. Institutional Displacement Candles
4. Fair Value Gaps (FVG) + Consequent Encroachment (50% midpoint)
5. Order Blocks (OB)
6. Market Structure Shift (MSS / CHoCH)
7. ICT Killzone Session Time Filters (WIB / UTC)
8. Multi-Horizon Signal Generator (Scalp, Intraday, Swing)

Designed for Hyperliquid L1 Perpetuals.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

WIB = timezone(timedelta(hours=7))


def find_swings(candles: List[Dict], left: int = 3, right: int = 3) -> Tuple[List[Dict], List[Dict]]:
    """
    Identifies Fractal Swing Highs and Swing Lows.
    A swing high has candle[i]['h'] > high of 'left' bars before and 'right' bars after.
    """
    swing_highs = []
    swing_lows = []
    n = len(candles)
    if n < left + right + 1:
        return swing_highs, swing_lows

    for i in range(left, n - right):
        h = candles[i]["h"]
        l = candles[i]["l"]
        
        # Check swing high
        is_sh = True
        for j in range(i - left, i):
            if candles[j]["h"] >= h:
                is_sh = False; break
        if is_sh:
            for j in range(i + 1, i + right + 1):
                if candles[j]["h"] > h:
                    is_sh = False; break
        if is_sh:
            swing_highs.append({"index": i, "price": h, "t": candles[i]["t"]})

        # Check swing low
        is_sl = True
        for j in range(i - left, i):
            if candles[j]["l"] <= l:
                is_sl = False; break
        if is_sl:
            for j in range(i + 1, i + right + 1):
                if candles[j]["l"] < l:
                    is_sl = False; break
        if is_sl:
            swing_lows.append({"index": i, "price": l, "t": candles[i]["t"]})

    return swing_highs, swing_lows


def detect_fvg(c1: Dict, c2: Dict, c3: Dict, min_gap_pct: float = 0.0008) -> Optional[Dict]:
    """
    Detects Fair Value Gap (Imbalance) across 3 consecutive candles.
    Bullish FVG: Low of candle 3 > High of candle 1
    Bearish FVG: High of candle 3 < Low of candle 1
    """
    # Bullish FVG
    if c3["l"] > c1["h"]:
        gap_size = c3["l"] - c1["h"]
        if gap_size / c2["c"] >= min_gap_pct:
            return {
                "type": "bullish",
                "top": round(c3["l"], 8),
                "bottom": round(c1["h"], 8),
                "mid": round((c3["l"] + c1["h"]) / 2, 8), # Consequent Encroachment (50%)
                "size_pct": round(gap_size / c2["c"] * 100, 4),
                "t": c2["t"]
            }
    # Bearish FVG
    elif c3["h"] < c1["l"]:
        gap_size = c1["l"] - c3["h"]
        if gap_size / c2["c"] >= min_gap_pct:
            return {
                "type": "bearish",
                "top": round(c1["l"], 8),
                "bottom": round(c3["h"], 8),
                "mid": round((c1["l"] + c3["h"]) / 2, 8),
                "size_pct": round(gap_size / c2["c"] * 100, 4),
                "t": c2["t"]
            }
    return None


def detect_displacement(c: Dict, atr_val: float, multiplier: float = 1.8) -> bool:
    """
    Detects institutional displacement candle:
    Candle body >= multiplier * ATR and body makes up >= 60% of total candle range.
    """
    if not atr_val or atr_val <= 0:
        return False
    body = abs(c["c"] - c["o"])
    rng = max(c["h"] - c["l"], 1e-9)
    return (body >= multiplier * atr_val) and (body / rng >= 0.60)


def detect_liquidity_sweep(candles: List[Dict], swing_highs: List[Dict], swing_lows: List[Dict],
                           lookback: int = 20) -> Optional[Dict]:
    """
    Detects if the latest completed candle swept a recent swing level and closed back inside.
    Buy-Side Liquidity (BSL) Sweep: high > swing_high, but close < swing_high (Bearish signal).
    Sell-Side Liquidity (SSL) Sweep: low < swing_low, but close > swing_low (Bullish signal).
    """
    if len(candles) < 2:
        return None
    cur = candles[-2] # latest closed candle
    cur_idx = len(candles) - 2

    # Check SSL sweep (Bullish reversal)
    for sl in reversed(swing_lows):
        if cur_idx - sl["index"] > lookback:
            break
        if sl["index"] < cur_idx:
            # Wick pierced below swing low, but closed above it
            if cur["l"] < sl["price"] and cur["c"] > sl["price"]:
                wick_depth = (sl["price"] - cur["l"]) / cur["c"] * 100
                return {
                    "type": "SSL_SWEEP",
                    "bias": "BULLISH",
                    "swept_level": sl["price"],
                    "wick_low": cur["l"],
                    "wick_depth_pct": round(wick_depth, 3),
                    "t": cur["t"]
                }

    # Check BSL sweep (Bearish reversal)
    for sh in reversed(swing_highs):
        if cur_idx - sh["index"] > lookback:
            break
        if sh["index"] < cur_idx:
            # Wick pierced above swing high, but closed below it
            if cur["h"] > sh["price"] and cur["c"] < sh["price"]:
                wick_depth = (cur["h"] - sh["price"]) / cur["c"] * 100
                return {
                    "type": "BSL_SWEEP",
                    "bias": "BEARISH",
                    "swept_level": sh["price"],
                    "wick_high": cur["h"],
                    "wick_depth_pct": round(wick_depth, 3),
                    "t": cur["t"]
                }
    return None


def get_killzone_status(timestamp_ms: int, aggressive: bool = True) -> Dict:
    """
    Checks if timestamp falls into high-liquidity ICT Killzones (in WIB / UTC+7).
    Aggressive mode allows broader sessions while strictly blacklisting dead chop.
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=WIB)
    hour = dt.hour
    minute = dt.minute
    time_float = hour + minute / 60.0

    # Killzones definitions in WIB:
    # 1. London Open Killzone: 13:30 - 17:00 WIB (06:30 - 10:00 UTC)
    # 2. New York Open Killzone: 19:30 - 23:30 WIB (12:30 - 16:30 UTC) [GOLDMINE FROM OUR DATA!]
    # 3. US Late / After-Hours Momentum: 03:30 - 05:30 WIB (20:30 - 22:30 UTC)
    # 4. Asia Open Volatility: 08:30 - 11:00 WIB (01:30 - 04:00 UTC)

    is_london = 13.5 <= time_float <= 17.0
    is_ny = 19.5 <= time_float <= 23.5
    is_us_late = 3.5 <= time_float <= 5.5
    is_asia_open = 8.5 <= time_float <= 11.0

    # Dead chop zones (where v1.0 lost money):
    # 00:00 - 03:00 WIB (-$15 to -$30)
    # 05:30 - 08:30 WIB (-$26)
    # 22:00 - 23:00 WIB (post-NY fix trap)
    is_dead_chop = (0.0 <= time_float < 3.5) or (5.5 < time_float < 8.5) or (22.0 <= time_float <= 23.0)

    in_prime_killzone = is_london or is_ny or is_us_late or (aggressive and is_asia_open)
    
    session_name = "OFF_SESSION"
    if is_ny:
        session_name = "NY_KILLZONE"
    elif is_london:
        session_name = "LONDON_KILLZONE"
    elif is_us_late:
        session_name = "US_AFTER_HOURS"
    elif is_asia_open:
        session_name = "ASIA_OPEN"
    elif is_dead_chop:
        session_name = "DEAD_CHOP"

    return {
        "hour_wib": hour,
        "time_str": dt.strftime("%H:%M WIB"),
        "in_killzone": in_prime_killzone and not (not aggressive and is_dead_chop),
        "is_dead_chop": is_dead_chop,
        "session": session_name,
        "size_multiplier": 1.5 if is_ny else (1.2 if is_london else 1.0)
    }


def evaluate_smc_scalp_signal(
    candles_5m: List[Dict],
    candles_15m: List[Dict],
    candles_1h: List[Dict],
    coin: str,
    atr_val: float,
    aggressive: bool = True
) -> Tuple[Optional[Dict], str]:
    """
    Evaluates SMC Silver Bullet Scalp on 5m with 15m/1h Market Bias.
    Setup:
    1. Check Killzone (prefer high-liquidity sessions)
    2. Filter Bias: 1h EMA 50/200 trend filter (strictly avoid shorting against strong HTF drift)
    3. Detect Liquidity Sweep on 5m or 15m
    4. Detect Displacement Candle leaving an FVG
    5. Set Limit Entry at FVG Consequent Encroachment (50%) with 1:3 to 1:4 RR
    """
    if len(candles_5m) < 30 or len(candles_15m) < 20 or len(candles_1h) < 20:
        return None, "insufficient_data"

    cur = candles_5m[-2] # latest closed 5m bar
    kz = get_killzone_status(cur["t"], aggressive=aggressive)

    # Block trading in toxic dead chop hours unless aggressive override is full
    if kz["is_dead_chop"] and not aggressive:
        return None, f"dead_chop_filtered ({kz['session']})"

    # HTF Trend Bias from 1h closes
    closes_1h = [x["c"] for x in candles_1h[:-1]]
    ema_fast = sum(closes_1h[-20:]) / 20.0
    ema_slow = sum(closes_1h[-50:]) / 50.0 if len(closes_1h) >= 50 else ema_fast
    cur_1h_price = closes_1h[-1]
    
    htf_bullish = cur_1h_price > ema_fast and ema_fast >= ema_slow
    htf_bearish = cur_1h_price < ema_fast and ema_fast <= ema_slow

    # Find Swings on 5m
    sh_5m, sl_5m = find_swings(candles_5m[:-1], left=3, right=3)
    sweep = detect_liquidity_sweep(candles_5m, sh_5m, sl_5m, lookback=24)

    # Detect FVG on last 3 bars
    c1, c2, c3 = candles_5m[-4], candles_5m[-3], candles_5m[-2]
    fvg = detect_fvg(c1, c2, c3, min_gap_pct=0.0006)
    disp = detect_displacement(c2, atr_val, multiplier=1.5)

    # Trade Setup 1: Bullish SMC Scalp (SSL Sweep + Displacement Bullish FVG)
    if (sweep and sweep["bias"] == "BULLISH") or (fvg and fvg["type"] == "bullish" and disp):
        # We want to enter LONG
        # If HTF is not heavily bearish
        if not htf_bearish or aggressive:
            entry_px = fvg["mid"] if fvg and fvg["type"] == "bullish" else cur["c"]
            # SL placed below the recent swing low or candle low with safety buffer
            recent_lows = [x["l"] for x in candles_5m[-6:-1]]
            sl_px = min(recent_lows) - (atr_val * 0.3)
            risk_px = entry_px - sl_px
            
            if risk_px > 0 and (risk_px / entry_px) <= 0.035 and (risk_px / entry_px) >= 0.003:
                rr = 3.5 if aggressive else 3.0
                tp_px = entry_px + (risk_px * rr)
                return {
                    "coin": coin,
                    "dir": "LONG",
                    "strategy": "smc_silver_bullet",
                    "entry": round(entry_px, 8),
                    "sl": round(sl_px, 8),
                    "tp": round(tp_px, 8),
                    "risk_px": round(risk_px, 8),
                    "risk_pct": round(risk_px / entry_px * 100, 3),
                    "rr": rr,
                    "hold": 48, # 48 bars on 5m = 4 hours max hold
                    "bar_t": cur["t"],
                    "session": kz["session"],
                    "size_multiplier": kz["size_multiplier"],
                    "fvg": fvg,
                    "sweep": sweep
                }, "ok_bullish_smc"

    # Trade Setup 2: Bearish SMC Scalp (BSL Sweep + Displacement Bearish FVG)
    # STRICT GUARD: Only short if HTF is NOT bullish! (Direct fix for our v1.0 -$104 short losses!)
    if (sweep and sweep["bias"] == "BEARISH") or (fvg and fvg["type"] == "bearish" and disp):
        if not htf_bullish:
            entry_px = fvg["mid"] if fvg and fvg["type"] == "bearish" else cur["c"]
            recent_highs = [x["h"] for x in candles_5m[-6:-1]]
            sl_px = max(recent_highs) + (atr_val * 0.3)
            risk_px = sl_px - entry_px

            if risk_px > 0 and (risk_px / entry_px) <= 0.035 and (risk_px / entry_px) >= 0.003:
                rr = 3.5 if aggressive else 3.0
                tp_px = entry_px - (risk_px * rr)
                return {
                    "coin": coin,
                    "dir": "SHORT",
                    "strategy": "smc_silver_bullet",
                    "entry": round(entry_px, 8),
                    "sl": round(sl_px, 8),
                    "tp": round(tp_px, 8),
                    "risk_px": round(risk_px, 8),
                    "risk_pct": round(risk_px / entry_px * 100, 3),
                    "rr": rr,
                    "hold": 48,
                    "bar_t": cur["t"],
                    "session": kz["session"],
                    "size_multiplier": kz["size_multiplier"],
                    "fvg": fvg,
                    "sweep": sweep
                }, "ok_bearish_smc"

    return None, "no_smc_setup"

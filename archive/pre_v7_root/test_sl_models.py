#!/usr/bin/env python3
"""
Bandingkan 3 model SL:
  A. ATR-based (sekarang)      : SL = entry ± ATR × mult
  B. Swing-based (price action): SL = swing low/high terakhir ± buffer
  C. Hybrid                    : SL = max(ATR, swing) — ambil yang lebih lebar

TP tetap R-multiple supaya perbandingan apple-to-apple.
"""
import json
from engine import fetch, ema_series, atr_series, metrics

CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))["coins"]
COINS = list(CFG.keys())


def align_htf(c5, c15, c1h):
    i15 = i1h = 0
    m15, m1h = [], []
    for c in c5:
        while i15 + 1 < len(c15) and c15[i15 + 1]["t"] <= c["t"]:
            i15 += 1
        while i1h + 1 < len(c1h) and c1h[i1h + 1]["t"] <= c["t"]:
            i1h += 1
        m15.append(i15)
        m1h.append(i1h)
    return m15, m1h


def run(c5, c15, c1h, params, family, sl_model, rr):
    n = len(c5)
    a = atr_series(c5, 14)
    m15, m1h = align_htf(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]
    cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, params.get("htf_ema", 20))
    e1h = ema_series(cl1h, params.get("htf_ema", 20))
    e1h50 = ema_series(cl1h, 50)

    trades = []
    busy = -1
    look = params.get("look", 6)

    for i in range(max(120, look + 3), n - 1):
        if i <= busy:
            continue
        cur = c5[i - 1]
        k15, k1h = m15[i - 1], m1h[i - 1]
        if None in (e15[k15], e1h[k1h], a[i - 1]):
            continue

        up15 = cl15[k15] > e15[k15]
        up1h = cl1h[k1h] > e1h[k1h]
        slope = e1h[k1h] > e1h50[k1h]
        rng = c5[i - 1 - look:i - 1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)
        br = body / rngc

        d = None
        if family == "breakout":
            if br < params.get("min_body", 0):
                continue
            if cur["c"] > hh and up15 and up1h:
                d = "LONG"
            elif cur["c"] < ll and not up15 and not up1h:
                d = "SHORT"
        elif family == "sweep_fade":
            if br < params.get("min_body", 0):
                continue
            if cur["l"] < ll and cur["c"] > ll and up15 and up1h:
                d = "LONG"
            elif cur["h"] > hh and cur["c"] < hh and not up15 and not up1h:
                d = "SHORT"
        elif family == "bollinger":
            import statistics as st
            if i < params["bb_period"]:
                continue
            w = cl15[:1]  # placeholder
            cl5 = [x["c"] for x in c5[:i]]
            ww = cl5[-params["bb_period"]:]
            m = sum(ww) / len(ww)
            sd = st.pstdev(ww)
            upper = m + params["bb_k"] * sd
            lower = m - params["bb_k"] * sd
            if cur["l"] < lower and cur["c"] > lower:
                d = "LONG"
            elif cur["h"] > upper and cur["c"] < upper:
                d = "SHORT"
        if not d:
            continue

        entry = cur["c"]
        atr_dist = a[i - 1] * params["atr_mult"]

        # swing terakhir: 10 bar sebelum candle trigger
        swing_win = c5[max(0, i - 12):i - 1]
        swing_low = min(x["l"] for x in swing_win)
        swing_high = max(x["h"] for x in swing_win)

        if sl_model == "atr":
            dist = atr_dist
        elif sl_model == "swing":
            if d == "LONG":
                dist = entry - swing_low + entry * 0.0005   # buffer 0.05%
            else:
                dist = swing_high - entry + entry * 0.0005
        elif sl_model == "hybrid":
            if d == "LONG":
                sd = entry - swing_low + entry * 0.0005
            else:
                sd = swing_high - entry + entry * 0.0005
            dist = max(atr_dist, sd)

        if dist <= 0:
            continue
        if dist / entry > 0.035:
            continue
        if dist / entry < 0.0015:
            continue

        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr

        cur_sl = sl
        outcome = None
        exit_p = None
        bars = 0
        for j in range(i, min(i + params.get("hold", 72) + 1, n)):
            bars = j - i
            h, l = c5[j]["h"], c5[j]["l"]
            if d == "LONG" and l <= cur_sl:
                outcome = "SL"
                exit_p = cur_sl
                break
            if d == "SHORT" and h >= cur_sl:
                outcome = "SL"
                exit_p = cur_sl
                break
            if d == "LONG" and h >= tp:
                outcome = "TP"
                exit_p = tp
                break
            if d == "SHORT" and l <= tp:
                outcome = "TP"
                exit_p = tp
                break
        if outcome is None:
            exit_p = c5[min(i + params.get("hold", 72), n - 1)]["c"]
            outcome = "TIME"

        pnl = (exit_p - entry) if d == "LONG" else (entry - exit_p)
        R = pnl / dist
        fee = (entry + exit_p) * 0.0004 / dist
        trades.append({"R": R - fee, "outcome": outcome, "bars": bars})
        busy = i + max(bars, 1)
    return trades


if __name__ == "__main__":
    print("Fetching 120d untuk", len(COINS), "coin...", flush=True)
    data = {}
    for c in COINS:
        try:
            data[c] = {"5m": fetch(c, "5m", 120), "15m": fetch(c, "15m", 130),
                       "1h": fetch(c, "1h", 170)}
            print(f"  {c} ok", flush=True)
        except Exception as e:
            print(f"  {c} ERR {e}", flush=True)

    print("\n" + "=" * 100)
    print("PERBANDINGAN MODEL SL (TP tetap R-multiple)")
    print("=" * 100)
    print(f"{'MODEL':<10}{'TotR':>9}{'N':>5}{'WR%':>7}{'PF':>7}{'MaxDD':>9}{'AvgR':>8}")
    print("-" * 100)

    for model in ["atr", "swing", "hybrid"]:
        all_tr = []
        for c, cc in CFG.items():
            if c not in data:
                continue
            for s in cc["strategies"]:
                try:
                    tr = run(data[c]["5m"], data[c]["15m"], data[c]["1h"],
                             s["params"], s["name"], model, s["params"]["rr"])
                    all_tr.extend(tr)
                except Exception:
                    pass
        if not all_tr:
            print(f"{model:<10}  no trades")
            continue
        m = metrics(all_tr)
        print(f"{model:<10}{m['totR']:>+9.1f}{m['n']:>5}{m['wr']:>7.1f}{m['pf']:>7.2f}"
              f"{m['mdd']:>9.1f}{m['totR']/m['n']:>8.3f}")

#!/usr/bin/env python3
"""Test dampak partial TP + BE terhadap total R. Pakai config aktif."""
import json
from engine import fetch, FAMILIES, metrics

CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))["coins"]


def run_with_mgmt(c5, c15, c1h, params, family, partial_at=None, partial_frac=0.5,
                  be_at=None, rr=2.0):
    """Wrapper: jalankan family, lalu replay trade dengan partial/BE overlay.

    Karena engine asli tidak support partial, kita re-simulate per trade
    dengan parameter exit yang sama tapi ada partial & BE.
    """
    import statistics as st
    from engine import ema_series, atr_series

    def align_htf(c5x, c15x, c1hx):
        i15 = i1h = 0
        m15x, m1hx = [], []
        for cc in c5x:
            while i15 + 1 < len(c15x) and c15x[i15 + 1]["t"] <= cc["t"]:
                i15 += 1
            while i1h + 1 < len(c1hx) and c1hx[i1h + 1]["t"] <= cc["t"]:
                i1h += 1
            m15x.append(i15)
            m1hx.append(i1h)
        return m15x, m1hx

    n = len(c5)
    a = atr_series(c5, 14)
    m15, m1h = align_htf(c5, c15, c1h)
    cl15 = [x["c"] for x in c15]
    cl1h = [x["c"] for x in c1h]
    e15 = ema_series(cl15, params.get("htf_ema", 20))
    e1h = ema_series(cl1h, params.get("htf_ema", 20))
    e1h50 = ema_series(cl1h, 50)
    closes = [x["c"] for x in c5]

    # bollinger helpers
    def bb(vals, period, k):
        if len(vals) < period: return None, None
        w = vals[-period:]
        m = sum(w) / period
        sd = st.pstdev(w)
        return m + k * sd, m - k * sd

    trades = []
    busy = -1
    look = params.get("look", 6)

    for i in range(max(120, look + 3), n - 1):
        if i <= busy: continue
        cur = c5[i - 1]
        k15, k1h = m15[i - 1], m1h[i - 1]
        if None in (e15[k15], e1h[k1h], a[i - 1]): continue

        up15 = cl15[k15] > e15[k15]
        up1h = cl1h[k1h] > e1h[k1h]
        slope = e1h[k1h] > e1h50[k1h]
        rng = c5[i - 1 - look:i - 1]
        hh = max(x["h"] for x in rng); ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"]); rngc = max(cur["h"] - cur["l"], 1e-9)
        br = body / rngc

        d = None
        if family == "breakout":
            if br < params.get("min_body", 0): continue
            if cur["c"] > hh and up15 and up1h: d = "LONG"
            elif cur["c"] < ll and not up15 and not up1h: d = "SHORT"
        elif family == "sweep_fade":
            if br < params.get("min_body", 0): continue
            if cur["l"] < ll and cur["c"] > ll and up15 and up1h: d = "LONG"
            elif cur["h"] > hh and cur["c"] < hh and not up15 and not up1h: d = "SHORT"
        elif family == "bollinger":
            upper, lower = bb(closes[:i], params["bb_period"], params["bb_k"])
            if upper is None: continue
            if cur["l"] < lower and cur["c"] > lower: d = "LONG"
            elif cur["h"] > upper and cur["c"] < upper: d = "SHORT"
        if not d: continue

        entry = cur["c"]
        dist = a[i - 1] * params["atr_mult"]
        if dist / entry > 0.035: continue
        risk = dist
        sl = entry - dist if d == "LONG" else entry + dist
        tp = entry + dist * rr if d == "LONG" else entry - dist * rr

        cur_sl = sl
        remaining = 1.0
        realized = 0.0
        partial_done = False
        be_done = False
        outcome = None
        bars = 0

        for j in range(i, min(i + params.get("hold", 72) + 1, n)):
            bars = j - i
            if bars == 0:
                # entry bar: check fill (market = immediate)
                pass
            h, l = c5[j]["h"], c5[j]["l"]
            r_now = (h - entry) / risk if d == "LONG" else (entry - l) / risk

            if be_at and not be_done and r_now >= be_at:
                cur_sl = entry
                be_done = True

            if partial_at and not partial_done and r_now >= partial_at:
                realized += partial_frac * partial_at
                remaining -= partial_frac
                partial_done = True
                cur_sl = entry  # BE after partial

            if d == "LONG" and l <= cur_sl:
                r_exit = (cur_sl - entry) / risk
                realized += remaining * r_exit
                outcome = "SL" if abs(cur_sl - sl) < 1e-12 else ("BE" if abs(cur_sl - entry) < 1e-12 else "TRAIL")
                break
            if d == "SHORT" and h >= cur_sl:
                r_exit = (entry - cur_sl) / risk
                realized += remaining * r_exit
                outcome = "SL" if abs(cur_sl - sl) < 1e-12 else ("BE" if abs(cur_sl - entry) < 1e-12 else "TRAIL")
                break
            if d == "LONG" and h >= tp:
                realized += remaining * rr
                outcome = "TP"
                break
            if d == "SHORT" and l <= tp:
                realized += remaining * rr
                outcome = "TP"
                break

        if outcome is None:
            px = c5[min(i + params.get("hold", 72), n - 1)]["c"]
            r_exit = (px - entry) / risk if d == "LONG" else (entry - px) / risk
            realized += remaining * r_exit
            outcome = "TIME"

        fee = (entry + (entry + risk * rr)) * 0.0004 / risk * 0.7
        trades.append({"R": realized - fee, "outcome": outcome, "bars": bars})
        busy = i + max(bars, 1)
    return trades


if __name__ == "__main__":
    variants = {
        "A_baseline (no BE, no partial)": dict(partial_at=None, be_at=None),
        "B_BE@0.6R":                      dict(partial_at=None, be_at=0.6),
        "C_BE@1.0R":                      dict(partial_at=None, be_at=1.0),
        "D_partial@1R + BE":              dict(partial_at=1.0, partial_frac=0.5, be_at=0.6),
        "E_partial@1.5R + BE":            dict(partial_at=1.5, partial_frac=0.5, be_at=0.6),
        "F_partial@1R/50% + BE@1R":       dict(partial_at=1.0, partial_frac=0.5, be_at=1.0),
        "G_partial@0.75R/50% + BE":       dict(partial_at=0.75, partial_frac=0.5, be_at=0.5),
    }

    print("Fetching 120d data...")
    data = {}
    for c in CFG:
        try:
            data[c] = {"5m": fetch(c, "5m", 120), "15m": fetch(c, "15m", 130),
                       "1h": fetch(c, "1h", 170)}
            print(f"  {c} ok")
        except Exception as e:
            print(f"  {c} ERR {e}")

    print("\n" + "=" * 96)
    print(f"{'VARIANT':<34}{'TotR':>9}{'N':>5}{'WR%':>7}{'PF':>7}{'MaxDD':>9}")
    print("=" * 96)
    for vname, mgmt in variants.items():
        all_tr = []
        for c, cc in CFG.items():
            if c not in data: continue
            for s in cc["strategies"]:
                try:
                    tr = run_with_mgmt(data[c]["5m"], data[c]["15m"], data[c]["1h"],
                                       s["params"], s["name"], **mgmt)
                    all_tr.extend(tr)
                except Exception:
                    pass
        if not all_tr: continue
        m = metrics(all_tr)
        print(f"{vname:<34}{m['totR']:>+9.1f}{m['n']:>5}{m['wr']:>7.1f}{m['pf']:>7.2f}{m['mdd']:>9.1f}")

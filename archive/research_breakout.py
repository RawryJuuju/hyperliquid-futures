"""Strategy family B: momentum/breakout (bukan mean-reversion).
Hipotesis: kripto trending, jadi breakout continuation lebih cocok dari fade."""
import urllib.request, json, time
from stratlib2 import fetch, ema_series, atr_series, adx_series, align_htf, stats


def run_breakout(c5, c15, c1h, cfg):
    n = len(c5)
    closes = [c["c"] for c in c5]
    e20 = ema_series(closes, 20)
    e50 = ema_series(closes, 50)
    a = atr_series(c5, 14)
    adx = adx_series(c5, 14) if cfg.get("min_adx") else [None]*n
    m15, m1h = align_htf(c5, c15, c1h)
    closes15 = [c["c"] for c in c15]
    closes1h = [c["c"] for c in c1h]
    e15 = ema_series(closes15, 20)
    e1h = ema_series(closes1h, 20)
    e1h50 = ema_series(closes1h, 50)

    trades = []
    busy = -1
    look = cfg["lookback"]

    for i in range(max(120, look + 3), n - 1):
        if i <= busy: continue
        cur = c5[i-1]
        k15, k1h = m15[i-1], m1h[i-1]
        if None in (e15[k15], e1h[k1h], e1h50[k1h], a[i-1], e20[i-1], e50[i-1]):
            continue

        up15 = closes15[k15] > e15[k15]
        up1h = closes1h[k1h] > e1h[k1h]
        slope_up = e1h[k1h] > e1h50[k1h]
        strength = abs(closes1h[k1h] - e1h[k1h]) / a[i-1]
        if cfg.get("min_strength") and strength < cfg["min_strength"]: continue
        if cfg.get("min_adx") and (adx[i-1] is None or adx[i-1] < cfg["min_adx"]): continue

        # breakout level = high/low of lookback EXCLUDING last bar
        rng = c5[i-1-look:i-1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)

        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)
        br = body / rngc
        if br < cfg.get("min_body", 0.0): continue
        if body / a[i-1] < cfg.get("min_disp", 0.0): continue

        vols = [x["v"] for x in c5[max(0, i-21):i-1]]
        avgv = sum(vols)/len(vols) if vols else 1
        if avgv and cur["v"]/avgv < cfg.get("min_vol", 0): continue

        direction = None
        # Breakout LONG: close ABOVE hh, in uptrend
        if cur["c"] > hh and up15 and up1h and slope_up:
            direction = "LONG"
        elif cur["c"] < ll and (not up15) and (not up1h) and (not slope_up):
            direction = "SHORT"
        if not direction: continue

        # entry: pullback limit to breakout level (retest) or market-ish at close
        if cfg.get("retest_entry"):
            entry = hh if direction == "LONG" else ll
        else:
            entry = cur["c"]

        dist = a[i-1] * cfg["atr_mult"]
        sl = entry - dist if direction == "LONG" else entry + dist
        risk = abs(entry - sl)
        if risk <= 0: continue
        if risk/entry > cfg.get("max_risk_pct", 0.025): continue
        if risk/entry < cfg.get("min_risk_pct", 0.001): continue

        tp = entry + risk*cfg["rr"] if direction == "LONG" else entry - risk*cfg["rr"]

        fill = None
        for j in range(i, min(i + cfg["ttl"], n)):
            if direction == "LONG" and c5[j]["l"] <= entry: fill = j; break
            if direction == "SHORT" and c5[j]["h"] >= entry: fill = j; break
        if fill is None: continue

        be_at = cfg.get("be_at")
        cur_sl = sl
        outcome = None; exit_p = None; bars = 0
        for j in range(fill+1, min(fill+cfg["max_hold"]+1, n)):
            bars += 1
            h, l = c5[j]["h"], c5[j]["l"]
            r_now = (h-entry)/risk if direction == "LONG" else (entry-l)/risk
            if be_at and r_now >= be_at: cur_sl = entry
            if direction == "LONG" and l <= cur_sl:
                outcome = "SL" if cur_sl == sl else "BEP"; exit_p = cur_sl; break
            if direction == "SHORT" and h >= cur_sl:
                outcome = "SL" if cur_sl == sl else "BEP"; exit_p = cur_sl; break
            if direction == "LONG" and h >= tp: outcome = "TP"; exit_p = tp; break
            if direction == "SHORT" and l <= tp: outcome = "TP"; exit_p = tp; break

        if outcome is None:
            exit_p = c5[min(fill+cfg["max_hold"], n-1)]["c"]
            outcome = "TIME"

        pnl = (exit_p-entry) if direction == "LONG" else (entry-exit_p)
        R = pnl/risk
        fee = (entry+exit_p)*0.0004/risk
        trades.append({"dir": direction, "R": R-fee, "outcome": outcome, "bars": bars})
        busy = fill + max(bars, 1)
    return trades


COINS = ["BTC", "ETH", "ZEC", "HYPE", "SOL"]

if __name__ == "__main__":
    print("Fetching 90d for 5 coins...")
    data = {}
    for c in COINS:
        try:
            data[c] = {"5m": fetch(c, "5m", 90), "15m": fetch(c, "15m", 100), "1h": fetch(c, "1h", 130)}
            print(f"  {c:<6} ok")
        except Exception as e:
            print(f"  {c:<6} ERR {e}")

    V = {
     "B1_break_rr2":    dict(lookback=20, atr_mult=1.2, rr=2.0, ttl=6, max_hold=72, be_at=1.0, min_body=0.5, min_vol=1.2, min_strength=1.0, retest_entry=False),
     "B2_retest_rr2":   dict(lookback=20, atr_mult=1.2, rr=2.0, ttl=12, max_hold=72, be_at=1.0, min_body=0.5, min_vol=1.2, min_strength=1.0, retest_entry=True),
     "B3_retest_rr3":   dict(lookback=20, atr_mult=1.2, rr=3.0, ttl=12, max_hold=96, be_at=1.0, min_body=0.5, min_vol=1.2, min_strength=1.0, retest_entry=True),
     "B4_adx_retest":   dict(lookback=20, atr_mult=1.2, rr=2.5, ttl=12, max_hold=96, be_at=1.0, min_body=0.5, min_vol=1.2, min_strength=1.0, min_adx=22, retest_entry=True),
     "B5_look12":       dict(lookback=12, atr_mult=1.2, rr=2.5, ttl=12, max_hold=96, be_at=1.0, min_body=0.5, min_vol=1.2, min_strength=1.0, min_adx=22, retest_entry=True),
     "B6_look36":       dict(lookback=36, atr_mult=1.5, rr=2.5, ttl=12, max_hold=96, be_at=1.0, min_body=0.5, min_vol=1.2, min_strength=1.0, min_adx=22, retest_entry=True),
     "B7_disp":         dict(lookback=20, atr_mult=1.2, rr=2.5, ttl=12, max_hold=96, be_at=1.0, min_body=0.6, min_disp=1.0, min_vol=1.3, min_strength=1.0, min_adx=22, retest_entry=True),
     "B8_vol15":        dict(lookback=20, atr_mult=1.2, rr=2.5, ttl=12, max_hold=96, be_at=1.0, min_body=0.5, min_vol=1.5, min_strength=1.0, min_adx=22, retest_entry=True),
    }

    print("\n" + "="*120)
    print(f"{'VARIANT':<17}" + "".join(f"{c:>13}" for c in COINS) + f"{'TOTAL_R':>12}{'PF_avg':>9}{'N':>6}")
    print("="*120)
    best = []
    for vname, cfg in V.items():
        row = f"{vname:<17}"; totR = 0.0; pfs = []; totn = 0
        for c in COINS:
            if c not in data: row += f"{'-':>13}"; continue
            tr = run_breakout(data[c]["5m"], data[c]["15m"], data[c]["1h"], cfg)
            st = stats(tr, c)
            if st["n"] == 0:
                row += f"{'0':>13}"; continue
            row += f"{st['totR']:>+8.1f}({st['n']:>2})"
            totR += st["totR"]; pfs.append(st["pf"]); totn += st["n"]
        pfavg = sum(pfs)/len(pfs) if pfs else 0
        row += f"{totR:>+12.1f}{pfavg:>9.2f}{totn:>6}"
        print(row)
        best.append((vname, totR, pfavg, totn))

    print("\n=== RANK by TOTAL R ===")
    for v, tr_, pf, n in sorted(best, key=lambda x: -x[1]):
        print(f"  {v:<17} TotR={tr_:>+7.1f}  PF_avg={pf:>5.2f}  N={n}")

    topv = sorted(best, key=lambda x: -x[1])[0][0]
    print(f"\n=== DETAIL {topv} ===")
    print(f"{'COIN':<7}{'N':>4}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}")
    print("-"*50)
    for c in COINS:
        if c not in data: continue
        tr = run_breakout(data[c]["5m"], data[c]["15m"], data[c]["1h"], V[topv])
        st = stats(tr, c)
        if st["n"] == 0: print(f"{c:<7}0"); continue
        print(f"{c:<7}{st['n']:>4}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}")

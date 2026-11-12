"""Grid search: cari apakah ADA parameter region yang punya edge positif.
Test market-entry (fill di close signal) vs limit-retest, banyak RR & ATR."""
from stratlib2 import fetch, ema_series, atr_series, adx_series, align_htf, stats


def run_grid(c5, c15, c1h, cfg):
    n = len(c5)
    closes = [c["c"] for c in c5]
    a = atr_series(c5, 14)
    m15, m1h = align_htf(c5, c15, c1h)
    closes15 = [c["c"] for c in c15]
    closes1h = [c["c"] for c in c1h]
    e15 = ema_series(closes15, cfg["ema_htf"])
    e1h = ema_series(closes1h, cfg["ema_htf"])
    e1h50 = ema_series(closes1h, 50)

    trades = []
    busy = -1
    look = cfg["lookback"]

    for i in range(max(120, look + 3), n - 1):
        if i <= busy: continue
        cur = c5[i-1]
        k15, k1h = m15[i-1], m1h[i-1]
        if None in (e15[k15], e1h[k1h], e1h50[k1h], a[i-1]): continue

        up15 = closes15[k15] > e15[k15]
        up1h = closes1h[k1h] > e1h[k1h]
        slope_up = e1h[k1h] > e1h50[k1h]

        rng = c5[i-1-look:i-1]
        hh = max(x["h"] for x in rng)
        ll = min(x["l"] for x in rng)
        body = abs(cur["c"] - cur["o"])
        rngc = max(cur["h"] - cur["l"], 1e-9)

        if cfg["mode"] == "sweep_fade":
            if body/rngc < cfg.get("min_body", 0): continue
            direction = None
            if cur["l"] < ll and cur["c"] > ll and up15 and up1h: direction = "LONG"
            elif cur["h"] > hh and cur["c"] < hh and (not up15) and (not up1h): direction = "SHORT"
        elif cfg["mode"] == "breakout":
            if body/rngc < cfg.get("min_body", 0): continue
            direction = None
            if cur["c"] > hh and up15 and up1h and slope_up: direction = "LONG"
            elif cur["c"] < ll and (not up15) and (not up1h) and (not slope_up): direction = "SHORT"
        elif cfg["mode"] == "trend_continuation":
            # any pullback to EMA20 in a trend
            direction = None
            if up15 and up1h and slope_up and cur["l"] <= e15[k15] and cur["c"] > e15[k15]:
                direction = "LONG"
            elif (not up15) and (not up1h) and (not slope_up) and cur["h"] >= e15[k15] and cur["c"] < e15[k15]:
                direction = "SHORT"
        else:
            continue

        if not direction: continue

        # entry mode
        if cfg["entry"] == "market":
            entry = cur["c"]
            fill = i
        else:
            entry = (cur["l"]+cur["c"])/2 if direction == "LONG" else (cur["h"]+cur["c"])/2
            fill = None
            for j in range(i, min(i+cfg["ttl"], n)):
                if direction == "LONG" and c5[j]["l"] <= entry: fill = j; break
                if direction == "SHORT" and c5[j]["h"] >= entry: fill = j; break
            if fill is None: continue

        dist = a[i-1] * cfg["atr_mult"]
        sl = entry - dist if direction == "LONG" else entry + dist
        risk = abs(entry - sl)
        if risk <= 0 or risk/entry > 0.03: continue

        tp = entry + risk*cfg["rr"] if direction == "LONG" else entry - risk*cfg["rr"]

        cur_sl = sl; outcome = None; exit_p = None; bars = 0
        be_at = cfg.get("be_at")
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
            exit_p = c5[min(fill+cfg["max_hold"], n-1)]["c"]; outcome = "TIME"

        pnl = (exit_p-entry) if direction == "LONG" else (entry-exit_p)
        R = pnl/risk; fee = (entry+exit_p)*0.0004/risk
        trades.append({"dir": direction, "R": R-fee, "outcome": outcome, "bars": bars})
        busy = fill + max(bars, 1)
    return trades


if __name__ == "__main__":
    COINS = ["ETH", "SOL"]
    print("Fetching 60d...")
    data = {}
    for c in COINS:
        data[c] = {"5m": fetch(c, "5m", 60), "15m": fetch(c, "15m", 70), "1h": fetch(c, "1h", 90)}
        print(f"  {c} ok")

    results = []
    for mode in ["sweep_fade", "breakout", "trend_continuation"]:
        for entry in ["market", "limit"]:
            for atr_mult in [1.0, 1.5, 2.0]:
                for rr in [1.5, 2.0, 3.0]:
                    for be_at in [None, 1.0]:
                        cfg = dict(mode=mode, entry=entry, lookback=6, atr_mult=atr_mult,
                                   rr=rr, ttl=8, max_hold=72, be_at=be_at,
                                   min_body=0.3, ema_htf=20)
                        tot = 0.0; ns = 0; pfs = []
                        for c in COINS:
                            tr = run_grid(data[c]["5m"], data[c]["15m"], data[c]["1h"], cfg)
                            st = stats(tr)
                            tot += st["totR"]; ns += st["n"]
                            if st["n"] > 0: pfs.append(st["pf"])
                        if ns < 15: continue
                        results.append((mode, entry, atr_mult, rr, be_at, tot, ns, sum(pfs)/len(pfs) if pfs else 0))

    results.sort(key=lambda x: -x[5])
    print("\n" + "="*104)
    print(f"{'MODE':<20}{'ENTRY':<8}{'ATR':>5}{'RR':>5}{'BE':>6}{'TotR':>9}{'N':>5}{'PFavg':>8}")
    print("="*104)
    for r in results[:20]:
        print(f"{r[0]:<20}{r[1]:<8}{r[2]:>5.1f}{r[3]:>5.1f}{str(r[4]):>6}{r[5]:>+9.1f}{r[6]:>5}{r[7]:>8.2f}")
    print("\n--- WORST 5 ---")
    for r in results[-5:]:
        print(f"{r[0]:<20}{r[1]:<8}{r[2]:>5.1f}{r[3]:>5.1f}{str(r[4]):>6}{r[5]:>+9.1f}{r[6]:>5}{r[7]:>8.2f}")
    print(f"\nTotal configs tested: {len(results)}")
    pos = [r for r in results if r[5] > 0]
    print(f"Configs with POSITIVE total R: {len(pos)}")
    if pos:
        print("\n=== POSITIVE CONFIGS ===")
        for r in pos[:10]:
            print(f"  {r[0]:<20}{r[1]:<8} ATR={r[2]} RR={r[3]} BE={r[4]}  TotR={r[5]:+.1f}  N={r[6]}  PF={r[7]:.2f}")

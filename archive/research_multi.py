#!/usr/bin/env python3
"""Multi-coin validation: top-5 volume (BTC ETH ZEC HYPE SOL) with v3 strategy."""
from stratlib2 import fetch, run_v3, stats

COINS = ["BTC", "ETH", "ZEC", "HYPE", "SOL"]

BASE = dict(lookback=6, atr_mult=1.0, ttl=12, max_hold=60,
            require_slope=True, min_body=0.45, min_strength=1.0,
            be_at=1.0, tp1_r=1.5, tp2_r=3.0)

VARIANTS = {
 "V0_base_rr2":   {**BASE, "tp1_r":2.0, "tp2_r":2.0},
 "V1_partial":    {**BASE, "partial":True, "partial_frac":0.5, "tp1_r":1.5, "tp2_r":3.0},
 "V2_adx20":      {**BASE, "min_adx":20, "partial":True, "partial_frac":0.5},
 "V3_adx25":      {**BASE, "min_adx":25, "partial":True, "partial_frac":0.5},
 "V4_disp":       {**BASE, "min_disp":0.6, "partial":True, "partial_frac":0.5},
 "V5_fvg":        {**BASE, "require_fvg":True, "partial":True, "partial_frac":0.5},
 "V6_fvg_entry":  {**BASE, "require_fvg":True, "entry_fvg":True, "partial":True, "partial_frac":0.5},
 "V7_vol13":      {**BASE, "min_vol":1.3, "partial":True, "partial_frac":0.5},
 "V8_strength15": {**BASE, "min_strength":1.5, "partial":True, "partial_frac":0.5},
}

if __name__ == "__main__":
    print("Fetching 60d for 5 coins...")
    data = {}
    for c in COINS:
        try:
            d5 = fetch(c, "5m", 60); d15 = fetch(c, "15m", 70); d1h = fetch(c, "1h", 90)
            data[c] = {"5m": d5, "15m": d15, "1h": d1h}
            print(f"  {c:<6} 5m={len(d5)} 15m={len(d15)} 1h={len(d1h)}")
        except Exception as e:
            print(f"  {c:<6} ERR {e}")

    print("\n" + "="*118)
    print(f"{'VARIANT':<15}" + "".join(f"{c:>12}" for c in COINS) + f"{'TOTAL_R':>12}{'PF_avg':>9}")
    print("="*118)

    best = []
    for vname, cfg in VARIANTS.items():
        row = f"{vname:<15}"
        totR = 0.0; pfs = []; ns = []
        for c in COINS:
            if c not in data: row += f"{'-':>12}"; continue
            tr = run_v3(data[c]["5m"], data[c]["15m"], data[c]["1h"], cfg)
            st = stats(tr, c)
            if st["n"] == 0:
                row += f"{'0':>12}"
                ns.append(0); continue
            row += f"{st['totR']:>+7.1f}({st['n']:>2})"
            totR += st["totR"]; pfs.append(st["pf"]); ns.append(st["n"])
        pfavg = sum(pfs)/len(pfs) if pfs else 0
        row += f"{totR:>+12.1f}{pfavg:>9.2f}"
        print(row)
        best.append((vname, totR, pfavg, sum(ns)))

    print("\n=== RANK by TOTAL R (5 coins) ===")
    for v, tr_, pf, n in sorted(best, key=lambda x: -x[1]):
        print(f"  {v:<15} TotR={tr_:>+7.1f}  PF_avg={pf:>5.2f}  N={n}")

    print("\n=== DETAIL PER COIN: TOP VARIANT ===")
    top = sorted(best, key=lambda x: -x[1])[0][0]
    print(f"variant: {top}")
    cfg = VARIANTS[top]
    print(f"{'COIN':<7}{'N':>4}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}{'TP':>5}{'BEP':>5}{'TIME':>6}")
    print("-"*70)
    for c in COINS:
        if c not in data: continue
        tr = run_v3(data[c]["5m"], data[c]["15m"], data[c]["1h"], cfg)
        st = stats(tr, c)
        if st["n"]==0: print(f"{c:<7}0"); continue
        print(f"{c:<7}{st['n']:>4}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}{st['TP']:>5}{st['BEP']:>5}{st['TIME']:>6}")

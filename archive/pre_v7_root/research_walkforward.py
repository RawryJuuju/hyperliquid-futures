#!/usr/bin/env python3
"""
Walk-forward research: 6 strategi x 14 koin likuid.
IS = 60 hari pertama, OOS = 60 hari terakhir.
Output: ranking metode x koin berdasarkan OOS profit factor.
"""
import json, time, itertools, sys
from engine import (fetch, FAMILIES, metrics)

COINS = ["BTC","ETH","ZEC","HYPE","SOL","NEAR","PUMP","XRP","WLD","ENA"]

# parameter grid per family
GRIDS = {
 "sweep_fade": [
   dict(look=l, atr_mult=a, rr=r, min_body=b, htf_ema=20, hold=72)
   for l in (6,10) for a in (1.5,2.0,2.5) for r in (2.0,3.0,4.0) for b in (0.3,0.5)
 ],
 "breakout": [
   dict(look=l, atr_mult=a, rr=r, min_body=b, htf_ema=20, hold=72)
   for l in (10,20,40) for a in (1.5,2.0) for r in (2.0,3.0) for b in (0.4,0.6)
 ],
 "ema_pullback": [
   dict(ema_fast=f, ema_slow=s, atr_mult=a, rr=r, hold=72)
   for f,s in ((20,50),(9,21)) for a in (1.5,2.0) for r in (2.0,3.0)
 ],
 "bollinger": [
   dict(bb_period=p, bb_k=k, atr_mult=a, rr=r, hold=48, atr_max_ratio=m)
   for p in (20,50) for k in (2.0,2.5) for a in (1.5,2.0) for r in (1.5,2.0) for m in (1.0,1.3)
 ],
 "rsi_rev": [
   dict(rsi_period=14, rsi_lo=l, rsi_hi=h, ema_trend=t, atr_mult=a, rr=r, hold=48)
   for l,h in ((30,70),(25,75)) for t in (50,200) for a in (1.5,2.0) for r in (1.5,2.0)
 ],
 "donchian": [
   dict(look=l, atr_mult=a, rr=r, hold=96, trail_at=ta)
   for l in (20,40,55) for a in (1.5,2.0) for r in (2.0,3.0,5.0) for ta in (None,1.5)
 ],
}

def run(coin, data, family, params):
    fn = FAMILIES[family]
    c5 = data["5m"]; c15 = data["15m"]; c1h = data["1h"]
    mid = len(c5)//2
    is_t = fn(c5[:mid], c15, c1h, params)
    oos_t = fn(c5[mid:], c15, c1h, params)
    return metrics(is_t), metrics(oos_t)

if __name__ == "__main__":
    print("Fetching 120d data for", len(COINS), "coins...", flush=True)
    data = {}
    for c in COINS:
        try:
            data[c] = {"5m": fetch(c, "5m", 120), "15m": fetch(c, "15m", 130), "1h": fetch(c, "1h", 170)}
            print(f"  {c:<8} 5m={len(data[c]['5m'])}", flush=True)
        except Exception as e:
            print(f"  {c:<8} ERR {e}", flush=True)

    results = []
    total = sum(len(g) for g in GRIDS.values()) * len(data)
    done = 0
    for family, grid in GRIDS.items():
        for params in grid:
            for coin in data:
                try:
                    is_m, oos_m = run(coin, data[coin], family, params)
                except Exception:
                    continue
                done += 1
                if not is_m or not oos_m: continue
                if is_m["n"] < 12 or oos_m["n"] < 12: continue
                # only keep configs profitable in BOTH halves
                if is_m["totR"] <= 0 or oos_m["totR"] <= 0: continue
                results.append({
                    "family": family, "coin": coin,
                    "is_pf": round(is_m["pf"],2), "is_R": round(is_m["totR"],1), "is_n": is_m["n"],
                    "oos_pf": round(oos_m["pf"],2), "oos_R": round(oos_m["totR"],1), "oos_n": oos_m["n"],
                    "oos_wr": round(oos_m["wr"],1), "oos_mdd": round(oos_m["mdd"],1),
                    "params": params,
                })
        print(f"  [{family}] done ({done}/{total}) — {len(results)} passing", flush=True)

    results.sort(key=lambda x: -(x["oos_R"]))
    with open("research_walkforward.json","w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "="*110)
    print("TOP 30 — profitable di IS DAN OOS (walk-forward survivors)")
    print("="*110)
    print(f"{'#':<3}{'FAMILY':<14}{'COIN':<7}{'IS_PF':>7}{'IS_R':>7}{'OOS_PF':>8}{'OOS_R':>8}{'OOS_WR':>8}{'OOS_DD':>8}{'N':>4}")
    print("-"*110)
    for i, r in enumerate(results[:30], 1):
        print(f"{i:<3}{r['family']:<14}{r['coin']:<7}{r['is_pf']:>7.2f}{r['is_R']:>7.1f}"
              f"{r['oos_pf']:>8.2f}{r['oos_R']:>8.1f}{r['oos_wr']:>7.1f}%{r['oos_mdd']:>8.1f}{r['oos_n']:>4}")

    print(f"\nTotal survivors: {len(results)}")
    # per-family best
    print("\n=== BEST PER FAMILY ===")
    for fam in GRIDS:
        sub = [r for r in results if r["family"] == fam]
        if not sub: 
            print(f"  {fam:<14} (no survivor)"); continue
        b = max(sub, key=lambda x: x["oos_R"])
        print(f"  {fam:<14} {b['coin']:<6} OOS_PF={b['oos_pf']:.2f} OOS_R={b['oos_R']:+.1f} N={b['oos_n']}")

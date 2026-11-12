#!/usr/bin/env python3
"""
Kandidat coin baru: walk-forward 120d (IS 60d / OOS 60d).
Pakai 3 strategi yang sudah terbukti + grid parameter ringkas.
Hanya lolos kalau OOS_PF >= 1.30 DAN OOS_R > 0 DAN n >= 15.
"""
import json, time
from engine import fetch, FAMILIES, metrics

CANDIDATES = ["ARB", "ZRO", "SUI", "INJ", "CRV", "ONDO", "UNI", "LINK",
              "AAVE", "DOGE", "XPL", "STRK", "XMR", "kPEPE", "TAO"]

GRIDS = {
    "breakout": [
        dict(look=l, atr_mult=a, rr=r, min_body=b, htf_ema=20, hold=72)
        for l in (10, 20) for a in (1.5, 2.0) for r in (2.0, 3.0) for b in (0.4, 0.6)
    ],
    "sweep_fade": [
        dict(look=l, atr_mult=a, rr=r, min_body=b, htf_ema=20, hold=72)
        for l in (6, 10) for a in (1.5, 2.0) for r in (3.0, 4.0) for b in (0.3, 0.5)
    ],
    "bollinger": [
        dict(bb_period=p, bb_k=k, atr_mult=a, rr=r, hold=48, atr_max_ratio=m)
        for p in (20,) for k in (2.0,) for a in (1.5, 2.0) for r in (2.0,) for m in (1.3,)
    ],
}

if __name__ == "__main__":
    print("Fetching 120d data untuk", len(CANDIDATES), "kandidat...", flush=True)
    data = {}
    for c in CANDIDATES:
        try:
            data[c] = {"5m": fetch(c, "5m", 120), "15m": fetch(c, "15m", 130),
                       "1h": fetch(c, "1h", 170)}
            print(f"  {c:<7} ok ({len(data[c]['5m'])} candles)", flush=True)
        except Exception as e:
            print(f"  {c:<7} ERR {e}", flush=True)

    results = []
    for coin, d in data.items():
        c5 = d["5m"]
        mid = len(c5) // 2
        for fam, grid in GRIDS.items():
            for params in grid:
                fn = FAMILIES[fam]
                try:
                    is_t = fn(c5[:mid], d["15m"], d["1h"], params)
                    oos_t = fn(c5[mid:], d["15m"], d["1h"], params)
                except Exception:
                    continue
                mi = metrics(is_t)
                mo = metrics(oos_t)
                if not mi or not mo:
                    continue
                if mi["n"] < 10 or mo["n"] < 15:
                    continue
                if mi["totR"] <= 0 or mo["totR"] <= 0:
                    continue
                if mo["pf"] < 1.30:
                    continue
                results.append({
                    "coin": coin, "family": fam,
                    "is_pf": round(mi["pf"], 2), "is_R": round(mi["totR"], 1), "is_n": mi["n"],
                    "oos_pf": round(mo["pf"], 2), "oos_R": round(mo["totR"], 1),
                    "oos_n": mo["n"], "oos_wr": round(mo["wr"], 1),
                    "oos_dd": round(mo["mdd"], 1), "params": params,
                })

    # best per coin
    best = {}
    for r in results:
        c = r["coin"]
        if c not in best or r["oos_R"] > best[c]["oos_R"]:
            best[c] = r

    print("\n" + "=" * 112)
    print("KANDIDAT LOLOS (OOS_PF >= 1.30, OOS_R > 0, n >= 15)")
    print("=" * 112)
    print(f"{'COIN':<8}{'FAMILY':<13}{'IS_PF':>7}{'IS_R':>7}{'OOS_PF':>8}{'OOS_R':>8}{'OOS_WR':>8}{'OOS_DD':>8}{'N':>5}")
    print("-" * 112)
    if not best:
        print("  (tidak ada kandidat yang lolos)")
    for c, r in sorted(best.items(), key=lambda kv: -kv[1]["oos_R"]):
        print(f"{c:<8}{r['family']:<13}{r['is_pf']:>7.2f}{r['is_R']:>7.1f}"
              f"{r['oos_pf']:>8.2f}{r['oos_R']:>8.1f}{r['oos_wr']:>7.1f}%{r['oos_dd']:>8.1f}{r['oos_n']:>5}")

    print("\n=== PARAMS KANDIDAT LOLOS ===")
    for c, r in sorted(best.items(), key=lambda kv: -kv[1]["oos_R"]):
        print(f"\n{c} | {r['family']} | OOS_PF={r['oos_pf']} OOS_R={r['oos_R']:+.1f} N={r['oos_n']}")
        print(f"  {r['params']}")

    with open("candidate_coins.json", "w") as f:
        json.dump(best, f, indent=2, default=str)
    print(f"\nDisimpan: candidate_coins.json ({len(best)} kandidat lolos)")

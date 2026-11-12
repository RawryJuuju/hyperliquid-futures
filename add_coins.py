#!/usr/bin/env python3
"""Tambah ARB + INJ ke portfolio, renormalisasi weight berbasis edge."""
import json, math

CFG_PATH = "/home/ubuntu/papertrade_backtest/strategy_config.json"
cfg = json.load(open(CFG_PATH))

# --- data existing (dari config) ---
existing = {}
for c, v in cfg["coins"].items():
    n = sum(s["n"] for s in v["strategies"])
    avg_r = v["combined_R"] / n if n else 0
    existing[c] = {"avg_R": round(avg_r, 4), "n": n,
                   "score": max(0.0, avg_r) * math.sqrt(n)}

# --- kandidat baru (dari walk-forward) ---
new_coins = {
    "ARB": {
        "family": "sweep_fade",
        "params": {"look": 6, "atr_mult": 2.0, "rr": 4.0, "min_body": 0.5,
                   "htf_ema": 20, "hold": 72},
        "oos_pf": 1.62, "oos_R": 9.0, "n": 20, "cluster": "A",
        "_corr_note": "max corr 0.72 vs ETH — masih OK, tapi cluster A",
        "_lev": 10,
    },
    "INJ": {
        "family": "breakout",
        "params": {"look": 10, "atr_mult": 2.0, "rr": 3.0, "min_body": 0.4,
                   "htf_ema": 20, "hold": 72},
        "oos_pf": 1.74, "oos_R": 31.2, "n": 67, "cluster": "C",
        "_corr_note": "max corr 0.67 vs ZEC — diversifier",
        "_lev": 5,   # max leverage INJ hanya 5x
    },
}

for c, d in new_coins.items():
    avg_r = d["oos_R"] / d["n"]
    existing[c] = {"avg_R": round(avg_r, 4), "n": d["n"],
                   "score": max(0.0, avg_r) * math.sqrt(d["n"])}

total_score = sum(v["score"] for v in existing.values())
print(f"total score: {total_score:.3f}\n")

print(f"{'COIN':<8}{'avg_R':>8}{'N':>5}{'score':>8}{'weight':>9}")
print("-" * 38)
new_weights = {}
for c in sorted(existing, key=lambda x: -existing[x]["score"]):
    w = existing[c]["score"] / total_score
    new_weights[c] = round(w, 4)
    print(f"{c:<8}{existing[c]['avg_R']:>8.4f}{existing[c]['n']:>5}"
          f"{existing[c]['score']:>8.2f}{w:>9.4f}")

print(f"\nsum weight: {sum(new_weights.values()):.4f}")

# --- terapkan ---
for c, w in new_weights.items():
    if c in cfg["coins"]:
        cfg["coins"][c]["weight"] = w

for c, d in new_coins.items():
    cfg["coins"][c] = {
        "cluster": d["cluster"],
        "weight": new_weights[c],
        "strategies": [{
            "name": d["family"],
            "params": d["params"],
            "oos_pf": d["oos_pf"],
            "oos_R": d["oos_R"],
            "n": d["n"],
        }],
        "combined_R": d["oos_R"],
        "combined_pf": d["oos_pf"],
        "avg_R": round(d["oos_R"] / d["n"], 4),
        "_added": "2026-10-20",
        "_corr_note": d["_corr_note"],
        "_max_leverage": d["_lev"],
    }

# update cluster map
cfg["_correlation_clusters"]["A"].append("ARB")
cfg["_correlation_clusters"]["C"].append("INJ")

cfg["_expansion_log"] = {
    "date": "2026-10-20",
    "added": ["ARB", "INJ"],
    "rejected": {
        "ZRO": "corr 0.87 vs PUMP — duplikasi",
        "STRK": "corr 0.88 vs SOL — duplikasi",
        "CRV": "corr 0.92 vs SOL — duplikasi",
        "UNI": "corr 0.85 vs SOL — duplikasi",
        "LINK": "corr 0.80 vs SOL — duplikasi",
        "AAVE": "corr 0.83 vs WLD — duplikasi",
        "kPEPE": "PF 1.50 tapi vol $9.5M & fee/risk 20% — tunda",
    },
    "total_coins": len(cfg["coins"]),
}

json.dump(cfg, open(CFG_PATH, "w"), indent=2)
print(f"\n✅ config updated: {len(cfg['coins'])} coins")
print("clusters:", {k: v for k, v in cfg["_correlation_clusters"].items() if k.startswith("cluster") or len(k) == 1})

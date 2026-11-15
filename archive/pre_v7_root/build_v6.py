#!/usr/bin/env python3
"""
Build config v6: multi-timeframe breakout.
15m = core (PF 1.34, R/day 1.92)
5m  = satellite (PF 1.07, R/day 0.64)
1h  = conviction (PF 1.51, R/day 0.39, sample kecil)
4h  = dropped (R/day 0.02)
"""
import json, math

P = "/home/ubuntu/papertrade_backtest/strategy_config.json"
c = json.load(open(P))

# parameter per timeframe (dari research_mtf)
TF_PARAMS = {
    "5m":  {"look": 10, "atr_mult": 1.5, "rr": 5.0, "min_body": 0.6,
            "htf_ema": 20, "hold": 72},
    "15m": {"look": 10, "atr_mult": 1.5, "rr": 4.0, "min_body": 0.5,
            "htf_ema": 20, "hold": 48},
    "1h":  {"look": 12, "atr_mult": 2.0, "rr": 4.0, "min_body": 0.5,
            "htf_ema": 20, "hold": 48},
}

# metrik riil per TF (dari mtf_result2)
TF_METRICS = {
    "5m":  {"pf": 1.07, "avgR": 0.063, "n": 604, "rday": 0.64, "mdd": -25.2},
    "15m": {"pf": 1.34, "avgR": 0.249, "n": 695, "rday": 1.92, "mdd": -21.5},
    "1h":  {"pf": 1.51, "avgR": 0.336, "n": 208, "rday": 0.39, "mdd": -12.2},
}

# risk weight per TF: 15m core, 5m satellite, 1h conviction
TF_RISK_WEIGHT = {"5m": 0.20, "15m": 0.55, "1h": 0.25}

COINS = ["WLD", "INJ", "ZEC", "NEAR", "HYPE", "ENA", "PUMP"]

new_coins = {}
for coin in COINS:
    old = c["coins"].get(coin)
    if not old:
        continue
    strategies = []
    for tf in ["5m", "15m", "1h"]:
        m = TF_METRICS[tf]
        strategies.append({
            "name": "breakout",
            "timeframe": tf,
            "params": TF_PARAMS[tf],
            "oos_pf": m["pf"],
            "oos_R": round(m["rday"], 2),
            "n": m["n"],
            "risk_weight": TF_RISK_WEIGHT[tf],
            "avg_R": m["avgR"],
        })
    # weight coin: rata-rata avgR * sqrt(n) dari semua TF
    score = sum(max(0, s["avg_R"]) * math.sqrt(s["n"]) for s in strategies) / len(strategies)
    new_coins[coin] = {
        "cluster": old["cluster"],
        "strategies": strategies,
        "_coin_score": round(score, 2),
    }

tot_score = sum(v["_coin_score"] for v in new_coins.values())
for coin, v in new_coins.items():
    v["weight"] = round(v["_coin_score"] / tot_score, 4)
    del v["_coin_score"]

c["coins"] = new_coins

rm = c["_risk_model"]
rm["base_risk_pct"] = 0.25
rm["max_concurrent"] = 15
rm["max_total_open_risk_pct"] = 2.25

c["_revision"] = {
    "date": "2026-10-21",
    "version": "v6-mtf",
    "reason": "Multi-timeframe research: 15m PF 1.34 R/day 1.92 (core), 5m PF 1.07 R/day 0.64 (satellite), 1h PF 1.51 R/day 0.39 (conviction), 4h dropped R/day 0.02",
    "tf_risk_weights": TF_RISK_WEIGHT,
    "tf_metrics": TF_METRICS,
    "changes": {
        "from": "single TF 5m, 7 coins, 7 slots",
        "to": "3 TF per coin (5m+15m+1h), 7 coins, 21 strategy slots",
    },
}

json.dump(c, open(P, "w"), indent=2)

print(f"coins: {len(new_coins)}")
print(f"strategies per coin: 3 (5m, 15m, 1h)")
print(f"total slots: {len(new_coins) * 3}")
print(f"base risk: {rm['base_risk_pct']}%")
print(f"max concurrent: {rm['max_concurrent']}")
print()
print(f"{'COIN':<7}{'weight':>8}{'cluster':>9}")
print("-" * 26)
for coin, v in sorted(new_coins.items(), key=lambda x: -x[1]["weight"]):
    print(f"{coin:<7}{v['weight']:>8.4f}{v['cluster']:>9}")
print()
print("risk weight per TF:")
for tf, w in TF_RISK_WEIGHT.items():
    print(f"  {tf:<5} {w*100:.0f}% of coin risk")

#!/usr/bin/env python3
"""Apply 6 perubahan: matikan sweep_fade+bollinger, breakout RR 1:5, base 0.25%, slot 12."""
import json

P = "/home/ubuntu/papertrade_backtest/strategy_config.json"
c = json.load(open(P))

removed = []
kept = []
for coin in list(c["coins"].keys()):
    cc = c["coins"][coin]
    new_strats = []
    for s in cc["strategies"]:
        if s["name"] in ("sweep_fade", "bollinger"):
            removed.append(f"{coin}:{s['name']}")
            continue
        # breakout -> RR 1:5
        if s["name"] == "breakout":
            s["params"]["rr"] = 5.0
        new_strats.append(s)
    if not new_strats:
        del c["coins"][coin]
        continue
    cc["strategies"] = new_strats
    # recompute combined dari strategi tersisa
    cc["combined_R"] = sum(s["oos_R"] for s in new_strats)
    cc["combined_pf"] = round(sum(s["oos_pf"] * s["n"] for s in new_strats) /
                              sum(s["n"] for s in new_strats), 2)
    kept.append(coin)

# renormalisasi weight
import math
scores = {}
for coin, cc in c["coins"].items():
    n = sum(s["n"] for s in cc["strategies"])
    avg_r = cc["combined_R"] / n if n else 0
    scores[coin] = max(0.0, avg_r) * math.sqrt(n)

tot = sum(scores.values())
for coin in c["coins"]:
    c["coins"][coin]["weight"] = round(scores[coin] / tot, 4)

# risk model
rm = c["_risk_model"]
rm["base_risk_pct"] = 0.25
rm["max_concurrent"] = 12
rm["max_total_open_risk_pct"] = 2.25

# cluster map cleanup
for k in ("A", "B", "C", "D"):
    c["_correlation_clusters"][k] = [x for x in c["_correlation_clusters"][k] if x in c["coins"]]

c["_revision"] = {
    "date": "2026-10-21",
    "reason": "Forensic: sweep_fade PF 0.51-0.67 semua RR varian. bollinger live PF 0.34. Breakout RR 1:5 = +17R vs 1:3 = -3.4R. BE lock fatal (-317R).",
    "removed_strategies": removed,
    "kept": kept,
    "changes": {
        "breakout_rr": "3.0 -> 5.0",
        "base_risk_pct": "0.55 -> 0.25",
        "max_concurrent": "6 -> 12",
        "be_lock": "disabled (proven -317R)",
    },
}

json.dump(c, open(P, "w"), indent=2)
print(f"removed: {len(removed)}")
for r in removed:
    print(f"  - {r}")
print(f"\nkept coins: {len(kept)} -> {', '.join(kept)}")
print(f"base risk: {rm['base_risk_pct']}%")
print(f"slots    : {rm['max_concurrent']}")
print(f"\nweights:")
for coin, cc in sorted(c["coins"].items(), key=lambda x: -x[1]["weight"]):
    print(f"  {coin:<6} {cc['weight']:.4f}  RR={cc['strategies'][0]['params']['rr']}")

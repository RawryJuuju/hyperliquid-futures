#!/usr/bin/env python3
"""
Test: apakah menggabungkan 2 strategi per koin (primary + secondary)
lebih baik dari 1 strategi saja? Ukur di OOS 60d.
"""
import json
from engine import fetch, FAMILIES, metrics

# kandidat terbaik per koin dari research_walkforward.json
r = json.load(open("/home/ubuntu/papertrade_backtest/research_walkforward.json"))
by_coin = {}
for x in r:
    c = x["coin"]
    by_coin.setdefault(c, []).append(x)

# ambil top-2 distinct family per coin
cands = {}
for c, lst in by_coin.items():
    lst.sort(key=lambda x: -x["oos_R"])
    seen_fam = set()
    picks = []
    for x in lst:
        if x["family"] in seen_fam:
            continue
        seen_fam.add(x["family"])
        picks.append(x)
        if len(picks) == 2:
            break
    cands[c] = picks

print("=" * 100)
print("KANDIDAT 2 STRATEGI PER KOIN")
print("=" * 100)
for c, picks in sorted(cands.items()):
    print(f"\n{c}:")
    for p in picks:
        print(f"  {p['family']:<14} OOS_PF={p['oos_pf']:.2f} OOS_R={p['oos_R']:+.1f} N={p['oos_n']}")
        print(f"    {p['params']}")

print("\n" + "=" * 100)
print("TEST: single vs combined (OOS 60d)")
print("=" * 100)

results = {}
for c, picks in sorted(cands.items()):
    try:
        d = {"5m": fetch(c, "5m", 120), "15m": fetch(c, "15m", 130), "1h": fetch(c, "1h", 170)}
    except Exception as e:
        print(f"{c}: fetch err {e}")
        continue
    mid = len(d["5m"]) // 2
    oos5 = d["5m"][mid:]

    per_fam = []
    for p in picks:
        fn = FAMILIES[p["family"]]
        tr = fn(oos5, d["15m"], d["1h"], p["params"])
        m = metrics(tr)
        if m:
            per_fam.append((p["family"], m, tr))

    if not per_fam:
        continue

    # single = best family only
    best_single = max(per_fam, key=lambda x: x[1]["totR"])

    # combined = union of all trades (both strategies run concurrently)
    all_tr = []
    for _, _, tr in per_fam:
        all_tr.extend(tr)
    mcomb = metrics(all_tr)

    results[c] = {
        "single_family": best_single[0],
        "single_R": best_single[1]["totR"],
        "single_n": best_single[1]["n"],
        "single_pf": best_single[1]["pf"],
        "comb_R": mcomb["totR"] if mcomb else 0,
        "comb_n": mcomb["n"] if mcomb else 0,
        "comb_pf": mcomb["pf"] if mcomb else 0,
        "fams": [f for f, _, _ in per_fam],
    }

print(f"{'COIN':<7}{'SINGLE':<16}{'S_R':>8}{'S_N':>5}{'S_PF':>7}  |  {'COMB_R':>8}{'C_N':>5}{'C_PF':>7}{'BETTER':>8}")
print("-" * 100)
tot_s = tot_c = 0
for c, x in sorted(results.items()):
    better = "COMB" if x["comb_R"] > x["single_R"] else "single"
    tot_s += x["single_R"]
    tot_c += x["comb_R"]
    print(f"{c:<7}{x['single_family']:<16}{x['single_R']:>+8.1f}{x['single_n']:>5}{x['single_pf']:>7.2f}  |  "
          f"{x['comb_R']:>+8.1f}{x['comb_n']:>5}{x['comb_pf']:>7.2f}{better:>8}")
print("-" * 100)
print(f"{'TOTAL':<23}{tot_s:>+8.1f}{'':>5}{'':>7}  |  {tot_c:>+8.1f}")
print(f"\nCombined wins: {sum(1 for x in results.values() if x['comb_R'] > x['single_R'])}/{len(results)}")

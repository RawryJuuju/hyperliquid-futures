import json

r = json.load(open("/home/ubuntu/papertrade_backtest/research_walkforward.json"))
print(f"total survivors: {len(r)}\n")

# best per (family, coin)
best = {}
for x in r:
    k = (x["family"], x["coin"])
    if k not in best or x["oos_R"] > best[k]["oos_R"]:
        best[k] = x

print("=" * 118)
print("BEST CONFIG PER (FAMILY, COIN) — sorted by OOS R")
print("=" * 118)
print(f"{'FAMILY':<14}{'COIN':<7}{'IS_PF':>7}{'IS_R':>7}{'OOS_PF':>8}{'OOS_R':>8}{'OOS_WR':>8}{'OOS_DD':>8}{'N':>4}")
print("-" * 118)
for k, x in sorted(best.items(), key=lambda kv: -kv[1]["oos_R"]):
    print(f"{x['family']:<14}{x['coin']:<7}{x['is_pf']:>7.2f}{x['is_R']:>7.1f}"
          f"{x['oos_pf']:>8.2f}{x['oos_R']:>8.1f}{x['oos_wr']:>7.1f}%{x['oos_mdd']:>8.1f}{x['oos_n']:>4}")

print("\n" + "=" * 118)
print("PARAMS untuk TOP 8")
print("=" * 118)
for k, x in sorted(best.items(), key=lambda kv: -kv[1]["oos_R"])[:8]:
    print(f"\n{x['family']} | {x['coin']} | OOS_R={x['oos_R']:+.1f} PF={x['oos_pf']:.2f} N={x['oos_n']}")
    print(f"  params: {x['params']}")

# portfolio view: 1 config per coin, best available
print("\n" + "=" * 118)
print("PORTFOLIO: best single strategy per coin (only OOS_PF >= 1.3)")
print("=" * 118)
per_coin = {}
for x in r:
    if x["oos_pf"] < 1.3: continue
    c = x["coin"]
    if c not in per_coin or x["oos_R"] > per_coin[c]["oos_R"]:
        per_coin[c] = x

print(f"{'COIN':<7}{'FAMILY':<14}{'OOS_PF':>8}{'OOS_R':>8}{'OOS_WR':>8}{'OOS_DD':>8}{'N':>5}")
print("-" * 118)
totR = 0; totN = 0
for c, x in sorted(per_coin.items(), key=lambda kv: -kv[1]["oos_R"]):
    print(f"{c:<7}{x['family']:<14}{x['oos_pf']:>8.2f}{x['oos_R']:>8.1f}{x['oos_wr']:>7.1f}%{x['oos_mdd']:>8.1f}{x['oos_n']:>5}")
    totR += x["oos_R"]; totN += x["oos_n"]
print("-" * 118)
print(f"{'TOTAL':<7}{'':<14}{'':>8}{totR:>+8.1f}{'':>8}{'':>8}{totN:>5}")
print(f"\ncoins qualified: {len(per_coin)}")

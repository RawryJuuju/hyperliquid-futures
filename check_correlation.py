#!/usr/bin/env python3
"""Cek korelasi kandidat baru vs 9 coin existing + likuiditas + max leverage."""
import json, statistics
from engine import fetch, FAMILIES, metrics

EXISTING = ["PUMP", "WLD", "ZEC", "ENA", "NEAR", "HYPE", "ETH", "SOL", "XRP"]
CAND = json.load(open("/home/ubuntu/papertrade_backtest/candidate_coins.json"))
CFG = json.load(open("/home/ubuntu/papertrade_backtest/strategy_config.json"))


def get_trades(coin, family, params, days=120):
    d = {"5m": fetch(coin, "5m", days), "15m": fetch(coin, "15m", days + 10),
         "1h": fetch(coin, "1h", days + 50)}
    fn = FAMILIES[family]
    return fn(d["5m"], d["15m"], d["1h"], params)


def buckets(rs, k=6):
    if not rs:
        return [0.0] * k
    size = max(1, len(rs) // k)
    out = []
    for i in range(k):
        seg = rs[i * size:(i + 1) * size]
        out.append(sum(seg) if seg else 0.0)
    return out


if __name__ == "__main__":
    print("Fetching trades existing 9 coins...")
    ex = {}
    for c in EXISTING:
        cc = CFG["coins"][c]
        allr = []
        for s in cc["strategies"]:
            try:
                allr.extend([t["R"] for t in get_trades(c, s["name"], s["params"])])
            except Exception:
                pass
        ex[c] = buckets(allr)
        print(f"  {c:<6} {len(allr)} trades")

    print("\nFetching candidate trades...")
    cand_b = {}
    for c, info in CAND.items():
        try:
            tr = get_trades(c, info["family"], info["params"])
            cand_b[c] = buckets([t["R"] for t in tr])
            print(f"  {c:<7} {len(tr)} trades")
        except Exception as e:
            print(f"  {c:<7} ERR {e}")

    print("\n" + "=" * 100)
    print("KORELASI KANDIDAT vs PORTFOLIO EXISTING (max abs corr)")
    print("=" * 100)
    print(f"{'CAND':<8}{'max|corr|':>11}{'vs coin':<10}{'avg|corr|':>11}{'OOS_PF':>8}{'OOS_R':>8}{'VERDICT':>12}")
    print("-" * 100)

    rows = []
    for c, cb in cand_b.items():
        cors = []
        for e, eb in ex.items():
            m = min(len(cb), len(eb))
            try:
                r = statistics.correlation(cb[:m], eb[:m])
                if r == r:  # not nan
                    cors.append((abs(r), e, r))
            except Exception:
                pass
        if not cors:
            continue
        cors.sort(reverse=True)
        maxc, maxcoin, realmax = cors[0]
        avgc = sum(x[0] for x in cors) / len(cors)
        info = CAND[c]
        # verdict
        if maxc < 0.5:
            v = "DIVERSIFIER"
        elif maxc < 0.75:
            v = "OK"
        else:
            v = "TERLALU MIRIP"
        rows.append((c, maxc, maxcoin, avgc, info["oos_pf"], info["oos_R"], v))
        print(f"{c:<8}{maxc:>11.2f}{maxcoin:<10}{avgc:>11.2f}{info['oos_pf']:>8.2f}"
              f"{info['oos_R']:>+8.1f}{v:>12}")

    print("-" * 100)
    print("\n=== REKOMENDASI (corr < 0.75 + PF >= 1.4) ===")
    good = [r for r in rows if r[1] < 0.75 and r[4] >= 1.40]
    for r in sorted(good, key=lambda x: -x[5]):
        print(f"  {r[0]:<8} corr={r[1]:.2f} (vs {r[2]})  PF={r[4]:.2f}  R={r[5]:+.1f}  -> {r[6]}")
    if not good:
        print("  (tidak ada)")

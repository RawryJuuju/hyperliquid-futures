"""Validate the only surviving edge: sweep_fade + market entry + ATR2.0 + RR3.
Test across 5 coins, 90d, IS/OOS split."""
from stratlib2 import fetch, stats
from research_grid import run_grid

COINS = ["BTC", "ETH", "ZEC", "HYPE", "SOL"]

CFG = dict(mode="sweep_fade", entry="market", lookback=6, atr_mult=2.0,
           rr=3.0, ttl=8, max_hold=72, be_at=None, min_body=0.3, ema_htf=20)

if __name__ == "__main__":
    print("Fetching 90d x 5 coins...")
    data = {}
    for c in COINS:
        data[c] = {"5m": fetch(c, "5m", 90), "15m": fetch(c, "15m", 100), "1h": fetch(c, "1h", 130)}
        print(f"  {c} ok")

    print("\n" + "="*100)
    print("VALIDATION: sweep_fade + market entry + ATR 2.0 + RR 3.0 + no BE")
    print("="*100)
    print(f"{'COIN':<7}{'WINDOW':<14}{'N':>4}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>7}{'MaxDD':>8}")
    print("-"*100)
    grand = 0
    for c in COINS:
        c5 = data[c]["5m"]; mid = len(c5)//2
        for label, seg in [("FULL 90d", c5), ("IS 45d", c5[:mid]), ("OOS 45d", c5[mid:])]:
            tr = run_grid(seg, data[c]["15m"], data[c]["1h"], CFG)
            st = stats(tr, label)
            if st["n"] == 0:
                print(f"{c:<7}{label:<14}{0:>4}"); continue
            if label == "FULL 90d": grand += st["totR"]
            print(f"{c:<7}{label:<14}{st['n']:>4}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>+9.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}")
        print("-"*100)

    print(f"\nGRAND TOTAL R (all 5 coins, 90d): {grand:+.1f}")

    print("\n=== PARAM SENSITIVITY (all coins, 90d) ===")
    print(f"{'VARIANT':<24}{'TotR':>9}{'N':>6}{'PFavg':>8}")
    tests = {
        "ATR2.0 RR3.0":  {**CFG},
        "ATR2.0 RR2.5":  {**CFG, "rr": 2.5},
        "ATR2.0 RR4.0":  {**CFG, "rr": 4.0},
        "ATR2.5 RR3.0":  {**CFG, "atr_mult": 2.5},
        "ATR1.75 RR3.0": {**CFG, "atr_mult": 1.75},
        "look4":         {**CFG, "lookback": 4},
        "look10":        {**CFG, "lookback": 10},
        "hold48":        {**CFG, "max_hold": 48},
        "hold120":       {**CFG, "max_hold": 120},
        "body0.5":       {**CFG, "min_body": 0.5},
    }
    for name, cfg in tests.items():
        tot = 0.0; ns = 0; pfs = []
        for c in COINS:
            tr = run_grid(data[c]["5m"], data[c]["15m"], data[c]["1h"], cfg)
            st = stats(tr)
            tot += st["totR"]; ns += st["n"]
            if st["n"] > 0: pfs.append(st["pf"])
        print(f"{name:<24}{tot:>+9.1f}{ns:>6}{(sum(pfs)/len(pfs) if pfs else 0):>8.2f}")

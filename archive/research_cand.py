"""Final candidate: sweep_fade market ATR2.0 RR3.0 body0.5 look10 — per coin IS/OOS."""
from stratlib2 import fetch, stats
from research_grid import run_grid

COINS = ["BTC", "ETH", "ZEC", "HYPE", "SOL"]

CANDS = {
 "C1_body0.5": dict(mode="sweep_fade", entry="market", lookback=6, atr_mult=2.0,
                    rr=3.0, ttl=8, max_hold=72, be_at=None, min_body=0.5, ema_htf=20),
 "C2_body0.5_l10": dict(mode="sweep_fade", entry="market", lookback=10, atr_mult=2.0,
                        rr=3.0, ttl=8, max_hold=72, be_at=None, min_body=0.5, ema_htf=20),
 "C3_body0.5_rr4": dict(mode="sweep_fade", entry="market", lookback=6, atr_mult=2.0,
                        rr=4.0, ttl=8, max_hold=72, be_at=None, min_body=0.5, ema_htf=20),
 "C4_body0.6_atr25": dict(mode="sweep_fade", entry="market", lookback=6, atr_mult=2.5,
                          rr=3.0, ttl=8, max_hold=72, be_at=None, min_body=0.6, ema_htf=20),
}

if __name__ == "__main__":
    print("Fetching 120d x 5 coins...")
    data = {}
    for c in COINS:
        data[c] = {"5m": fetch(c, "5m", 120), "15m": fetch(c, "15m", 130), "1h": fetch(c, "1h", 170)}
        print(f"  {c} ok")

    for cname, cfg in CANDS.items():
        print("\n" + "="*104)
        print(f"  {cname}")
        print("="*104)
        print(f"{'COIN':<7}{'WINDOW':<13}{'N':>4}{'WR%':>7}{'PF':>7}{'TotR':>9}{'AvgR':>7}{'MaxDD':>8}")
        print("-"*104)
        grand_all = 0; grand_no_btc = 0
        for c in COINS:
            c5 = data[c]["5m"]; mid = len(c5)//2
            for label, seg in [("FULL 120d", c5), ("IS 60d", c5[:mid]), ("OOS 60d", c5[mid:])]:
                tr = run_grid(seg, data[c]["15m"], data[c]["1h"], cfg)
                st = stats(tr, label)
                if st["n"] == 0:
                    print(f"{c:<7}{label:<13}{0:>4}"); continue
                if label == "FULL 120d":
                    grand_all += st["totR"]
                    if c != "BTC": grand_no_btc += st["totR"]
                print(f"{c:<7}{label:<13}{st['n']:>4}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>+9.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}")
            print("-"*104)
        print(f"  GRAND ALL 5: {grand_all:+.1f}R   |   EXCL BTC: {grand_no_btc:+.1f}R")

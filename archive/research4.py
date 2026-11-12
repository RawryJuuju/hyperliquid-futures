#!/usr/bin/env python3
"""Round 4: konfirmasi ETH-only vs BTC, plus final param lock (Q4) + stress test."""
from stratlib import fetch, run_v2, stats

Q4 = dict(lookback=6, sl_model="atr", atr_mult=1.2, rr=2.0, ttl=5, max_hold=60,
          require_slope=True, min_body=0.45, min_strength=1.0, be_at=0.8)

if __name__ == "__main__":
    print("Fetching 90d both coins...")
    d = {}
    for coin in ["ETH", "BTC"]:
        d[coin] = {"5m": fetch(coin, "5m", 90), "15m": fetch(coin, "15m", 100), "1h": fetch(coin, "1h", 130)}
        print(f"  {coin}: 5m={len(d[coin]['5m'])}")

    print("\n" + "="*92)
    print("FINAL PARAM Q4 (lookback=6, ATR1.2 SL, RR2.0, be@0.8R, slope+strength+body filter)")
    print("="*92)
    print(f"{'COIN':<8}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}{'TP':>5}{'BEP':>5}{'SL':>5}{'TIME':>6}{'AvgBars':>9}")
    print("-"*92)
    tot_eth = 0
    for coin in ["ETH", "BTC"]:
        tr = run_v2(d[coin]["5m"], d[coin]["15m"], d[coin]["1h"], Q4)
        st = stats(tr, coin)
        sl_cnt = st["n"] - st["TP"] - st["BEP"] - st["TIME"] - st["TRAIL"]
        if coin == "ETH": tot_eth = st["totR"]
        print(f"{coin:<8}{st['n']:>5}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}{st['TP']:>5}{st['BEP']:>5}{sl_cnt:>5}{st['TIME']:>6}{st['avgBars']:>9.1f}")

    print("\n" + "="*92)
    print("MONTHLY BREAKDOWN ETH (Q4) - konsistensi antar bulan")
    print("="*92)
    c5 = d["ETH"]["5m"]
    # split into 3 x 30d windows
    third = len(c5)//3
    for k, label in enumerate(["Bulan -3", "Bulan -2", "Bulan -1"]):
        seg = c5[k*third:(k+1)*third]
        tr = run_v2(seg, d["ETH"]["15m"], d["ETH"]["1h"], Q4)
        st = stats(tr, label)
        if st["n"] == 0:
            print(f"  {label}: 0 trades"); continue
        print(f"  {label:<10} N={st['n']:>3}  WR={st['wr']:>5.1f}%  PF={st['pf']:>5.2f}  TotR={st['totR']:>+6.1f}  MaxDD={st['mdd']:>5.1f}")

    print("\n" + "="*92)
    print("SENSITIVITY: apakah edge tahan kalau parameter digeser? (ETH 90d)")
    print("="*92)
    tests = {
        "ATR 1.0": {**Q4, "atr_mult": 1.0},
        "ATR 1.4": {**Q4, "atr_mult": 1.4},
        "RR 1.8": {**Q4, "rr": 1.8},
        "RR 2.2": {**Q4, "rr": 2.2},
        "BE 0.6R": {**Q4, "be_at": 0.6},
        "BE 1.0R": {**Q4, "be_at": 1.0},
        "Body 0.35": {**Q4, "min_body": 0.35},
        "Body 0.55": {**Q4, "min_body": 0.55},
    }
    for name, cfg in tests.items():
        tr = run_v2(d["ETH"]["5m"], d["ETH"]["15m"], d["ETH"]["1h"], cfg)
        st = stats(tr, name)
        print(f"  {name:<12} N={st['n']:>3}  WR={st['wr']:>5.1f}%  PF={st['pf']:>5.2f}  TotR={st['totR']:>+6.1f}")

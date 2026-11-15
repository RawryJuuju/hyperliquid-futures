#!/usr/bin/env python3
"""Round 6: VALIDASI FINAL kandidat R8 vs R4 vs R2. ETH + BTC, IS/OOS split."""
from stratlib import fetch, run_v2, stats

CAND = {
 "R8_ttl20":  dict(lookback=6, sl_model="atr", atr_mult=1.0, rr=2.0, ttl=20, max_hold=60,
                   require_slope=True, min_body=0.45, min_strength=1.0, be_at=1.0),
 "R4_ttl12_l8": dict(lookback=8, sl_model="atr", atr_mult=1.0, rr=2.0, ttl=12, max_hold=60,
                   require_slope=True, min_body=0.45, min_strength=1.0, be_at=1.0),
 "R2_ttl12":  dict(lookback=6, sl_model="atr", atr_mult=1.0, rr=2.0, ttl=12, max_hold=60,
                   require_slope=True, min_body=0.45, min_strength=1.0, be_at=1.0),
}

if __name__ == "__main__":
    print("Fetching 120d ETH + BTC...")
    d={}
    for coin in ["ETH","BTC"]:
        d[coin]={"5m":fetch(coin,"5m",120),"15m":fetch(coin,"15m",130),"1h":fetch(coin,"1h",170)}
        print(f"  {coin}: {len(d[coin]['5m'])} candles 5m")

    for name,cfg in CAND.items():
        print("\n" + "="*96)
        print(f"  {name}")
        print("="*96)
        print(f"{'COIN':<6}{'WINDOW':<12}{'N':>4}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}")
        print("-"*96)
        for coin in ["ETH","BTC"]:
            c5=d[coin]["5m"]; c15=d[coin]["15m"]; c1h=d[coin]["1h"]
            mid=len(c5)//2
            for label,seg in [("FULL 120d",c5),("IS (first 60d)",c5[:mid]),("OOS (last 60d)",c5[mid:])]:
                tr=run_v2(seg,c15,c1h,cfg); st=stats(tr,label)
                if st["n"]==0:
                    print(f"{coin:<6}{label:<12}{0:>4}   (no trades)"); continue
                print(f"{coin:<6}{label:<12}{st['n']:>4}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}")

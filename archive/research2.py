#!/usr/bin/env python3
"""
Round 2 research: cari kombinasi filter yang beneran punya edge.
Fokus: (a) kenapa BTC jelek, (b) filter kualitas entry, (c) exit model terbaik.
"""
import urllib.request, json, time
exec(open("/home/ubuntu/papertrade_backtest/research.py").read().split('if __name__')[0])

def run_v2(c5, c15, c1h, cfg):
    """Trend-following pullback with quality filters + optional HTF strength gate."""
    n=len(c5)
    closes=[c["c"] for c in c5]
    e20=ema_series(closes,20); e50=ema_series(closes,50)
    a=atr(c5,14)
    m15,m1h=align_htf(c5,c15,c1h)
    closes15=[c["c"] for c in c15]; closes1h=[c["c"] for c in c1h]
    e15=ema_series(closes15,20); e1h=ema_series(closes1h,20); e1h50=ema_series(closes1h,50)

    trades=[]; busy=-1
    look=cfg["lookback"]

    for i in range(max(80,look+2), n-1):
        if i<=busy: continue
        cur=c5[i-1]; k15,k1h=m15[i-1],m1h[i-1]
        if None in (e15[k15], e1h[k1h], e1h50[k1h], e20[i-1], e50[i-1], a[i-1]): continue

        up15=closes15[k15]>e15[k15]
        up1h=closes1h[k1h]>e1h[k1h]
        slope= e1h[k1h]>e1h50[k1h]

        # trend strength: how far price from 1h EMA20, normalized by ATR
        strength = abs(closes1h[k1h]-e1h[k1h])/a[i-1] if a[i-1] else 0
        if cfg.get("min_strength") and strength < cfg["min_strength"]: continue
        if cfg.get("max_strength") and strength > cfg["max_strength"]: continue

        rng=c5[i-1-look:i-1]
        lh=max(x["h"] for x in rng); ll=min(x["l"] for x in rng)
        body=abs(cur["c"]-cur["o"]); rngc=max(cur["h"]-cur["l"],1e-9)
        br=body/rngc
        vols=[x["v"] for x in c5[max(0,i-21):i-1]]; avgv=sum(vols)/len(vols) if vols else 1
        vratio=cur["v"]/avgv if avgv else 1

        direction=None
        if cur["l"]<ll and cur["c"]>ll and up15 and up1h: direction="LONG"
        elif cur["h"]>lh and cur["c"]<lh and (not up15) and (not up1h): direction="SHORT"
        if not direction: continue
        if cfg.get("require_slope"):
            if direction=="LONG" and not slope: continue
            if direction=="SHORT" and slope: continue
        if br < cfg.get("min_body",0): continue
        if cfg.get("min_vol") and vratio < cfg["min_vol"]: continue
        # 5m EMA alignment
        if cfg.get("ema5_align"):
            if direction=="LONG" and not (cur["c"]>e20[i-1]): continue
            if direction=="SHORT" and not (cur["c"]<e20[i-1]): continue

        if direction=="LONG":
            entry=(cur["l"]+cur["c"])/2; stop_ref=cur["l"]
        else:
            entry=(cur["h"]+cur["c"])/2; stop_ref=cur["h"]

        atr_v=a[i-1]
        if cfg["sl_model"]=="atr":
            dist=atr_v*cfg["atr_mult"]; sl= entry-dist if direction=="LONG" else entry+dist
        else:
            sl= entry*(1-cfg["sl"]) if direction=="LONG" else entry*(1+cfg["sl"])
        risk=abs(entry-sl)
        if risk<=0: continue
        if risk/entry > cfg.get("max_risk_pct",0.02): continue
        if risk/entry < cfg.get("min_risk_pct",0.0012): continue

        tp = entry+risk*cfg["rr"] if direction=="LONG" else entry-risk*cfg["rr"]

        fill=None
        for j in range(i,min(i+cfg["ttl"],n)):
            if direction=="LONG" and c5[j]["l"]<=entry: fill=j; break
            if direction=="SHORT" and c5[j]["h"]>=entry: fill=j; break
        if fill is None: continue

        be_at=cfg.get("be_at"); cur_sl=sl; outcome=None; exit_p=None; bars=0
        for j in range(fill+1,min(fill+cfg["max_hold"]+1,n)):
            bars+=1
            h,l=c5[j]["h"],c5[j]["l"]
            r_now=(h-entry)/risk if direction=="LONG" else (entry-l)/risk
            if be_at and r_now>=be_at: cur_sl=entry
            if direction=="LONG" and l<=cur_sl:
                outcome="SL" if cur_sl==sl else "BEP"; exit_p=cur_sl; break
            if direction=="SHORT" and h>=cur_sl:
                outcome="SL" if cur_sl==sl else "BEP"; exit_p=cur_sl; break
            if direction=="LONG" and h>=tp: outcome="TP"; exit_p=tp; break
            if direction=="SHORT" and l<=tp: outcome="TP"; exit_p=tp; break
        if outcome is None:
            exit_p=c5[min(fill+cfg["max_hold"],n-1)]["c"]; outcome="TIME"

        pnl=(exit_p-entry) if direction=="LONG" else (entry-exit_p)
        R=pnl/risk; fee=(entry+exit_p)*0.0004/risk
        trades.append({"dir":direction,"R":R-fee,"outcome":outcome,"bars":bars})
        busy=fill+max(bars,1)
    return trades

if __name__=="__main__":
    print("Fetching 30d...")
    data={}
    for coin in ["ETH","BTC"]:
        data[coin]={"5m":fetch(coin,"5m",30),"15m":fetch(coin,"15m",40),"1h":fetch(coin,"1h",60)}

    V={
     "P1_base":        dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,be_at=1.0),
     "P2_body60":      dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.60,be_at=1.0),
     "P3_vol12":       dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_vol=1.2,be_at=1.0),
     "P4_ema5":        dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,ema5_align=True,be_at=1.0),
     "P5_strength":    dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,min_strength=1.0,be_at=1.0),
     "P6_combo":       dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,ema5_align=True,min_vol=1.1,be_at=1.0),
     "P7_combo_rr15":  dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=1.5,ttl=5,max_hold=60,require_slope=True,min_body=0.45,ema5_align=True,min_vol=1.1,be_at=0.8),
     "P8_combo_rr30":  dict(lookback=6,sl_model="atr",atr_mult=1.2,rr=3.0,ttl=5,max_hold=80,require_slope=True,min_body=0.45,ema5_align=True,min_vol=1.1,be_at=1.0),
     "P9_atr20":       dict(lookback=6,sl_model="atr",atr_mult=2.0,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,ema5_align=True,min_vol=1.1,be_at=1.0),
     "P10_atr08":      dict(lookback=6,sl_model="atr",atr_mult=0.8,rr=2.0,ttl=5,max_hold=60,require_slope=True,min_body=0.45,ema5_align=True,min_vol=1.1,be_at=1.0),
    }

    print("\n"+"="*112)
    print(f"{'VARIANT':<18}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}{'TP':>5}{'BEP':>5}{'TIME':>6}{'AvgBar':>8}")
    print("="*112)
    allres={}
    for coin in ["ETH","BTC"]:
        for name,cfg in V.items():
            tr=run_v2(data[coin]["5m"],data[coin]["15m"],data[coin]["1h"],cfg)
            st=stats(tr,name); allres[(coin,name)]=st
            if st["n"]==0:
                print(f"{coin+' '+name:<18}{0:>5}"); continue
            print(f"{coin+' '+name:<18}{st['n']:>5}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}{st['TP']:>5}{st['BEP']:>5}{st['TIME']:>6}{st['avgBars']:>8.1f}")
        print("-"*112)

    print("\n=== RANK BY COMBINED TotR (min 12 trades each) ===")
    rows=[]
    for name in V:
        a=allres[("ETH",name)]; b=allres[("BTC",name)]
        if a.get("n",0)>=12 and b.get("n",0)>=12:
            rows.append((name, a["pf"], b["pf"], a["totR"]+b["totR"], a["n"]+b["n"], (a["pf"]+b["pf"])/2))
    for r in sorted(rows,key=lambda x:-x[3]):
        print(f"  {r[0]:<18} PF_ETH={r[1]:5.2f} PF_BTC={r[2]:5.2f}  TotR={r[3]:7.1f}  N={r[4]:3d}  PF_avg={r[5]:5.2f}")

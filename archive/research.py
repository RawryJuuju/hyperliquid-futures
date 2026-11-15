#!/usr/bin/env python3
"""
Strategy Research Harness - Papertrade Scalp
Tujuan: cari varian entry/exit yang beneran punya edge di data riil Hyperliquid.
Semua hasil di sini = backtest nyata, bukan opini.
"""
import urllib.request, json, time, math
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
URL = "https://api.hyperliquid.xyz/info"

def fetch(coin, interval, days=30):
    now_ms = int(time.time()*1000)
    start = now_ms - days*24*3600*1000
    p = json.dumps({"type":"candleSnapshot","req":{"coin":coin,"interval":interval,"startTime":start}}).encode()
    r = urllib.request.Request(URL, data=p, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        raw = json.loads(resp.read().decode())
    return [{"t":k["t"],"o":float(k["o"]),"h":float(k["h"]),"l":float(k["l"]),"c":float(k["c"]),"v":float(k["v"])} for k in raw]

def ema_series(vals, period):
    if len(vals) < period: return [None]*len(vals)
    k = 2/(period+1)
    out = [None]*(period-1)
    e = sum(vals[:period])/period
    out.append(e)
    for v in vals[period:]:
        e = v*k + e*(1-k)
        out.append(e)
    return out

def atr(candles, period=14):
    out=[None]
    trs=[]
    for i in range(1,len(candles)):
        h,l,pc = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
        if len(trs)>=period:
            out.append(sum(trs[-period:])/period)
        else:
            out.append(None)
    return out

def align_htf(c5, c15, c1h):
    """Map each 5m candle index to the last closed 15m and 1h candle before it."""
    i15 = 0; i1h = 0
    m15 = []; m1h = []
    for c in c5:
        while i15+1 < len(c15) and c15[i15+1]["t"] <= c["t"]:
            i15 += 1
        while i1h+1 < len(c1h) and c1h[i1h+1]["t"] <= c["t"]:
            i1h += 1
        m15.append(i15); m1h.append(i1h)
    return m15, m1h

def run_variant(name, c5, c15, c1h, cfg):
    """Generic runner with configurable filters + exit model."""
    n = len(c5)
    closes = [c["c"] for c in c5]
    e20 = ema_series(closes, 20)
    e50 = ema_series(closes, 50)
    a = atr(c5, 14)
    m15, m1h = align_htf(c5, c15, c1h)

    closes15 = [c["c"] for c in c15]; closes1h = [c["c"] for c in c1h]
    e15 = ema_series(closes15, cfg.get("htf_ema",20))
    e1h = ema_series(closes1h, cfg.get("htf_ema",20))
    e1h_slow = ema_series(closes1h, 50)

    trades = []
    busy_until = -1
    look = cfg["lookback"]

    for i in range(max(60, look+2), n-1):
        if i <= busy_until: continue
        cur = c5[i-1]  # last CLOSED candle
        k15, k1h = m15[i-1], m1h[i-1]

        # --- HTF trend gate ---
        if e15[k15] is None or e1h[k1h] is None or e1h_slow[k1h] is None: continue
        up15 = closes15[k15] > e15[k15]
        up1h = closes1h[k1h] > e1h[k1h]
        slope_up = e1h[k1h] > e1h_slow[k1h]

        # --- 5m local structure ---
        rng = c5[i-1-look:i-1]
        lh = max(x["h"] for x in rng); ll = min(x["l"] for x in rng)

        body = abs(cur["c"]-cur["o"]); rngc = max(cur["h"]-cur["l"], 1e-9)
        body_ratio = body/rngc
        vols = [x["v"] for x in c5[max(0,i-21):i-1]]
        avgv = sum(vols)/len(vols) if vols else 1
        vratio = cur["v"]/avgv if avgv else 1

        direction = None
        # LONG: sweep below local low then close back above it, in an uptrend
        if cur["l"] < ll and cur["c"] > ll and up15 and up1h:
            direction = "LONG"
        # SHORT: sweep above local high then close back below, in a downtrend
        elif cur["h"] > lh and cur["c"] < lh and (not up15) and (not up1h):
            direction = "SHORT"
        if not direction: continue

        # --- Extra filters ---
        if cfg.get("require_slope") and direction=="LONG" and not slope_up: continue
        if cfg.get("require_slope") and direction=="SHORT" and slope_up: continue
        if cfg.get("min_body_ratio") and body_ratio < cfg["min_body_ratio"]: continue
        if cfg.get("max_body_ratio") and body_ratio > cfg["max_body_ratio"]: continue
        if cfg.get("min_vol") and vratio < cfg["min_vol"]: continue

        # --- Entry at 50% retrace of trigger candle (limit) ---
        if direction == "LONG":
            entry = (cur["l"] + cur["c"]) / 2
            stop_ref = cur["l"]
        else:
            entry = (cur["h"] + cur["c"]) / 2
            stop_ref = cur["h"]

        # --- SL model ---
        if cfg["sl_model"] == "pct":
            sl = entry*(1-cfg["sl"]) if direction=="LONG" else entry*(1+cfg["sl"])
        else:  # atr
            atr_v = a[i-1] or (entry*0.004)
            dist = atr_v*cfg["atr_mult"]
            sl = entry-dist if direction=="LONG" else entry+dist
        risk = abs(entry-sl)
        if risk <= 0: continue

        # Risk sanity: skip absurd risk (news spike / illiquid wick)
        if risk/entry > cfg.get("max_risk_pct", 0.02): continue
        if risk/entry < cfg.get("min_risk_pct", 0.0015): continue

        tp = entry + risk*cfg["rr"] if direction=="LONG" else entry - risk*cfg["rr"]

        # --- Fill window: limit must be touched within N bars ---
        fill_i = None
        for j in range(i, min(i+cfg["ttl"], n)):
            if direction=="LONG" and c5[j]["l"] <= entry: fill_i=j; break
            if direction=="SHORT" and c5[j]["h"] >= entry: fill_i=j; break
        if fill_i is None: continue

        # --- Exit management ---
        be_at = cfg.get("be_at")   # move SL to entry after X R
        trail_at = cfg.get("trail_at")
        cur_sl = sl
        outcome=None; exit_p=None; bars=0
        for j in range(fill_i+1, min(fill_i+cfg["max_hold"]+1, n)):
            bars += 1
            h,l = c5[j]["h"], c5[j]["l"]
            # progress in R
            if direction=="LONG":
                r_now = (h-entry)/risk
            else:
                r_now = (entry-l)/risk
            if be_at and r_now >= be_at:
                cur_sl = entry if direction=="LONG" else entry
            if trail_at and r_now >= trail_at:
                lock = entry + risk*(r_now-cfg.get("trail_gap",0.5)) if direction=="LONG" else entry - risk*(r_now-cfg.get("trail_gap",0.5))
                cur_sl = max(cur_sl,lock) if direction=="LONG" else min(cur_sl,lock)

            # stop first (conservative)
            if direction=="LONG" and l <= cur_sl: outcome="SL" if cur_sl==sl else ("BEP" if cur_sl==entry else "TRAIL"); exit_p=cur_sl; break
            if direction=="SHORT" and h >= cur_sl: outcome="SL" if cur_sl==sl else ("BEP" if cur_sl==entry else "TRAIL"); exit_p=cur_sl; break
            if direction=="LONG" and h >= tp: outcome="TP"; exit_p=tp; break
            if direction=="SHORT" and l <= tp: outcome="TP"; exit_p=tp; break

        if outcome is None:
            exit_p = c5[min(fill_i+cfg["max_hold"], n-1)]["c"]
            outcome = "TIME"

        pnl = (exit_p-entry) if direction=="LONG" else (entry-exit_p)
        R = pnl/risk
        fee_R = (entry+exit_p)*0.0004/risk
        trades.append({"dir":direction,"R":R-fee_R,"outcome":outcome,"bars":bars})
        busy_until = fill_i + max(bars,1)

    return trades

def stats(trades, label):
    if not trades: return {"label":label,"n":0}
    wins=[t for t in trades if t["R"]>0]
    losses=[t for t in trades if t["R"]<=0]
    gw=sum(t["R"] for t in wins); gl=abs(sum(t["R"] for t in losses))
    pf = gw/gl if gl>0 else 99
    n=len(trades)
    wr=len(wins)/n*100
    tot=sum(t["R"] for t in trades)
    # max drawdown in R
    eq=0; peak=0; mdd=0
    for t in trades:
        eq+=t["R"]; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    tp=sum(1 for t in trades if t["outcome"]=="TP")
    bep=sum(1 for t in trades if t["outcome"]=="BEP")
    tr=sum(1 for t in trades if t["outcome"]=="TRAIL")
    tm=sum(1 for t in trades if t["outcome"]=="TIME")
    return {"label":label,"n":n,"wr":wr,"pf":pf,"totR":tot,"mdd":mdd,
            "TP":tp,"BEP":bep,"TRAIL":tr,"TIME":tm,
            "avgR":tot/n,"avgBars":sum(t["bars"] for t in trades)/n}

if __name__ == "__main__":
    print("Fetching data (30d)...")
    data={}
    for coin in ["ETH","BTC"]:
        data[coin]={"5m":fetch(coin,"5m",30),"15m":fetch(coin,"15m",40),"1h":fetch(coin,"1h",60)}
        print(f"  {coin}: 5m={len(data[coin]['5m'])} 15m={len(data[coin]['15m'])} 1h={len(data[coin]['1h'])}")

    variants = {
        "A_current(loose)": dict(lookback=6, sl_model="pct", sl=0.0030, rr=2.0, ttl=5, max_hold=60),
        "B_slope+body":     dict(lookback=6, sl_model="pct", sl=0.0030, rr=2.0, ttl=5, max_hold=60,
                                 require_slope=True, min_body_ratio=0.45),
        "C_atr_sl":         dict(lookback=6, sl_model="atr", atr_mult=1.2, rr=2.0, ttl=5, max_hold=60,
                                 require_slope=True, min_body_ratio=0.45),
        "D_bep_lock":       dict(lookback=6, sl_model="atr", atr_mult=1.2, rr=2.5, ttl=5, max_hold=60,
                                 require_slope=True, min_body_ratio=0.45, be_at=1.0),
        "E_trail":          dict(lookback=6, sl_model="atr", atr_mult=1.2, rr=3.0, ttl=5, max_hold=60,
                                 require_slope=True, min_body_ratio=0.45, be_at=1.0, trail_at=1.5, trail_gap=0.6),
        "F_tight_look":     dict(lookback=4, sl_model="atr", atr_mult=1.2, rr=2.5, ttl=4, max_hold=48,
                                 require_slope=True, min_body_ratio=0.45, be_at=1.0),
        "G_vol_confirm":    dict(lookback=6, sl_model="atr", atr_mult=1.2, rr=2.5, ttl=5, max_hold=60,
                                 require_slope=True, min_body_ratio=0.45, be_at=1.0, min_vol=1.1),
        "H_wide_look":      dict(lookback=12, sl_model="atr", atr_mult=1.5, rr=2.5, ttl=6, max_hold=72,
                                 require_slope=True, min_body_ratio=0.45, be_at=1.0),
    }

    print("\n" + "="*118)
    print(f"{'VARIANT':<20}{'N':>5}{'WR%':>7}{'PF':>7}{'TotR':>8}{'AvgR':>7}{'MaxDD':>8}{'TP':>5}{'BEP':>5}{'TRL':>5}{'TIME':>6}{'AvgBar':>8}")
    print("="*118)
    results={}
    for coin in ["ETH","BTC"]:
        d=data[coin]
        for vname,cfg in variants.items():
            tr = run_variant(vname, d["5m"], d["15m"], d["1h"], cfg)
            st = stats(tr, vname)
            results[(coin,vname)]=st
            if st["n"]==0:
                print(f"{coin+' '+vname:<20}{'0':>5}")
                continue
            print(f"{coin+' '+vname:<20}{st['n']:>5}{st['wr']:>7.1f}{st['pf']:>7.2f}{st['totR']:>8.1f}{st['avgR']:>7.2f}{st['mdd']:>8.1f}{st['TP']:>5}{st['BEP']:>5}{st['TRAIL']:>5}{st['TIME']:>6}{st['avgBars']:>8.1f}")
        print("-"*118)

    # Best combined
    print("\n=== RANKING (avg PF across ETH+BTC) ===")
    rank=[]
    for vname in variants:
        a=results.get(("ETH",vname)); b=results.get(("BTC",vname))
        if a and b and a["n"]>10 and b["n"]>10:
            rank.append((vname,(a["pf"]+b["pf"])/2, a["totR"]+b["totR"], a["n"]+b["n"]))
    for v,pf,tr,n in sorted(rank,key=lambda x:-x[1]):
        print(f"  {v:<20} PF_avg={pf:5.2f}  TotR={tr:7.1f}  N={n}")

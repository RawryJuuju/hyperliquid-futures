"""Clean strategy library for research. Import this, don't exec other files."""
import urllib.request, json, time

URL = "https://api.hyperliquid.xyz/info"

def fetch(coin, interval, days=30):
    now_ms = int(time.time()*1000)
    start = now_ms - days*24*3600*1000
    p = json.dumps({"type":"candleSnapshot","req":{"coin":coin,"interval":interval,"startTime":start}}).encode()
    r = urllib.request.Request(URL, data=p, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r, timeout=25) as resp:
        raw = json.loads(resp.read().decode())
    return [{"t":k["t"],"o":float(k["o"]),"h":float(k["h"]),"l":float(k["l"]),
             "c":float(k["c"]),"v":float(k["v"])} for k in raw]

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
    out=[None]; trs=[]
    for i in range(1,len(candles)):
        h,l,pc = candles[i]["h"], candles[i]["l"], candles[i-1]["c"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
        out.append(sum(trs[-period:])/period if len(trs)>=period else None)
    return out

def align_htf(c5, c15, c1h):
    i15 = 0; i1h = 0; m15 = []; m1h = []
    for c in c5:
        while i15+1 < len(c15) and c15[i15+1]["t"] <= c["t"]: i15 += 1
        while i1h+1 < len(c1h) and c1h[i1h+1]["t"] <= c["t"]: i1h += 1
        m15.append(i15); m1h.append(i1h)
    return m15, m1h

def run_v2(c5, c15, c1h, cfg):
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
        if None in (e15[k15], e1h[k1h], e1h50[k1h], e20[i-1], a[i-1]): continue

        up15=closes15[k15]>e15[k15]
        up1h=closes1h[k1h]>e1h[k1h]
        slope= e1h[k1h]>e1h50[k1h]

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
        if cfg.get("ema5_align"):
            if direction=="LONG" and not (cur["c"]>e20[i-1]): continue
            if direction=="SHORT" and not (cur["c"]<e20[i-1]): continue

        entry=(cur["l"]+cur["c"])/2 if direction=="LONG" else (cur["h"]+cur["c"])/2

        atr_v=a[i-1]
        if cfg["sl_model"]=="atr":
            dist=atr_v*cfg["atr_mult"]
            sl= entry-dist if direction=="LONG" else entry+dist
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

def stats(trades, label=""):
    if not trades: return {"label":label,"n":0,"wr":0,"pf":0,"totR":0,"mdd":0,"TP":0,"BEP":0,"TRAIL":0,"TIME":0,"avgR":0,"avgBars":0}
    wins=[t for t in trades if t["R"]>0]; losses=[t for t in trades if t["R"]<=0]
    gw=sum(t["R"] for t in wins); gl=abs(sum(t["R"] for t in losses))
    pf = gw/gl if gl>0 else 99
    n=len(trades); wr=len(wins)/n*100; tot=sum(t["R"] for t in trades)
    eq=0; peak=0; mdd=0
    for t in trades:
        eq+=t["R"]; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {"label":label,"n":n,"wr":wr,"pf":pf,"totR":tot,"mdd":mdd,
            "TP":sum(1 for t in trades if t["outcome"]=="TP"),
            "BEP":sum(1 for t in trades if t["outcome"]=="BEP"),
            "TRAIL":sum(1 for t in trades if t["outcome"]=="TRAIL"),
            "TIME":sum(1 for t in trades if t["outcome"]=="TIME"),
            "avgR":tot/n,"avgBars":sum(t["bars"] for t in trades)/n}

"""Extended strategy library v2: FVG, BOS, displacement, partials, trailing."""
import urllib.request, json, time

URL = "https://api.hyperliquid.xyz/info"

def fetch(coin, interval, days=60):
    now_ms = int(time.time()*1000)
    start = now_ms - days*24*3600*1000
    p = json.dumps({"type":"candleSnapshot","req":{"coin":coin,"interval":interval,"startTime":start}}).encode()
    r = urllib.request.Request(URL, data=p, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        raw = json.loads(resp.read().decode())
    return [{"t":k["t"],"o":float(k["o"]),"h":float(k["h"]),"l":float(k["l"]),
             "c":float(k["c"]),"v":float(k["v"])} for k in raw]

def ema_series(vals, period):
    if len(vals) < period: return [None]*len(vals)
    k = 2/(period+1); out=[None]*(period-1)
    e = sum(vals[:period])/period; out.append(e)
    for v in vals[period:]:
        e = v*k + e*(1-k); out.append(e)
    return out

def atr_series(candles, period=14):
    out=[None]; trs=[]
    for i in range(1,len(candles)):
        h,l,pc = candles[i]["h"],candles[i]["l"],candles[i-1]["c"]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
        out.append(sum(trs[-period:])/period if len(trs)>=period else None)
    return out

def adx_series(candles, period=14):
    """Wilder ADX."""
    n=len(candles); out=[None]*n
    if n < period*2: return out
    tr=[];pdm=[];ndm=[]
    for i in range(1,n):
        h,l,ph,pl,pc = candles[i]["h"],candles[i]["l"],candles[i-1]["h"],candles[i-1]["l"],candles[i-1]["c"]
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
        up=h-ph; dn=pl-l
        pdm.append(up if (up>dn and up>0) else 0.0)
        ndm.append(dn if (dn>up and dn>0) else 0.0)
    atr_s=sum(tr[:period]); pdi_s=sum(pdm[:period]); ndi_s=sum(ndm[:period])
    dxs=[]
    for i in range(period, len(tr)):
        atr_s = atr_s - atr_s/period + tr[i]
        pdi_s = pdi_s - pdi_s/period + pdm[i]
        ndi_s = ndi_s - ndi_s/period + ndm[i]
        if atr_s<=0: dxs.append(0); continue
        pdi=100*pdi_s/atr_s; ndi=100*ndi_s/atr_s
        denom=pdi+ndi
        dxs.append(100*abs(pdi-ndi)/denom if denom>0 else 0)
    if len(dxs)<period: return out
    adx=sum(dxs[:period])/period
    out[period*2]=adx
    for i in range(period, len(dxs)):
        adx=(adx*(period-1)+dxs[i])/period
        idx=period+i+1
        if idx<n: out[idx]=adx
    return out

def align_htf(c5, c15, c1h):
    i15=0;i1h=0;m15=[];m1h=[]
    for c in c5:
        while i15+1<len(c15) and c15[i15+1]["t"]<=c["t"]: i15+=1
        while i1h+1<len(c1h) and c1h[i1h+1]["t"]<=c["t"]: i1h+=1
        m15.append(i15); m1h.append(i1h)
    return m15,m1h

def find_fvg(candles, i, direction):
    """3-candle imbalance: gap between candle i-2 high and i low (bullish)."""
    if i < 3: return None
    a,b,c = candles[i-3], candles[i-2], candles[i-1]
    if direction=="LONG":
        # bullish FVG: low of c > high of a
        if c["l"] > a["h"]:
            return (a["h"], c["l"])
    else:
        if c["h"] < a["l"]:
            return (c["h"], a["l"])
    return None

def run_v3(c5, c15, c1h, cfg):
    """v3: trend gate + ADX + FVG optional + displacement + partial TP + trailing."""
    n=len(c5)
    closes=[c["c"] for c in c5]
    e20=ema_series(closes,20)
    a=atr_series(c5,14)
    adx=adx_series(c5,14) if cfg.get("min_adx") else [None]*n
    m15,m1h=align_htf(c5,c15,c1h)
    closes15=[c["c"] for c in c15]; closes1h=[c["c"] for c in c1h]
    e15=ema_series(closes15,20); e1h=ema_series(closes1h,20); e1h50=ema_series(closes1h,50)

    trades=[]; busy=-1; look=cfg["lookback"]

    for i in range(max(100,look+3), n-1):
        if i<=busy: continue
        cur=c5[i-1]; k15,k1h=m15[i-1],m1h[i-1]
        if None in (e15[k15],e1h[k1h],e1h50[k1h],a[i-1]): continue

        up15=closes15[k15]>e15[k15]; up1h=closes1h[k1h]>e1h[k1h]
        slope=e1h[k1h]>e1h50[k1h]
        strength=abs(closes1h[k1h]-e1h[k1h])/a[i-1]
        if cfg.get("min_strength") and strength<cfg["min_strength"]: continue
        if cfg.get("min_adx") and (adx[i-1] is None or adx[i-1]<cfg["min_adx"]): continue

        rng=c5[i-1-look:i-1]
        lh=max(x["h"] for x in rng); ll=min(x["l"] for x in rng)
        body=abs(cur["c"]-cur["o"]); rngc=max(cur["h"]-cur["l"],1e-9)
        br=body/rngc
        if br<cfg.get("min_body",0): continue

        vols=[x["v"] for x in c5[max(0,i-21):i-1]]
        avgv=sum(vols)/len(vols) if vols else 1
        vratio=cur["v"]/avgv if avgv else 1
        if cfg.get("min_vol") and vratio<cfg["min_vol"]: continue

        direction=None
        if cur["l"]<ll and cur["c"]>ll and up15 and up1h: direction="LONG"
        elif cur["h"]>lh and cur["c"]<lh and (not up15) and (not up1h): direction="SHORT"
        if not direction: continue
        if cfg.get("require_slope"):
            if direction=="LONG" and not slope: continue
            if direction=="SHORT" and slope: continue

        # displacement: body must exceed X * ATR
        disp = body/a[i-1]
        if cfg.get("min_disp") and disp<cfg["min_disp"]: continue

        # FVG requirement
        fvg = find_fvg(c5, i, direction)
        if cfg.get("require_fvg") and not fvg: continue

        # entry: FVG midpoint if available else 50% retrace
        if cfg.get("entry_fvg") and fvg:
            entry=(fvg[0]+fvg[1])/2
        else:
            entry=(cur["l"]+cur["c"])/2 if direction=="LONG" else (cur["h"]+cur["c"])/2

        dist=a[i-1]*cfg["atr_mult"]
        sl = entry-dist if direction=="LONG" else entry+dist
        risk=abs(entry-sl)
        if risk<=0: continue
        if risk/entry>cfg.get("max_risk_pct",0.02): continue
        if risk/entry<cfg.get("min_risk_pct",0.001): continue

        tp1 = entry+risk*cfg.get("tp1_r",1.5) if direction=="LONG" else entry-risk*cfg.get("tp1_r",1.5)
        tp2 = entry+risk*cfg.get("tp2_r",3.0) if direction=="LONG" else entry-risk*cfg.get("tp2_r",3.0)

        fill=None
        for j in range(i,min(i+cfg["ttl"],n)):
            if direction=="LONG" and c5[j]["l"]<=entry: fill=j; break
            if direction=="SHORT" and c5[j]["h"]>=entry: fill=j; break
        if fill is None: continue

        be_at=cfg.get("be_at"); cur_sl=sl
        tp1_hit=False; realized=0.0; rem=1.0
        outcome=None; exit_p=None; bars=0

        for j in range(fill+1,min(fill+cfg["max_hold"]+1,n)):
            bars+=1
            h,l=c5[j]["h"],c5[j]["l"]
            r_now=(h-entry)/risk if direction=="LONG" else (entry-l)/risk

            if be_at and r_now>=be_at: cur_sl=entry

            # partial at tp1
            if cfg.get("partial") and not tp1_hit:
                hit1 = (h>=tp1) if direction=="LONG" else (l<=tp1)
                if hit1:
                    realized += cfg["partial_frac"]*cfg["tp1_r"]
                    rem = 1-cfg["partial_frac"]
                    tp1_hit=True

            # stop check (remaining portion)
            if direction=="LONG" and l<=cur_sl:
                r_exit = (cur_sl-entry)/risk
                realized += rem*r_exit
                outcome="SL" if cur_sl==sl else "BEP"; exit_p=cur_sl; break
            if direction=="SHORT" and h>=cur_sl:
                r_exit = (entry-cur_sl)/risk
                realized += rem*r_exit
                outcome="SL" if cur_sl==sl else "BEP"; exit_p=cur_sl; break

            # final target
            if direction=="LONG" and h>=tp2:
                realized += rem*cfg.get("tp2_r",3.0)
                outcome="TP"; exit_p=tp2; break
            if direction=="SHORT" and l<=tp2:
                realized += rem*cfg.get("tp2_r",3.0)
                outcome="TP"; exit_p=tp2; break

        if outcome is None:
            exit_p=c5[min(fill+cfg["max_hold"],n-1)]["c"]
            r_exit=(exit_p-entry)/risk if direction=="LONG" else (entry-exit_p)/risk
            realized += rem*r_exit
            outcome="TIME"

        fee_R=(entry+exit_p)*0.0004/risk
        trades.append({"dir":direction,"R":realized-fee_R,"outcome":outcome,"bars":bars})
        busy=fill+max(bars,1)
    return trades

def stats(trades, label=""):
    if not trades: return {"label":label,"n":0,"wr":0,"pf":0,"totR":0,"mdd":0,"TP":0,"BEP":0,"TIME":0,"avgR":0,"avgBars":0}
    wins=[t for t in trades if t["R"]>0]; losses=[t for t in trades if t["R"]<=0]
    gw=sum(t["R"] for t in wins); gl=abs(sum(t["R"] for t in losses))
    pf=gw/gl if gl>0 else 99
    n=len(trades); wr=len(wins)/n*100; tot=sum(t["R"] for t in trades)
    eq=0;peak=0;mdd=0
    for t in trades:
        eq+=t["R"]; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {"label":label,"n":n,"wr":wr,"pf":pf,"totR":tot,"mdd":mdd,
            "TP":sum(1 for t in trades if t["outcome"]=="TP"),
            "BEP":sum(1 for t in trades if t["outcome"]=="BEP"),
            "TIME":sum(1 for t in trades if t["outcome"]=="TIME"),
            "avgR":tot/n,"avgBars":sum(t["bars"] for t in trades)/n}

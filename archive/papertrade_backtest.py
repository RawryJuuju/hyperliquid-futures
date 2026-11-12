#!/usr/bin/env python3
"""
Hyperliquid / Papertrade.xyz Synthetic Perps Backtester
Asset: ETH & BTC (5m Timeframe)
Model: Pool-to-peer BBO Execution, RR 1:2, Fast Target, Max Hold 1-2 Hours (Time Exit)
No Real Funds Required (Pure Paper Engine)
"""
import urllib.request
import json
import time
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

def fetch_hyperliquid_candles(coin="ETH", interval="5m", days=3):
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 24 * 3600 * 1000)
    
    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms
        }
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
        
    candles = []
    for k in raw:
        candles.append({
            "timestamp": k["t"],
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "time_str": datetime.fromtimestamp(k["t"]/1000, tz=WIB).strftime("%Y-%m-%d %H:%M")
        })
    return candles

def run_papertrade_simulation(candles, coin="ETH", rr=2.0, max_bars_hold=18):
    """
    Simulates trades using Papertrade's pool-to-peer BBO execution.
    Entry: Swing Failure / Liquidity Sweep (SFP)
    SL: Past swing wick (+ small buffer)
    TP: Entry + (2 * Risk)
    Max Hold: 18 bars (90 minutes) -> Time Exit at market
    Fee: 0.04% per trade (standard perp taker fee)
    """
    trades = []
    in_trade_until = -1
    
    # Adaptive risk limits
    min_risk = 1.0 if coin == "ETH" else 25.0
    max_risk = 25.0 if coin == "ETH" else 500.0
    buffer = 0.5 if coin == "ETH" else 10.0
    
    for i in range(20, len(candles) - max_bars_hold):
        if i <= in_trade_until:
            continue
            
        lookback = candles[i-20:i]
        recent_high = max(c["high"] for c in lookback)
        recent_low = min(c["low"] for c in lookback)
        cur = candles[i]
        
        # 1. SETUP SHORT (Sweep High / SFP)
        if cur["high"] > recent_high and cur["close"] < recent_high:
            entry = cur["close"]
            sl = cur["high"] + buffer
            risk = sl - entry
            
            if min_risk <= risk <= max_risk:
                tp = entry - (risk * rr)
                outcome = None
                exit_price = None
                bars_held = 0
                
                for j in range(i + 1, i + 1 + max_bars_hold):
                    bars_held += 1
                    c_next = candles[j]
                    # Check SL hit first (conservative assumption)
                    if c_next["high"] >= sl:
                        outcome = "SL_HIT"
                        exit_price = sl
                        break
                    elif c_next["low"] <= tp:
                        outcome = "TP_HIT"
                        exit_price = tp
                        break
                        
                if outcome is None:
                    final_candle = candles[i + max_bars_hold]
                    exit_price = final_candle["close"]
                    pnl_raw = entry - exit_price
                    outcome = "TIME_EXIT_PROFIT" if pnl_raw > 0 else "TIME_EXIT_LOSS"
                    bars_held = max_bars_hold
                    
                pnl = entry - exit_price
                # Calculate fee deduction (0.04% open + 0.04% close)
                fee = (entry + exit_price) * 0.0004
                net_pnl = pnl - fee
                
                trades.append({
                    "coin": coin,
                    "time": cur["time_str"],
                    "dir": "SHORT",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "exit": exit_price,
                    "outcome": outcome,
                    "bars": bars_held,
                    "dur_min": bars_held * 5,
                    "pnl": net_pnl,
                    "r_mult": net_pnl / risk
                })
                in_trade_until = i + bars_held
                
        # 2. SETUP LONG (Sweep Low / SFP)
        elif cur["low"] < recent_low and cur["close"] > recent_low:
            entry = cur["close"]
            sl = cur["low"] - buffer
            risk = entry - sl
            
            if min_risk <= risk <= max_risk:
                tp = entry + (risk * rr)
                outcome = None
                exit_price = None
                bars_held = 0
                
                for j in range(i + 1, i + 1 + max_bars_hold):
                    bars_held += 1
                    c_next = candles[j]
                    if c_next["low"] <= sl:
                        outcome = "SL_HIT"
                        exit_price = sl
                        break
                    elif c_next["high"] >= tp:
                        outcome = "TP_HIT"
                        exit_price = tp
                        break
                        
                if outcome is None:
                    final_candle = candles[i + max_bars_hold]
                    exit_price = final_candle["close"]
                    pnl_raw = exit_price - entry
                    outcome = "TIME_EXIT_PROFIT" if pnl_raw > 0 else "TIME_EXIT_LOSS"
                    bars_held = max_bars_hold
                    
                pnl = exit_price - entry
                fee = (entry + exit_price) * 0.0004
                net_pnl = pnl - fee
                
                trades.append({
                    "coin": coin,
                    "time": cur["time_str"],
                    "dir": "LONG",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "exit": exit_price,
                    "outcome": outcome,
                    "bars": bars_held,
                    "dur_min": bars_held * 5,
                    "pnl": net_pnl,
                    "r_mult": net_pnl / risk
                })
                in_trade_until = i + bars_held
                
    return trades

def summarize_results(trades, coin="ETH"):
    if not trades:
        return {"coin": coin, "total": 0}
        
    wins = [t for t in trades if "TP" in t["outcome"] or (t["outcome"] == "TIME_EXIT_PROFIT")]
    losses = [t for t in trades if "SL" in t["outcome"] or (t["outcome"] == "TIME_EXIT_LOSS")]
    tp_direct = [t for t in trades if t["outcome"] == "TP_HIT"]
    
    total = len(trades)
    winrate = (len(wins) / total) * 100
    
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    
    avg_hold = sum(t["dur_min"] for t in trades) / total
    avg_win_hold = (sum(t["dur_min"] for t in tp_direct) / len(tp_direct)) if tp_direct else 0
    total_r = sum(t["r_mult"] for t in trades)
    
    return {
        "coin": coin,
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "tp_direct": len(tp_direct),
        "winrate": winrate,
        "profit_factor": pf,
        "total_r": total_r,
        "avg_hold": avg_hold,
        "avg_win_hold": avg_win_hold,
        "trades": trades
    }

if __name__ == "__main__":
    for c in ["ETH", "BTC"]:
        cd = fetch_hyperliquid_candles(coin=c, days=3)
        tr = run_papertrade_simulation(cd, coin=c)
        res = summarize_results(tr, coin=c)
        print(f"\n=== RESULTS {c} (3 Days Hyperliquid Data) ===")
        print(f"Total Trades: {res['total']}")
        print(f"Winrate: {res['winrate']:.1f}% ({res['wins']}W / {res['losses']}L)")
        print(f"TP Hit Cepat: {res['tp_direct']} trades (Rata-rata hit target: {res['avg_win_hold']:.1f} menit)")
        print(f"Profit Factor: {res['profit_factor']:.2f}")
        print(f"Net R-Multiple: {res['total_r']:+.2f}R")
        print(f"Avg Hold Time (Semua Trade): {res['avg_hold']:.1f} menit")

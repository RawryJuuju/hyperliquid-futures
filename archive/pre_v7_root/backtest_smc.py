#!/usr/bin/env python3
"""
backtest_smc.py — Backtest SMC Silver Bullet + ICT Killzone Engine on Hyperliquid
"""
import sys
import os
import json
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/ubuntu/papertrade_backtest")
from engine import fetch, atr_series, ema_series
from smc_lib import evaluate_smc_scalp_signal, get_killzone_status, find_swings, detect_fvg, detect_displacement

COINS = ["HYPE", "NEAR", "ZEC", "INJ", "WLD", "ENA", "PUMP", "ARB"]

def run_backtest(days=30):
    print(f"=== BACKTESTING SMC SILVER BULLET ({days} Days) ===")
    all_trades = []
    
    for coin in COINS:
        print(f"Fetching {coin}...", flush=True)
        try:
            c5 = fetch(coin, "5m", days=days)
            c15 = fetch(coin, "15m", days=days)
            c1h = fetch(coin, "1h", days=days)
        except Exception as e:
            print(f"Error fetching {coin}: {e}")
            continue

        atrs = atr_series(c5, 14)
        n = len(c5)
        
        # Walk through candles
        in_pos = None
        coin_trades = []
        
        for i in range(60, n - 1):
            cur = c5[i]
            cur_atr = atrs[i]
            
            # Manage open trade
            if in_pos:
                bars_held = i - in_pos["entry_bar"]
                h = cur["h"]
                l = cur["l"]
                direction = in_pos["dir"]
                entry = in_pos["entry"]
                sl = in_pos["sl"]
                tp = in_pos["tp"]
                risk = in_pos["risk_px"]
                
                # Check Breakeven trailing: if price hits +1.2R, move SL to entry + fee buffer
                r_max = (h - entry) / risk if direction == "LONG" else (entry - l) / risk
                if r_max >= 1.2:
                    in_pos["sl"] = entry + (risk * 0.15) if direction == "LONG" else entry - (risk * 0.15)
                
                exit_r = None
                kind = None
                
                # SL check
                if (direction == "LONG" and l <= in_pos["sl"]) or (direction == "SHORT" and h >= in_pos["sl"]):
                    exit_r = -1.0 if in_pos["sl"] != entry else 0.0
                    kind = "SL" if in_pos["sl"] != entry else "BE"
                # TP check
                elif (direction == "LONG" and h >= tp) or (direction == "SHORT" and l <= tp):
                    exit_r = in_pos["rr"]
                    kind = "TP"
                # Time exit
                elif bars_held >= in_pos["hold"]:
                    exit_px = cur["c"]
                    exit_r = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
                    kind = "TIME"
                    
                if exit_r is not None:
                    trade_res = {
                        "coin": coin,
                        "dir": direction,
                        "entry": entry,
                        "risk_px": risk,
                        "R": round(exit_r, 2),
                        "kind": kind,
                        "bars": bars_held,
                        "session": in_pos.get("session", "UNKNOWN")
                    }
                    coin_trades.append(trade_res)
                    all_trades.append(trade_res)
                    in_pos = None
                    continue
                    
            # If not in position, look for setup
            if not in_pos and cur_atr:
                # Slice historical view up to current bar i
                sub_c5 = c5[:i+1]
                sub_c15 = [c for c in c15 if c["t"] <= cur["t"]]
                sub_c1h = [c for c in c1h if c["t"] <= cur["t"]]
                
                sig, reason = evaluate_smc_scalp_signal(sub_c5, sub_c15, sub_c1h, coin, cur_atr, aggressive=True)
                if sig:
                    in_pos = {
                        "entry_bar": i,
                        "dir": sig["dir"],
                        "entry": sig["entry"],
                        "sl": sig["sl"],
                        "tp": sig["tp"],
                        "risk_px": sig["risk_px"],
                        "rr": sig["rr"],
                        "hold": sig["hold"],
                        "session": sig["session"]
                    }

        # Summary per coin
        tot_r = sum(t["R"] for t in coin_trades)
        wins = [t for t in coin_trades if t["R"] > 0]
        wr = len(wins) / len(coin_trades) * 100 if coin_trades else 0
        print(f"[{coin}] Trades: {len(coin_trades)} | WR: {wr:.1f}% | Net R: {tot_r:+.2f}R")

    # Overall Summary
    total_r = sum(t["R"] for t in all_trades)
    wins = [t for t in all_trades if t["R"] > 0]
    losses = [t for t in all_trades if t["R"] < 0]
    be = [t for t in all_trades if t["R"] == 0]
    wr = len(wins) / len(all_trades) * 100 if all_trades else 0
    gross_win = sum(t["R"] for t in wins)
    gross_loss = abs(sum(t["R"] for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
    
    print("\n" + "="*50)
    print(f"📊 TOTAL SMC RESULTS ({len(COINS)} Coins, {days}d):")
    print(f"Total Trades: {len(all_trades)}")
    print(f"Win Rate    : {wr:.2f}% ({len(wins)}W / {len(losses)}L / {len(be)}BE)")
    print(f"Gross Win R : +{gross_win:.2f}R")
    print(f"Gross Loss R: -{gross_loss:.2f}R")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Net Total R : {total_r:+.2f}R")
    print("="*50)

if __name__ == "__main__":
    run_backtest(days=14)

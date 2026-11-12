#!/usr/bin/env python3
"""
Close all open positions at current market price, record to trade ledger,
update equity. Works on shadow state.
"""
import json, os, urllib.request
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE = "/home/ubuntu/papertrade_backtest"
STATE = os.path.join(BASE, "fut_state.json")
TRADES = os.path.join(BASE, "fut_trades.jsonl")
HL = "https://api.hyperliquid.xyz/info"


def now_wib():
    return datetime.now(WIB)


def post_info(payload):
    req = urllib.request.Request(
        HL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def mids():
    d = post_info({"type": "allMids"})
    return {k: float(v) for k, v in d.items()}


def main():
    state = json.load(open(STATE))
    px = mids()
    ts = now_wib().isoformat()
    closed = []

    for key in list(state["open"].keys()):
        pos = state["open"][key]
        coin = pos["coin"]
        p = px.get(coin)
        if not p:
            print(f"SKIP {key}: no price")
            continue

        entry = pos["entry"]
        size = pos["size"]
        d = pos["dir"]
        risk_px = pos["risk_px"]
        risk_usd = pos["risk_usd"]

        # PnL
        if d == "LONG":
            pnl = (p - entry) * size
            r_mult = (p - entry) / risk_px
        else:
            pnl = (entry - p) * size
            r_mult = (entry - p) / risk_px

        state["equity"] += pnl
        state["day_pnl"] += pnl

        rec = {
            "t": ts,
            "coin": coin,
            "dir": d,
            "strategy": pos["strategy"],
            "kind": "MANUAL",
            "entry": entry,
            "exit": p,
            "R": round(r_mult, 3),
            "usd": round(pnl, 2),
            "equity": round(state["equity"], 2),
        }
        closed.append(rec)

        with open(TRADES, "a") as f:
            f.write(json.dumps(rec) + "\n")

        # update per-slot stats
        st = state["stats"].setdefault(key, {"n": 0, "w": 0, "l": 0, "R": 0.0, "usd": 0.0})
        st["n"] += 1
        if pnl > 0:
            st["w"] += 1
        else:
            st["l"] += 1
        st["R"] += r_mult
        st["usd"] += pnl

        print(f"CLOSED {key:<22} {d:<5} entry {entry:.6g} -> {p:.6g}  "
              f"R {r_mult:+.2f}  PnL ${pnl:+.2f}")

        del state["open"][key]

    state["peak_equity"] = max(state.get("peak_equity", 0), state["equity"])
    json.dump(state, open(STATE, "w"), indent=1)

    print()
    print(f"equity now : ${state['equity']:.2f}")
    print(f"open left  : {len(state['open'])}")
    print(f"closed     : {len(closed)} positions this run")


if __name__ == "__main__":
    main()

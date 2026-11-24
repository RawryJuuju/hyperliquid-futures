#!/usr/bin/env python3
# Author: Juuju  |  X: @Juujutsu_  |  Telegram: @Juujutsuu
"""
Telegram command handler for futures bot.
Commands: /entry, /trade, /perps, /status, /pnl, /positions
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Config
TG_TOKEN_FILE = "/home/ubuntu/credentials/gweilovejuujubot_bot_tele_token.txt"
TG_CHAT = "1341231370"
STATE_FILE = "/home/ubuntu/hl-futures-engine/fut_state.json"
TRADES_FILE = "/home/ubuntu/hl-futures-engine/fut_trades.jsonl"
EQUITY_FILE = "/home/ubuntu/hl-futures-engine/equity_curve.jsonl"

def load_token():
    with open(TG_TOKEN_FILE) as f:
        return f.read().strip()

def send_message(token, text):
    """Send message to Telegram."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:
        print(f"Send failed: {e}")
        return False

def get_updates(token, offset=None):
    """Get updates from Telegram."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 30, "limit": 100}
    if offset:
        params["offset"] = offset
    query = "&".join(f"{k}={v}" for k,v in params.items())
    req = urllib.request.Request(f"{url}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read().decode()).get("result", [])
    except Exception as e:
        print(f"Get updates failed: {e}")
        return []

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}

def load_trades(limit=10):
    trades = []
    try:
        with open(TRADES_FILE) as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))
    except:
        pass
    return trades[-limit:]

def load_equity(limit=1):
    try:
        with open(EQUITY_FILE) as f:
            lines = f.readlines()
            if lines:
                return json.loads(lines[-1])
    except:
        pass
    return {}

def format_positions(state):
    """Format open positions for /entry."""
    open_pos = state.get("open", {})
    if not open_pos:
        return "📭 *No open positions*"
    
    wib = timezone(timedelta(hours=7))
    lines = ["📊 *OPEN POSITIONS & LIMIT ORDERS*"]
    total_risk = 0
    total_margin = 0
    
    for slot, pos in open_pos.items():
        coin = pos.get("coin", slot.split(":")[0])
        direction = pos.get("dir", "?")
        strategy = pos.get("strategy", "?")
        tf = pos.get("timeframe", "?")
        entry = pos.get("entry", 0)
        sl = pos.get("sl", 0)
        tp = pos.get("tp", 0)
        size = pos.get("size", 0)
        lev = pos.get("leverage", 10)
        risk_usd = pos.get("risk_usd", 0)
        risk_pct = pos.get("risk_pct_equity", 0)
        margin = pos.get("margin", 0)
        opened = pos.get("opened_ts", 0)
        
        total_risk += risk_pct
        total_margin += margin
        
        # Duration
        dur = ""
        if opened:
            dt = datetime.fromtimestamp(opened, wib)
            dur = f" | ⏱ {dt.strftime('%H:%M:%S')}"
        
        emoji = "🟢" if direction == "LONG" else "🔴"
        lines.append(
            f"{emoji} *{coin}* {direction} {strategy} {tf}{dur}\n"
            f"   Entry: ${entry:,.6g} | SL: ${sl:,.6g} | TP: ${tp:,.6g}\n"
            f"   Size: {size:,.4f} | Lev: {lev}x | Risk: ${risk_usd:.2f} ({risk_pct:.2f}%)"
        )
    
    equity = state.get("equity", 0)
    lines.append(f"\n💰 Equity: ${equity:.2f} | Total Risk: {total_risk:.2f}% | Margin: ${total_margin:.2f}")
    return "\n".join(lines)

def format_trades(trades):
    """Format recent trades for /trade."""
    if not trades:
        return "📭 *No trades found*"
    
    wib = timezone(timedelta(hours=7))
    lines = [f"📈 *LAST {len(trades)} TRADES*"]
    
    for t in reversed(trades):
        ts = t.get("t", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(wib)
            time_str = dt.strftime("%m-%d %H:%M")
        except:
            time_str = ts[:16]
        
        coin = t.get("coin", "?")
        side = t.get("side", "?")
        pnl = t.get("usd", 0)
        strat = t.get("strategy", "?")
        tf = t.get("tf", "?")
        rr = t.get("rr", 0)
        
        emoji = "🟢" if pnl >= 0 else "🔴"
        sign = "+" if pnl >= 0 else ""
        lines.append(f"{emoji} {time_str} {coin} {side} {strat} {tf} | {sign}${pnl:.2f} (RR 1:{rr})")
    
    return "\n".join(lines)

def format_perps(state, equity_data):
    """Format detailed perps info for /perps."""
    open_pos = state.get("open", {})
    equity = equity_data.get("equity", state.get("equity", 0))
    day_pnl = state.get("day_pnl", 0)
    week = state.get("week", "?")
    
    lines = [
        "🔮 *PERPS BOT STATUS*",
        f"💰 Equity: ${equity:.2f}",
        f"📅 Day PnL: ${day_pnl:+.2f}",
        f"📆 Week: {week}",
        f"📊 Open Positions: {len(open_pos)}",
        ""
    ]
    
    # Risk breakdown
    if open_pos:
        by_cluster = {}
        for slot, pos in open_pos.items():
            cluster = "?"
            # Simplified cluster mapping
            coin = pos.get("coin", slot.split(":")[0])
            if coin in ["ENA"]: cluster = "A"
            elif coin in ["WLD", "NEAR"]: cluster = "B"
            elif coin in ["ZEC", "INJ", "ARB"]: cluster = "C"
            elif coin in ["AVAX", "SUI", "TAO"]: cluster = "D"
            elif coin in ["PAXG"]: cluster = "E"
            elif coin in ["BTC", "ETH", "SOL"]: cluster = "F"
            
            risk = pos.get("risk_pct_equity", 0)
            by_cluster[cluster] = by_cluster.get(cluster, 0) + risk
        
        lines.append("*Risk by Cluster:*")
        for cl, risk in sorted(by_cluster.items()):
            lines.append(f"  Cluster {cl}: {risk:.2f}%")
    
    # Session info
    now = datetime.now(timezone(timedelta(hours=7)))
    hour = now.hour
    if 22 <= hour or hour < 4:
        session = "🌙 NIGHT (22-04) — Funding only"
    elif 4 <= hour < 8:
        session = "🌅 ASIA (04-08) — Breakout 1.0x, Swing 1.0x, SMC 0.5x"
    elif 8 <= hour < 14:
        session = "☀️ EU (08-14) — ALL 1.0x *GOLDEN WINDOW*"
    else:
        session = "🌆 US (14-22) — Swing 1.2x, SMC 0.7x, Breakout 0.5x"
    
    lines.append(f"\n{session}")
    lines.append(f"⏰ {now.strftime('%H:%M:%S WIB')}")
    
    return "\n".join(lines)

def format_pnl(state, equity_data):
    """Format PnL summary for /pnl."""
    equity = equity_data.get("equity", state.get("equity", 0))
    day_pnl = state.get("day_pnl", 0)
    initial = state.get("initial_equity", 1000)
    peak = state.get("peak_equity", equity)
    dd = (peak - equity) / peak * 100 if peak > 0 else 0
    
    # Load recent trades for today
    trades = load_trades(200)
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    today_trades = [t for t in trades if t.get("t", "").startswith(today)]
    today_pnl = sum(t.get("usd", 0) for t in today_trades)
    today_count = len(today_trades)
    
    return (
        f"💹 *PnL SUMMARY*\n"
        f"💰 Equity: ${equity:.2f}\n"
        f"📈 Total PnL: ${equity - initial:+.2f} ({(equity/initial - 1)*100:+.1f}%)\n"
        f"📅 Day PnL: ${day_pnl:+.2f} ({today_count} trades, ${today_pnl:+.2f})\n"
        f"🏔 Peak: ${peak:.2f} | DD: {dd:.1f}%\n"
        f"📊 Open Risk: {sum(p.get('risk_pct_equity', 0) for p in state.get('open', {}).values()):.2f}%"
    )

# Command router
COMMANDS = {
    "/entry": lambda s, e: format_positions(s),
    "/positions": lambda s, e: format_positions(s),
    "/trade": lambda s, e: format_trades(load_trades(10)),
    "/trades": lambda s, e: format_trades(load_trades(20)),
    "/perps": lambda s, e: format_perps(s, e),
    "/status": lambda s, e: format_perps(s, e),
    "/pnl": lambda s, e: format_pnl(s, e),
    "/help": lambda s, e: (
        "🤖 *FUTURES BOT COMMANDS*\n"
        "/entry, /positions — open positions & limit orders\n"
        "/trade — last 10 trades\n"
        "/trades — last 20 trades\n"
        "/perps, /status — full bot status\n"
        "/pnl — PnL summary\n"
        "/help — this message"
    ),
}

def handle_command(text, state, equity_data):
    """Route command to handler."""
    cmd = text.split()[0].lower()
    handler = COMMANDS.get(cmd)
    if handler:
        return handler(state, equity_data)
    return None

def main():
    token = load_token()
    print(f"🤖 Bot command handler started (chat: {TG_CHAT})")
    
    offset = 0
    while True:
        try:
            updates = get_updates(token, offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id"))
                text = msg.get("text", "").strip()
                
                if chat_id != TG_CHAT:
                    continue
                
                if not text.startswith("/"):
                    continue
                
                print(f"📩 Command: {text}")
                state = load_state()
                equity_data = load_equity()
                response = handle_command(text, state, equity_data)
                
                if response:
                    send_message(token, response)
                else:
                    send_message(token, f"❓ Unknown command: {text}\nType /help for list")
                    
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()

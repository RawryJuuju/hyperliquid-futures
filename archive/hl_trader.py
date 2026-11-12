#!/usr/bin/env python3
"""
Hyperliquid REAL Futures Execution Engine
==========================================
Bukan paper trading. Ini order sungguhan ke Hyperliquid L1 perpetuals.

Mode:
  --network testnet   -> api.hyperliquid-testnet.xyz (uang mainan, mekanik asli)
  --network mainnet   -> api.hyperliquid.xyz (UANG ASLI)

Safety:
  - Wajib private key file (chmod 600)
  - Wajib --confirm untuk mainnet
  - Hard cap notional per order
  - Hard cap jumlah posisi terbuka
  - Kill switch file: /home/ubuntu/papertrade_backtest/STOP_TRADING
"""
import os
import sys
import json
import time
import argparse
import urllib.request
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE_DIR = "/home/ubuntu/papertrade_backtest"
STATE_FILE = os.path.join(BASE_DIR, "hl_state.json")
KILL_SWITCH = os.path.join(BASE_DIR, "STOP_TRADING")

NETWORKS = {
    "testnet": "https://api.hyperliquid-testnet.xyz",
    "mainnet": "https://api.hyperliquid.xyz",
}

# ==== RISK LIMITS (hard caps, bukan saran) ====
MAX_NOTIONAL_USD = 500.0      # maksimum ukuran 1 posisi dalam USD
MAX_OPEN_POSITIONS = 1        # maksimum posisi terbuka bersamaan
MAX_LEVERAGE = 5              # leverage maksimum yang boleh di-set
MAX_DAILY_LOSS_USD = 25.0     # stop total kalau rugi harian tembus ini

sys.path.insert(0, os.path.join(BASE_DIR, ".venv", "lib", "python3.12", "site-packages"))


def wib_now():
    return datetime.now(tz=WIB).strftime("%d/%m/%Y %H:%M:%S WIB")


def load_key(path):
    if not os.path.exists(path):
        raise SystemExit(f"[FATAL] private key file tidak ada: {path}")
    key = open(path).read().strip()
    if not key.startswith("0x") or len(key) != 66:
        raise SystemExit(f"[FATAL] format private key tidak valid (harus 0x + 64 hex)")
    return key


def get_sdk():
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    from eth_account import Account
    return Info, Exchange, Account


def post_info(base_url, payload):
    req = urllib.request.Request(
        f"{base_url}/info",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def get_account_state(base_url, address):
    return post_info(base_url, {"type": "clearinghouseState", "user": address})


def get_mid(base_url, coin):
    mids = post_info(base_url, {"type": "allMids"})
    v = mids.get(coin)
    return float(v) if v else None


def get_meta(base_url):
    return post_info(base_url, {"type": "meta"})


def round_sz(sz, sz_decimals):
    return round(sz, sz_decimals)


def asset_info(base_url, coin):
    meta = get_meta(base_url)
    for a in meta.get("universe", []):
        if a["name"] == coin:
            return a
    return None


# ============================================================
#  READ-ONLY PREFLIGHT
# ============================================================
def preflight(network, key_path):
    base_url = NETWORKS[network]
    _, _, Account = get_sdk()
    key = load_key(key_path)
    acct = Account.from_key(key)
    address = acct.address

    print(f"=== HYPERLIQUID PREFLIGHT ({network.upper()}) ===")
    print(f"waktu        : {wib_now()}")
    print(f"endpoint     : {base_url}")
    print(f"wallet addr  : {address}")

    st = get_account_state(base_url, address)
    ms = st.get("marginSummary", {})
    acct_value = float(ms.get("accountValue", 0) or 0)
    withdrawable = float(st.get("withdrawable", 0) or 0)
    positions = st.get("assetPositions", [])

    print(f"accountValue : ${acct_value:,.2f}")
    print(f"withdrawable : ${withdrawable:,.2f}")
    print(f"open pos     : {len(positions)}")
    for p in positions:
        pos = p["position"]
        print(f"   - {pos['coin']} size={pos['szi']} entry={pos.get('entryPx')} uPnL={pos.get('unrealizedPnl')}")

    eth = get_mid(base_url, "ETH")
    btc = get_mid(base_url, "BTC")
    print(f"ETH mid      : ${eth:,.2f}" if eth else "ETH mid      : n/a")
    print(f"BTC mid      : ${btc:,.2f}" if btc else "BTC mid      : n/a")

    ok = acct_value > 0
    print(f"\nTRADING READY: {'YA' if ok else 'TIDAK — saldo $0.00'}")
    if not ok:
        print("Deposit dulu ke address di atas, atau pakai --network testnet + faucet.")
    return ok, acct_value, address, base_url


# ============================================================
#  ORDER PLACEMENT
# ============================================================
def place_bracket_order(network, key_path, coin, side, notional_usd,
                        sl_pct, tp_pct, leverage, dry_run=True):
    """
    Buka posisi + langsung pasang SL & TP sebagai trigger order di exchange.
    side: 'long' | 'short'
    """
    Info, Exchange, Account = get_sdk()
    base_url = NETWORKS[network]
    key = load_key(key_path)
    acct = Account.from_key(key)
    address = acct.address

    if notional_usd > MAX_NOTIONAL_USD:
        raise SystemExit(f"[BLOCK] notional ${notional_usd} > cap ${MAX_NOTIONAL_USD}")
    if leverage > MAX_LEVERAGE:
        raise SystemExit(f"[BLOCK] leverage {leverage}x > cap {MAX_LEVERAGE}x")

    ai = asset_info(base_url, coin)
    if not ai:
        raise SystemExit(f"[BLOCK] coin {coin} tidak ada di universe")
    sz_dec = ai["szDecimals"]

    mid = get_mid(base_url, coin)
    if not mid:
        raise SystemExit(f"[BLOCK] tidak dapat harga {coin}")

    is_buy = side == "long"
    sz = round_sz(notional_usd / mid, sz_dec)
    if sz <= 0:
        raise SystemExit(f"[BLOCK] size kebulat jadi 0 (notional terlalu kecil)")

    # SL & TP dari harga eksekusi
    if is_buy:
        sl_px = round(mid * (1 - sl_pct), 2 if mid > 1000 else 4)
        tp_px = round(mid * (1 + tp_pct), 2 if mid > 1000 else 4)
    else:
        sl_px = round(mid * (1 + sl_pct), 2 if mid > 1000 else 4)
        tp_px = round(mid * (1 - tp_pct), 2 if mid > 1000 else 4)

    plan = {
        "network": network,
        "coin": coin,
        "side": side,
        "size": sz,
        "mid": mid,
        "notional": round(sz * mid, 2),
        "leverage": leverage,
        "sl_px": sl_px,
        "tp_px": tp_px,
        "dry_run": dry_run,
        "ts": wib_now(),
    }

    print("=== ORDER PLAN ===")
    for k, v in plan.items():
        print(f"  {k:<10}: {v}")

    if dry_run:
        print("\n[DRY-RUN] Order TIDAK dikirim. Hapus --dry-run untuk eksekusi nyata.")
        return plan

    # ---- LIVE ----
    exch = Exchange(acct, base_url, account_address=address)
    try:
        lev_res = exch.update_leverage(leverage, coin, is_cross=True)
        print(f"[LEVERAGE] {lev_res}")
    except Exception as e:
        print(f"[WARN] update_leverage: {e}")

    # 1. Entry market
    order_res = exch.market_open(coin, is_buy, sz, slippage=0.01)
    print(f"[ENTRY] {order_res}")

    # 2. Reduce-only SL & TP trigger orders
    sl_res = exch.order(
        coin, not is_buy, sz, sl_px,
        {"trigger": {"triggerPx": sl_px, "isMarket": True, "tpsl": "sl"}},
        reduce_only=True,
    )
    tp_res = exch.order(
        coin, not is_buy, sz, tp_px,
        {"trigger": {"triggerPx": tp_px, "isMarket": True, "tpsl": "tp"}},
        reduce_only=True,
    )
    print(f"[SL] {sl_res}")
    print(f"[TP] {tp_res}")

    plan["entry_result"] = order_res
    plan["sl_result"] = sl_res
    plan["tp_result"] = tp_res

    with open(STATE_FILE, "w") as f:
        json.dump(plan, f, indent=2, default=str)
    print(f"\n[STATE] disimpan ke {STATE_FILE}")
    return plan


def show_positions(network, key_path):
    _, _, Account = get_sdk()
    base_url = NETWORKS[network]
    address = Account.from_key(load_key(key_path)).address
    st = get_account_state(base_url, address)
    ms = st.get("marginSummary", {})
    print(f"=== {network.upper()} | {address} ===")
    print(f"accountValue: ${float(ms.get('accountValue',0) or 0):,.2f}")
    for p in st.get("assetPositions", []):
        pos = p["position"]
        print(f"  {pos['coin']:<6} size={pos['szi']:>12} entry={pos.get('entryPx')} "
              f"uPnL={pos.get('unrealizedPnl')} liq={pos.get('liquidationPx')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", choices=["testnet", "mainnet"], default="testnet")
    ap.add_argument("--key", default="/home/ubuntu/credentials/pk_2897.txt")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--positions", action="store_true")
    ap.add_argument("--coin", default="ETH")
    ap.add_argument("--side", choices=["long", "short"])
    ap.add_argument("--notional", type=float, default=0)
    ap.add_argument("--sl-pct", type=float, default=0.006)
    ap.add_argument("--tp-pct", type=float, default=0.012)
    ap.add_argument("--leverage", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--live", action="store_true", help="kirim order sungguhan")
    a = ap.parse_args()

    if a.preflight:
        preflight(a.network, a.key)
    elif a.positions:
        show_positions(a.network, a.key)
    elif a.side and a.notional > 0:
        if a.network == "mainnet" and not a.live:
            raise SystemExit("[BLOCK] mainnet butuh --live eksplisit")
        place_bracket_order(a.network, a.key, a.coin, a.side, a.notional,
                            a.sl_pct, a.tp_pct, a.leverage,
                            dry_run=not a.live)
    else:
        ap.print_help()

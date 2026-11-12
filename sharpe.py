#!/usr/bin/env python3
"""
Sharpe / Sortino / Calmar calculation from real equity + trade data.
Multiple granularities: per-trade, daily, hourly.
"""
import json, os, math, statistics
from datetime import datetime, timezone, timedelta
from collections import defaultdict

WIB = timezone(timedelta(hours=7))
BASE = "/home/ubuntu/papertrade_backtest"
TRADE_LOG = os.path.join(BASE, "fut_trades.jsonl")
EQ_LOG = os.path.join(BASE, "equity_curve.jsonl")
INITIAL = 1000.0


def load_trades():
    if not os.path.exists(TRADE_LOG):
        return []
    out = []
    for line in open(TRADE_LOG):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            r["_dt"] = datetime.fromisoformat(r["t"]).astimezone(WIB)
            out.append(r)
        except Exception:
            pass
    return out


def load_equity():
    if not os.path.exists(EQ_LOG):
        return []
    out = []
    for line in open(EQ_LOG):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            r["_dt"] = datetime.fromisoformat(r["t"]).astimezone(WIB)
            out.append(r)
        except Exception:
            pass
    return out


def sharpe(returns, periods_per_year, rf=0.0):
    if len(returns) < 2:
        return None, None, None
    excess = [r - rf / periods_per_year for r in returns]
    mean = statistics.mean(excess)
    sd = statistics.stdev(excess)
    if sd == 0:
        return None, mean, 0.0
    sr = (mean / sd) * math.sqrt(periods_per_year)
    return sr, mean, sd


def sortino(returns, periods_per_year, rf=0.0):
    if len(returns) < 2:
        return None
    excess = [r - rf / periods_per_year for r in returns]
    mean = statistics.mean(excess)
    downside = [r for r in excess if r < 0]
    if not downside:
        return None
    dd = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
    if dd == 0:
        return None
    return (mean / dd) * math.sqrt(periods_per_year)


def max_dd(equity_series):
    peak = equity_series[0]
    mdd = 0.0
    for v in equity_series:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, (v - peak) / peak)
    return mdd


if __name__ == "__main__":
    trades = load_trades()
    eq = load_equity()

    print("=" * 84)
    print("RISK-ADJUSTED METRICS — HYPERLIQUID FUTURES BOOK")
    print("=" * 84)
    print()

    if not trades:
        print("No trades recorded.")
        raise SystemExit

    # ---- 1. Per-trade R multiples ----
    Rs = [t.get("R", 0) or 0 for t in trades]
    sr_trade, mean_R, sd_R = sharpe(Rs, periods_per_year=252 * 10)  # ~10 trades/day proxy
    so_trade = sortino(Rs, 252 * 10)

    # ---- 2. Per-trade % return on equity ----
    pct_returns = []
    for t in trades:
        eq_before = (t.get("equity", 0) or 0) - (t.get("usd", 0) or 0)
        if eq_before > 0:
            pct_returns.append((t.get("usd", 0) or 0) / eq_before)

    sr_pct, mean_pct, sd_pct = sharpe(pct_returns, 252 * 10)
    so_pct = sortino(pct_returns, 252 * 10)

    # ---- 3. Daily returns from equity log ----
    daily_eq = {}
    for e in eq:
        d = e["_dt"].strftime("%Y-%m-%d")
        daily_eq[d] = e["equity"]  # last value of day wins

    days = sorted(daily_eq)
    daily_ret = []
    prev = INITIAL
    for d in days:
        cur = daily_eq[d]
        if prev > 0:
            daily_ret.append((cur - prev) / prev)
        prev = cur

    sr_daily, mean_d, sd_d = sharpe(daily_ret, 365) if len(daily_ret) >= 2 else (None, None, None)
    so_daily = sortino(daily_ret, 365) if len(daily_ret) >= 2 else None

    # ---- 4. Max drawdown & Calmar ----
    equity_series = [INITIAL] + [e["equity"] for e in eq]
    mdd = max_dd(equity_series)
    total_return = (equity_series[-1] / INITIAL) - 1

    span_days = (trades[-1]["_dt"] - trades[0]["_dt"]).total_seconds() / 86400
    ann_return = ((1 + total_return) ** (365 / span_days) - 1) if span_days > 0 else 0
    calmar = (ann_return / abs(mdd)) if mdd != 0 else None

    # ---- Report ----
    print(f"Sample")
    print(f"  trades          : {len(trades)}")
    print(f"  period          : {trades[0]['_dt'].strftime('%d %b %Y %H:%M')} → {trades[-1]['_dt'].strftime('%d %b %Y %H:%M')} WIB")
    print(f"  span            : {span_days:.2f} days ({span_days*24:.1f} hours)")
    print(f"  trades / day    : {len(trades)/span_days:.1f}" if span_days > 0 else "")
    print()

    print(f"Return")
    print(f"  initial equity  : ${INITIAL:,.2f}")
    print(f"  current equity  : ${equity_series[-1]:,.2f}")
    print(f"  total return    : {total_return*100:+.2f}%")
    print(f"  max drawdown    : {mdd*100:.2f}%")
    print(f"  annualized      : {ann_return*100:+.1f}% (extrapolated)")
    print()

    def fmt(v, dec=2):
        return f"{v:.{dec}f}" if v is not None else "n/a"

    print(f"Sharpe Ratio")
    print(f"  per trade (R)   : {fmt(sr_trade)}   (mean {fmt(mean_R,3)}R, sd {fmt(sd_R,3)}R)")
    print(f"  per trade (%)   : {fmt(sr_pct)}   (mean {fmt(mean_pct*100,3)}%, sd {fmt(sd_pct*100,3)}%)")
    print(f"  daily           : {fmt(sr_daily)}   ({len(daily_ret)} daily samples)")
    print()

    print(f"Sortino Ratio (downside-only volatility)")
    print(f"  per trade (R)   : {fmt(so_trade)}")
    print(f"  per trade (%)   : {fmt(so_pct)}")
    print(f"  daily           : {fmt(so_daily)}")
    print()

    print(f"Calmar Ratio (annual return / max DD)")
    print(f"  calmar          : {fmt(calmar)}")
    print()

    # ---- Verdict ----
    print("=" * 84)
    print("INTERPRETATION")
    print("=" * 84)

    ref = sr_daily if sr_daily is not None else sr_pct

    if ref is None:
        verdict = "insufficient data"
    elif ref < 0:
        verdict = "NEGATIVE — system losing money on risk-adjusted basis"
    elif ref < 1.0:
        verdict = "BELOW INSTITUTIONAL THRESHOLD (typical bar: >1.0)"
    elif ref < 2.0:
        verdict = "ACCEPTABLE (institutional range 1.0-2.0)"
    elif ref < 3.0:
        verdict = "STRONG (rare, 2.0-3.0)"
    else:
        verdict = "EXCEPTIONAL — verify for look-ahead bias"

    print(f"\nVerdict: {verdict}")
    print()
    print("Caveats that matter:")
    print(f"  • Sample is {len(trades)} trades over {span_days:.1f} days — statistically thin.")
    print(f"  • Sharpe needs 100+ independent samples to stabilize.")
    print(f"  • Daily Sharpe uses only {len(daily_ret)} samples — unreliable.")
    print(f"  • Annualization of a {span_days:.1f}-day window is extrapolation, not evidence.")

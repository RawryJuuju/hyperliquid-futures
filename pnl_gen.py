#!/usr/bin/env python3
# Author: Juuju  |  X: @Juujutsu_  |  Telegram: @Juujutsuu
"""All-time performance report generator.

Reads the full trade ledger and renders a single-page performance report:
headline metrics, equity curve, monthly and weekday breakdown, strategy and
coin attribution, exit-type distribution, drawdown analysis, streaks, and a
rolling expectancy chart.

Every number is derived from fut_trades.jsonl. Nothing is estimated.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE = os.path.dirname(os.path.abspath(__file__))
TRADE_LOG = os.path.join(BASE, "fut_trades.jsonl")
OUT_PATH = os.path.join(BASE, "static", "pnl.html")
INITIAL_EQUITY = 1000.0


# ---------------------------------------------------------------- data

def load():
    rows = []
    with open(TRADE_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                r["_dt"] = datetime.fromisoformat(r["t"]).astimezone(WIB)
                rows.append(r)
            except Exception:
                pass
    rows.sort(key=lambda r: r["_dt"])
    return rows


def streaks(rows):
    """Longest win and loss streaks by sign of usd."""
    best_w = best_l = cur_w = cur_l = 0
    best_w_usd = best_l_usd = 0.0
    run_usd = 0.0
    sign = 0
    for r in rows:
        s = 1 if r["usd"] > 0 else -1
        if s == sign:
            run_usd += r["usd"]
        else:
            run_usd = r["usd"]
            sign = s
        if s > 0:
            cur_w += 1
            cur_l = 0
            if cur_w > best_w:
                best_w, best_w_usd = cur_w, run_usd
        else:
            cur_l += 1
            cur_w = 0
            if cur_l > best_l:
                best_l, best_l_usd = cur_l, run_usd
    return best_w, best_w_usd, best_l, best_l_usd


def max_drawdown(curve):
    peak = curve[0][1]
    mdd = 0.0
    mdd_start = mdd_end = curve[0][0]
    cur_peak_dt = curve[0][0]
    for dt, eq in curve:
        if eq > peak:
            peak = eq
            cur_peak_dt = dt
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        if dd > mdd:
            mdd = dd
            mdd_start = cur_peak_dt
            mdd_end = dt
    return mdd, mdd_start, mdd_end


def longest_dd(curve):
    """Longest stretch below a prior peak, in days."""
    peak = curve[0][1]
    peak_dt = curve[0][0]
    worst = timedelta(0)
    worst_from = worst_to = curve[0][0]
    for dt, eq in curve:
        if eq >= peak:
            if dt - peak_dt > worst:
                worst = dt - peak_dt
                worst_from, worst_to = peak_dt, dt
            peak = eq
            peak_dt = dt
    if curve[-1][0] - peak_dt > worst:
        worst = curve[-1][0] - peak_dt
        worst_from, worst_to = peak_dt, curve[-1][0]
    return worst, worst_from, worst_to


def bucket(rows, keyfn, label_map=None):
    out = defaultdict(lambda: {"n": 0, "w": 0, "usd": 0.0, "R": 0.0})
    for r in rows:
        k = keyfn(r)
        if label_map:
            k = label_map.get(k, k)
        b = out[k]
        b["n"] += 1
        b["usd"] += r["usd"]
        b["R"] += r["R"]
        if r["usd"] > 0:
            b["w"] += 1
    return out


# ---------------------------------------------------------------- charts

def area_chart(curve, w=1000, h=280):
    if len(curve) < 2:
        return ""
    vals = [c[1] for c in curve]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    rng = hi - lo

    def y(v):
        return h - ((v - lo) / rng * h)

    pts = []
    for i, v in enumerate(vals):
        pts.append(f"{i / (len(vals) - 1) * w:.1f},{y(v):.1f}")
    up = vals[-1] >= vals[0]
    color = "#5eead4" if up else "#f2707f"
    area = f"0,{h} " + " ".join(pts) + f" {w},{h}"
    base_y = y(INITIAL_EQUITY)
    return (
        f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.28"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<line x1="0" y1="{base_y:.1f}" x2="{w}" y2="{base_y:.1f}" '
        f'stroke="#2a3038" stroke-width="1" stroke-dasharray="4 4"/>'
        f'<polygon points="{area}" fill="url(#ag)"/>'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def bar_chart(items, w=1000, h=200):
    """items: list of (label, value). Diverging bars around zero."""
    if not items:
        return ""
    vals = [v for _, v in items]
    mx = max(abs(v) for v in vals) or 1
    n = len(items)
    gap = 6
    bw = (w - gap * (n - 1)) / n
    mid = h / 2
    parts = [f'<line x1="0" y1="{mid}" x2="{w}" y2="{mid}" stroke="#2a3038" stroke-width="1"/>']
    for i, (label, v) in enumerate(items):
        bh = abs(v) / mx * (h / 2 - 18)
        x = i * (bw + gap)
        y = mid - bh if v >= 0 else mid
        color = "#5eead4" if v >= 0 else "#f2707f"
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh,1):.1f}" '
            f'rx="2" fill="{color}" opacity="0.75"><title>{label}: {v:+.2f}</title></rect>'
        )
    return (f'<svg class="chart bar" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            + "".join(parts) + "</svg>")


def rolling_expectancy(rows, window=50, w=1000, h=170):
    if len(rows) < window + 1:
        return ""
    vals = []
    for i in range(window, len(rows) + 1):
        chunk = rows[i - window:i]
        vals.append(sum(r["R"] for r in chunk) / window)
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 0.1
    lo, hi = lo - pad, hi + pad
    rng = hi - lo

    def y(v):
        return h - ((v - lo) / rng * h)

    pts = [f"{i / (len(vals) - 1) * w:.1f},{y(v):.1f}" for i, v in enumerate(vals)]
    zero_y = y(0)
    color = "#5eead4" if vals[-1] >= 0 else "#f2707f"
    return (
        f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<line x1="0" y1="{zero_y:.1f}" x2="{w}" y2="{zero_y:.1f}" '
        f'stroke="#2a3038" stroke-width="1" stroke-dasharray="4 4"/>'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round"/></svg>'
    )


# ---------------------------------------------------------------- render

def money(v):
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


def pct(v):
    return f"{v:+.2f}%"


def cls(v):
    return "pos" if v >= 0 else "neg"


def render():
    rows = load()
    if not rows:
        return "<h1>No trades</h1>"

    n = len(rows)
    wins = [r for r in rows if r["usd"] > 0]
    losses = [r for r in rows if r["usd"] <= 0]
    gw = sum(r["usd"] for r in wins)
    gl = abs(sum(r["usd"] for r in losses))
    net = sum(r["usd"] for r in rows)
    final_eq = rows[-1]["equity"]
    ret = (final_eq / INITIAL_EQUITY - 1) * 100
    pf = gw / gl if gl else float("inf")
    wr = len(wins) / n * 100
    total_r = sum(r["R"] for r in rows)
    avg_win = gw / len(wins) if wins else 0
    avg_loss = -gl / len(losses) if losses else 0
    expectancy = total_r / n

    curve = [(r["_dt"], r["equity"]) for r in rows]
    mdd, mdd_from, mdd_to = max_drawdown(curve)
    dd_len, dd_from, dd_to = longest_dd(curve)
    bw, bw_usd, bl, bl_usd = streaks(rows)

    first_dt, last_dt = rows[0]["_dt"], rows[-1]["_dt"]
    days = (last_dt - first_dt).total_seconds() / 86400

    # --- buckets
    by_month = bucket(rows, lambda r: r["_dt"].strftime("%b %Y"))
    by_dow = bucket(rows, lambda r: r["_dt"].strftime("%a"))
    by_strat = bucket(rows, lambda r: r["strategy"])
    by_coin = bucket(rows, lambda r: r["coin"])
    by_kind = bucket(rows, lambda r: r["kind"])
    by_dir = bucket(rows, lambda r: r["dir"])

    month_order = sorted(by_month.items(), key=lambda kv: datetime.strptime(kv[0], "%b %Y"))
    dow_order = [(d, by_dow[d]) for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") if d in by_dow]
    strat_order = sorted(by_strat.items(), key=lambda kv: -kv[1]["usd"])
    coin_order = sorted(by_coin.items(), key=lambda kv: -kv[1]["usd"])
    kind_order = sorted(by_kind.items(), key=lambda kv: -kv[1]["usd"])

    def rows_html(items, key_label, total_usd):
        out = []
        for k, b in items:
            wr_b = b["w"] / b["n"] * 100 if b["n"] else 0
            share = b["usd"] / total_usd * 100 if total_usd else 0
            out.append(
                f'<tr><td class="k">{k}</td><td>{b["n"]}</td>'
                f'<td>{wr_b:.1f}%</td>'
                f'<td class="{cls(b["usd"])}">{money(b["usd"])}</td>'
                f'<td class="{cls(b["R"])}">{b["R"]:+.2f}R</td>'
                f'<td class="mut">{share:+.1f}%</td></tr>'
            )
        return (f'<table><thead><tr><th>{key_label}</th><th>Trades</th><th>Win</th>'
                f'<th>Net PnL</th><th>Total R</th><th>Share</th></tr></thead>'
                f'<tbody>{"".join(out)}</tbody></table>')

    hero = f"""
<div class="hero">
  <div class="eyebrow">All-time record · Hyperliquid L1</div>
  <h1>Every trade,<br>every <em>number.</em></h1>
  <p class="lede">Complete performance record across <strong>{n:,} closed positions</strong>
  and {len(by_coin)} instruments, from {first_dt:%d %b %Y} to {last_dt:%d %b %Y}.
  Measured from fills, net of fees.</p>

  <div class="headline">
    <div class="hl">
      <div class="hlv {cls(net)}">{money(net)}</div>
      <div class="hll">Net PnL</div>
    </div>
    <div class="hl">
      <div class="hlv {cls(ret)}">{pct(ret)}</div>
      <div class="hll">Total Return</div>
    </div>
    <div class="hl">
      <div class="hlv">{wr:.1f}%</div>
      <div class="hll">Win Rate</div>
    </div>
    <div class="hl">
      <div class="hlv">{pf:.2f}</div>
      <div class="hll">Profit Factor</div>
    </div>
  </div>
</div>

<section>
  <div class="sh"><span class="sn">01</span><h2>Equity <em>curve</em></h2></div>
  <div class="chartbox">
    <div class="charthead">
      <span>${INITIAL_EQUITY:,.0f} → ${final_eq:,.2f}</span>
      <span class="mut">{days:.1f} days · {n:,} trades</span>
    </div>
    {area_chart(curve)}
  </div>
</section>

<section>
  <div class="sh"><span class="sn">02</span><h2>Core <em>metrics</em></h2></div>
  <div class="grid">
    <div class="m"><div class="ml">Total R</div><div class="mv {cls(total_r)}">{total_r:+.2f}R</div></div>
    <div class="m"><div class="ml">Expectancy</div><div class="mv {cls(expectancy)}">{expectancy:+.4f}R</div></div>
    <div class="m"><div class="ml">Avg Win</div><div class="mv pos">{money(avg_win)}</div></div>
    <div class="m"><div class="ml">Avg Loss</div><div class="mv neg">{money(avg_loss)}</div></div>
    <div class="m"><div class="ml">Max Drawdown</div><div class="mv neg">-{mdd:.2f}%</div></div>
    <div class="m"><div class="ml">Longest Drawdown</div><div class="mv">{dd_len.days}d {dd_len.seconds // 3600}h</div></div>
    <div class="m"><div class="ml">Best Streak</div><div class="mv pos">{bw} <span class="sm">{money(bw_usd)}</span></div></div>
    <div class="m"><div class="ml">Worst Streak</div><div class="mv neg">{bl} <span class="sm">{money(bl_usd)}</span></div></div>
    <div class="m"><div class="ml">Winners</div><div class="mv">{len(wins):,}</div></div>
    <div class="m"><div class="ml">Losers</div><div class="mv">{len(losses):,}</div></div>
    <div class="m"><div class="ml">Gross Profit</div><div class="mv pos">{money(gw)}</div></div>
    <div class="m"><div class="ml">Gross Loss</div><div class="mv neg">{money(-gl)}</div></div>
  </div>
  <div class="note">Peak-to-trough drawdown ran {mdd_from:%d %b %H:%M} → {mdd_to:%d %b %H:%M} WIB.
  Longest stretch below a prior peak: {dd_len.days} days {dd_len.seconds // 3600} hours.</div>
</section>

<section>
  <div class="sh"><span class="sn">03</span><h2>Rolling <em>expectancy</em></h2></div>
  <p class="sub">Average R per trade over a rolling 50-trade window. Above the dashed line is an edge.</p>
  <div class="chartbox">{rolling_expectancy(rows)}</div>
</section>

<section>
  <div class="sh"><span class="sn">04</span><h2>By <em>month</em></h2></div>
  <div class="chartbox">{bar_chart([(k, b["usd"]) for k, b in month_order])}</div>
  <div class="labels">{"".join(f'<span>{k}</span>' for k, _ in month_order)}</div>
  {rows_html(month_order, "Month", net)}
</section>

<section>
  <div class="sh"><span class="sn">05</span><h2>By <em>strategy</em></h2></div>
  {rows_html(strat_order, "Strategy", net)}
</section>

<section>
  <div class="sh"><span class="sn">06</span><h2>By <em>instrument</em></h2></div>
  {rows_html(coin_order, "Instrument", net)}
</section>

<section>
  <div class="sh"><span class="sn">07</span><h2>Exits &amp; <em>direction</em></h2></div>
  <div class="two">
    <div>{rows_html(kind_order, "Exit type", net)}</div>
    <div>{rows_html(sorted(by_dir.items(), key=lambda kv: -kv[1]["usd"]), "Side", net)}</div>
  </div>
</section>

<section>
  <div class="sh"><span class="sn">08</span><h2>By <em>weekday</em></h2></div>
  <div class="chartbox">{bar_chart([(k, b["usd"]) for k, b in dow_order])}</div>
  <div class="labels">{"".join(f'<span>{k}</span>' for k, _ in dow_order)}</div>
</section>
"""

    nav = """
<nav><div class="nav-in">
  <div class="logo"><div class="pulse"></div>QUANT FUTURES</div>
  <div class="navlinks">
    <a href="/terminal">Terminal</a>
    <a href="/calendar">PnL Calendar</a>
    <a href="/versions">Versions</a>
    <a href="/pnl" class="on">Performance</a>
    <a href="/">About</a>
    <a href="/terminal" class="nav-cta">Terminal →</a>
  </div>
</div></nav>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Performance — Systematic Futures Trader</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/hl-favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/static/hl-favicon-16x16.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{
 --bg:#08090b; --bg2:#0d0f12; --panel:#111418; --line:#1d2228;
 --txt:#f2f4f7; --txt2:#8b939f; --txt3:#5a626d;
 --acc:#5eead4; --acc2:#38bdf8; --red:#f2707f;
 --mono:'JetBrains Mono',monospace; --ui:'Inter',sans-serif; --serif:'Instrument Serif',serif;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--txt);font-family:var(--ui);-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 28px}}

nav{{position:fixed;top:0;left:0;right:0;z-index:50;backdrop-filter:blur(20px);
 background:rgba(8,9,11,.72);border-bottom:1px solid var(--line)}}
.nav-in{{max-width:1080px;margin:0 auto;padding:16px 28px;display:flex;align-items:center;justify-content:space-between}}
.logo{{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:13px;font-weight:600}}
.pulse{{width:7px;height:7px;border-radius:50%;background:var(--acc);box-shadow:0 0 10px var(--acc);animation:p 2s infinite}}
@keyframes p{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.4;transform:scale(.85)}}}}
.navlinks{{display:flex;gap:24px;font-size:12.5px;color:var(--txt2);align-items:center}}
.navlinks a{{color:inherit;text-decoration:none;transition:.2s}}
.navlinks a:hover{{color:var(--acc)}}
.navlinks a.on{{color:var(--acc)}}
.nav-cta{{border:1px solid rgba(94,234,212,.35);border-radius:6px;padding:6px 13px;
 color:var(--acc) !important;font-family:var(--mono);font-size:11px;font-weight:600}}

.hero{{padding:160px 0 70px}}
.eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;
 color:var(--acc);margin-bottom:24px;display:flex;align-items:center;gap:10px}}
.eyebrow::before{{content:'';width:28px;height:1px;background:var(--acc)}}
h1{{font-family:var(--serif);font-size:clamp(44px,6.5vw,76px);line-height:1.03;font-weight:400;letter-spacing:-.025em;margin-bottom:26px}}
h1 em{{font-style:italic;color:var(--acc)}}
.lede{{font-size:16px;line-height:1.75;color:var(--txt2);max-width:620px;font-weight:300}}
.lede strong{{color:var(--txt);font-weight:500}}

.headline{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);
 border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-top:56px}}
.hl{{background:var(--bg2);padding:28px 22px}}
.hlv{{font-family:var(--mono);font-size:30px;font-weight:600;letter-spacing:-.03em}}
.hll{{font-size:10.5px;color:var(--txt3);text-transform:uppercase;letter-spacing:.1em;margin-top:8px}}

section{{padding:70px 0;border-top:1px solid var(--line)}}
.sh{{display:flex;align-items:baseline;gap:16px;margin-bottom:32px}}
.sn{{font-family:var(--mono);font-size:11px;color:var(--txt3)}}
h2{{font-family:var(--serif);font-size:clamp(28px,4vw,40px);font-weight:400;letter-spacing:-.02em}}
h2 em{{font-style:italic;color:var(--acc2)}}
.sub{{font-size:13.5px;color:var(--txt2);margin-bottom:20px;line-height:1.6}}

.chartbox{{background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:20px}}
.charthead{{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11.5px;
 color:var(--txt2);margin-bottom:14px}}
.chart{{width:100%;height:auto;display:block}}
.chart.bar{{height:180px}}

.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);
 border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.m{{background:var(--bg2);padding:20px}}
.ml{{font-size:10px;color:var(--txt3);text-transform:uppercase;letter-spacing:.09em}}
.mv{{font-family:var(--mono);font-size:18px;font-weight:600;margin-top:7px;letter-spacing:-.02em}}
.mv .sm{{font-size:11px;color:var(--txt3);font-weight:400}}

.note{{font-size:12px;color:var(--txt3);margin-top:16px;line-height:1.6;font-family:var(--mono)}}

table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:18px}}
thead th{{text-align:right;font-size:10px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--txt3);padding:10px 12px;border-bottom:1px solid var(--line);font-weight:500}}
thead th:first-child{{text-align:left}}
tbody td{{padding:11px 12px;border-bottom:1px solid rgba(29,34,40,.55);text-align:right;
 font-family:var(--mono);font-size:12px}}
tbody td:first-child{{text-align:left;color:var(--txt);font-family:var(--ui);font-size:12.5px}}
tbody tr:hover td{{background:rgba(94,234,212,.03)}}
td.k{{font-weight:500}}
td.mut{{color:var(--txt3)}}

.pos{{color:var(--acc)}}
.neg{{color:var(--red)}}

.labels{{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10.5px;
 color:var(--txt3);margin-top:10px;padding:0 4px}}

.two{{display:grid;grid-template-columns:1fr 1fr;gap:26px}}

footer{{border-top:1px solid var(--line);padding:34px 0;text-align:center;font-size:11.5px;
 color:var(--txt3);font-family:var(--mono)}}
.disclaimer{{margin-top:10px;font-size:10.5px;line-height:1.6;color:#40474f}}

@media(max-width:820px){{
 .headline,.grid{{grid-template-columns:repeat(2,1fr)}}
 .two{{grid-template-columns:1fr}}
 .navlinks{{display:none}}
}}
</style>
</head>
<body>
{nav}
<div class="wrap">
{hero}
</div>
<footer>
  QUANT FUTURES — PERFORMANCE RECORD
  <div class="disclaimer">
    All figures measured from closed positions and net of exchange fees. Times in WIB (UTC+7).
    Past performance is not indicative of future results.
  </div>
</footer>
</body>
</html>"""
    return html


if __name__ == "__main__":
    html = render()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(html)
    print(f"written {OUT_PATH} ({len(html)} bytes)")

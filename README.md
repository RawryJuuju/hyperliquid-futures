# Hyperliquid Systematic Futures Trading Engine

<!-- Author: Juuju  |  X: @Juujutsu_  |  Telegram: @Juujutsuu -->

<div align="center">

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-38bdf8.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Hyperliquid L1](https://img.shields.io/badge/exchange-Hyperliquid%20L1-5eead4.svg?style=flat-square)](https://hyperliquid.xyz)
[![FastAPI](https://img.shields.io/badge/framework-FastAPI-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-e8b923.svg?style=flat-square)](LICENSE)
[![Status: Production](https://img.shields.io/badge/status-production%20active-22c55e.svg?style=flat-square)](https://rawry.cyou/versions)

**High-performance, systematic quantitative execution engine and real-time monitoring infrastructure for Hyperliquid L1 perpetuals.**

[Live Terminal](https://rawry.cyou/) • [Release Versions](https://rawry.cyou/versions) • [PnL Calendar](https://rawry.cyou/calendar)

</div>

---

## 🏛️ Executive Summary

This repository hosts an autonomous, quantitative trading system operating 24/7 on Hyperliquid Layer-1 perpetual contracts. Built with institutional risk boundaries, it pairs systematic trend expansion with intraday Smart Money Concepts (SMC/ICT), executing bracket orders directly against on-chain liquidity.

### Core Capabilities
- **Multi-Engine Execution**: SMC Silver Bullet (5m Fair Value Gaps, Liquidity Sweeps), Multi-Timeframe Breakout (15m/1h), and Funding Rate Arbitrage (1h delta-neutral on majors).
- **Session-Aware Risk Gating (v1.7)**: WIB-hour based risk multipliers per strategy family — Night (22-04) disables directional, only Funding Arb; Asia (04-08) Breakout full/SMC half; EU (08-14) ALL full; US (14-22) Swing 1h 1.2x, Breakout 15m 0.5x, SMC 0.7x.
- **Post-Only Limit Order Execution (v1.6)**: Guaranteed maker rebates (0.002% vs 0.02% taker) with automatic fallback to market orders after 2 bars.
- **Volatility-Targeted Position Sizing (v1.6)**: Dynamic risk scaling inversely to realized ATR volatility targeting 2% daily portfolio vol.
- **Dynamic Scale-Out**: Automated 33% partial profit locking at +1.0R with positive fee-buffered Breakeven trailing (+0.15R) to protect floating returns.
- **Institutional Risk Safeguards**: Aggregate open risk caps, margin exhaustion throttles, drawdown dampeners, and correlation-cluster concurrency limits.
- **Full Operational Web Stack**: Ultra-low-latency FastAPI web terminal with TradingView charts, WIB-normalized PnL calendar, and an immutable cryptographic version release registry.

---

## 📐 System Architecture

```text
                              ┌──────────────────────────────────────────────┐
                              │             Hyperliquid L1 Node              │
                              │          (Perpetuals Matching Engine)        │
                              └──────────────────────┬───────────────────────┘
                                                     │ WebSocket / REST Info
                                                     ▼
┌────────────────────────┐         ┌──────────────────────────────────────────┐
│   FastAPI Web Terminal │ <────── │          Execution Daemon                │
│   • TradingView Charts │  State  │           (futures_bot.py)               │
│   • Position Controls  │  Sync   ├──────────────────────────────────────────┤
│   • Real-Time Metrics  │         │ • Engine: SMC Silver Bullet (5m)         │
└────────────────────────┘         │ • Engine: Multi-TF Breakout (15m/1h)     │
                                   │ • Money Management & Correlation Cluster │
┌────────────────────────┐         │ • Dynamic Scale-Out & Trailing BE Engine │
│  Automated Reporting   │         └──────────────────┬───────────────────────┘
│  • PnL Calendar (/cal) │ <──────────────────────────┘ State Log (JSONL)
│  • Versions (/versions)│
└────────────────────────┘
```

---

## 🪙 Asset Universe & Correlation Clusters (v1.7)

The book currently trades **13 assets** across **33 active strategy slots**, partitioned into **6 independent correlation clusters**. 10 assets operate **3 synchronized time horizons simultaneously** (Scalp 5m, Intraday 15m, Swing 1h). 3 major assets (BTC, ETH, SOL) run **Funding Rate Arbitrage only** (1h delta-neutral perp positions).

| Cluster | Category | Assets | Active Strategy Stacks |
|---|---|---|---|
| **Cluster A** | Ecosystem Hyperliquid | `ENA` | 5m SMC Scalp + 15m Intraday Breakout + 1h Swing Breakout |
| **Cluster B** | Alt Momentum | `WLD`, `NEAR` | 5m SMC Scalp + 15m Intraday Breakout + 1h Swing Breakout |
| **Cluster C** | Layer 2 & High-Beta DeFi | `INJ`, `ZEC`, `ARB` | 5m SMC Scalp + 15m Intraday Breakout + 1h Swing Breakout |
| **Cluster D** | Alternate L1 / AI Narrative | `AVAX`, `TAO`, `SUI` | 5m SMC Scalp + 15m Intraday Breakout + 1h Swing Breakout |
| **Cluster E** | Macro Commodities & Metals | `PAXG` (Paxos Gold) | 5m SMC Scalp + 15m Intraday Breakout + 1h Swing Breakout |
| **Cluster F** | **Majors - Funding Arb Only** | `BTC`, `ETH`, `SOL` | **1h Funding Rate Arbitrage (Delta-Neutral)** |

---

## 🛡️ Risk Management Parameters (v1.7 Release)

```yaml
Base Risk per Trade: 0.45% of total equity (Vol-Adjusted: 0.5x-2.0x scaling, Session-Adjusted: 0.0x-1.2x)
Aggregate Open Risk Ceiling: 6.00%
Maximum Concurrent Positions: 20
Maximum Margin Utilization: 75% of equity
Correlation Cluster Max: 3 concurrent positions per cluster
Risk-to-Reward Model: Calibrated 1:2.0 target (SMC Scalp) / 1:2.5 target (Breakout)
Multi-Horizon Stacking: Scalp (5m), Intraday (15m), Swing (1h) concurrent entries enabled
Anti-Hedging Guard: Prohibits opposite-direction positions on the same asset
Variable Leverage by Horizon: Scalp 15x | Intraday 10x | Swing 5x (INJ capped 5x)
Regime Detection: EMA20/50 alignment on 1h + 15m (BULL/BEAR/CHOP)
Dynamic Partial Take Profit: 33% closed at +1.0R (Realized Cashflow Lock)
Runner Position: 67% retained to run for full +2.0R / +2.5R expansion
Breakeven Trailing: Shift SL to Entry + 0.15R positive fee buffer at +1.2R MFE
Autonomous Loss Cooldown: 45 minutes timeout per coin following a stopout
Limit Order Engine: FVG/Sweep zone entries (0.15-0.25R improvement over market)
Post-Only Limit Orders: True (Maker rebate 0.002% vs Taker 0.02% = 10x fee savings)
Volatility Targeting: 2% daily portfolio vol via ATR(14), capped 0.5x-2.0x risk scale
Funding Rate Arbitrage: Delta-neutral perp on BTC/ETH/SOL @ |funding| > 0.01%/8h (13.7% APR)
Session-Aware Gating (v1.7): WIB-hour multipliers — Night dir=0/fund=1, Asia smc=0.5/brk=1, EU all=1, US smc=0.7/brk15=0.5/brk1h=1.2/fund=1
```

---

## 📂 Repository Directory Layout

```text
.
├── futures_bot.py              # 24/7 autonomous trading loop daemon (v1.7 session gating)
├── futures_dashboard.py        # Real-time FastAPI terminal & API gateway
├── strategy_config.json        # Production configuration, asset parameters & risk rules
├── versions.json               # Immutable release catalog and trade performance ledgers
├── fut_state.json              # Runtime state (positions, equity, cooldowns)
├── scripts/                    # Research & backtest scripts (gitignored)
│   ├── backtest_smc.py
│   ├── check_meta.py
│   ├── dashboard.py
│   ├── engine.py
│   ├── hl_live_bot.py
│   ├── hl_trader.py
│   ├── research.py
│   ├── research2.py
│   ├── research3.py
│   ├── research4.py
│   ├── research5.py
│   ├── research6.py
│   ├── research_breakout.py
│   ├── research_cand.py
│   ├── research_final.py
│   ├── research_grid.py
│   ├── research_multi.py
│   ├── scan_top30.py
│   ├── scan_volume.py
│   ├── stratlib.py
│   ├── stratlib2.py
│   ├── smc_lib.py
│   ├── candidate_coins.json
│   └── versions_gen.py
├── static/                     # Static production assets
│   ├── about.html              # System philosophy and methodology page
│   ├── calendar.html           # Rendered daily PnL performance calendar
│   ├── versions.html           # Rendered version release history
│   ├── hl-apple-touch-icon.png
│   ├── hl-favicon-16x16.png
│   ├── hl-favicon-32x32.png
│   └── lightweight-charts.js   # TradingView lightweight-charts library
├── .control_pin                # Dashboard access PIN (chmod 600, gitignored)
├── .control_pin.example        # Template for PIN setup
├── futures-bot.service         # systemd service for trading daemon
└── futures-dashboard.service   # systemd service for web terminal
```

---

## ⚡ Quick Start

### 1. Prerequisites
- Linux / macOS environment
- Python 3.12+
- `uv` or standard Python `venv`

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/RawryJuuju/hyperliquid-futures.git
cd hyperliquid-futures

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required dependencies
pip install fastapi uvicorn requests eth-account
```

### 3. Dashboard PIN Configuration
Create an access PIN for the dashboard control panel:
```bash
echo "YOUR_PIN_HERE" > .control_pin
chmod 600 .control_pin
```

### 4. Running the System
```bash
# Launch the trading daemon
python futures_bot.py

# In a separate process, start the web terminal
python futures_dashboard.py
```
Access the local monitoring dashboard at `http://localhost:8899`.

---

## 🔒 Security Architecture

- **Zero Credential Exposure**: Private keys and notification tokens are never committed to version control. They are resolved at runtime via external credential directories with strict POSIX permissions (`chmod 600`).
- **PIN Protected Controls**: All manual overrides (emergency close, parameter modifications) require cryptographic verification.
- **Production Data Stripping**: All public API endpoints strip proprietary infrastructure comments, internal backtest paths, and private host metadata.
- **State & Logs Gitignored**: Runtime state (`fut_state.json`, `equity_curve.jsonl`, `fut_trades.jsonl`) and logs are excluded from version control.

---

## 📜 Release Cadence

- **`v1.7` (Current Active)**: Session-Aware Risk Gating — WIB-hour risk multipliers per strategy family. Night (22-04) directional OFF/funding ON; Asia (04-08) breakout 1.0x/SMC 0.5x; EU (08-14) ALL 1.0x (golden window); US (14-22) SMC 0.7x/Breakout 15m 0.5x/Swing 1h 1.2x. Eliminates -$152 night bleed. Zero new strategies, pure risk gating overlay.
- **`v1.6` (Superseded)**: Post-Only Limit Orders (maker rebate 0.002%), Volatility-Targeted Sizing (2% daily vol), Funding Rate Arbitrage on BTC/ETH/SOL (delta-neutral, 13.7% APR), Universe expansion to 13 assets (Cluster F), 33 strategy slots.
- **`v1.5` (Superseded)**: Regime Detection (BULL/BEAR/CHOP via EMA alignment), Limit Order Engine (FVG/Sweep/Breakout levels with 0.15-0.25R improvement), Variable Leverage per Horizon (Scalp 15x, Intraday 10x, Swing 5x), full multi-horizon stacking across 10 assets.
- **`v1.4` (Superseded)**: Symmetric Multi-Horizon Stacking (Scalp 5m, Intraday 15m, Swing 1h) across all 10 assets, strict dollar risk normalization (0.45% flat), anti-hedging directional guard, and calibrated 1:2.5R breakout targets.
- **`v1.3` (Superseded)**: Delisted toxic chop assets (`HYPE`, `PUMP`), upgraded scale-out ratio to 33% @ 1.0R (67% runner), deployed 45m loss cooldown, and normalized 10-asset universe.
- **`v1.2` (Superseded)**: Dynamic Scale-Out (50% partial at 1.0R), calibrated RR 1:2.0, positive fee-buffered Breakeven trailing, and strict 1h short filtering.
- **`v1.1` (Superseded)**: SMC/ICT Silver Bullet integration, Killzone time filtering, and universe expansion to 12 assets (including Gold PAXG).
- **`v1.0` (Archived)**: Multi-timeframe breakout baseline (157 closed trades, documented in `/versions`).

For detailed changelogs and audit metrics, visit the [Version Registry](https://rawry.cyou/versions).

---

## ⚖️ License

Distributed under the [MIT License](LICENSE).

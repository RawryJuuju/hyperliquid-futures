# Hyperliquid Systematic Futures Trading Engine

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
- **Dual-Engine Execution**: Multi-timeframe Breakout (5m / 15m / 1h) combined with SMC Silver Bullet (Fair Value Gaps, Liquidity Sweeps, and Displacement filters).
- **Dynamic Scale-Out**: Automated 50% partial profit locking at +1.0R with positive fee-buffered Breakeven trailing (+0.15R) to protect floating returns.
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

## 🪙 Asset Universe & Correlation Clusters

The book currently trades **10 high-conviction alpha assets** across **30 active strategy slots**, partitioned into 5 independent correlation clusters to eliminate portfolio contagion:

| Cluster | Category | Assets | Active Strategies |
|---|---|---|---|
| **Cluster A** | Ecosystem Hyperliquid | `ENA` | SMC Silver Bullet 5m + Breakout 5m/15m/1h |
| **Cluster B** | Alt Momentum | `WLD`, `NEAR` | SMC Silver Bullet 5m + Breakout 5m/15m/1h |
| **Cluster C** | Layer 2 & High-Beta DeFi | `INJ`, `ZEC`, `ARB` | SMC Silver Bullet 5m + Breakout 5m/15m/1h |
| **Cluster D** | Alternate L1 / AI Narrative | `AVAX`, `TAO`, `SUI` | SMC Silver Bullet 5m + Breakout 15m |
| **Cluster E** | Macro Commodities & Metals | `PAXG` (Paxos Gold) | SMC Silver Bullet 5m + Breakout 15m |

---

## 🛡️ Risk Management Parameters (v1.3 Release)

```yaml
Base Risk per Trade: 0.45% of total equity
Aggregate Open Risk Ceiling: 6.00%
Maximum Concurrent Positions: 20
Maximum Margin Utilization: 75% of equity
Correlation Cluster Max: 3 concurrent positions per cluster
Risk-to-Reward Model: Calibrated 1:2.0 target (SMC Scalp)
Dynamic Partial Take Profit: 33% closed at +1.0R (Realized Cashflow Lock)
Runner Position: 67% retained to run for full +2.0R expansion
Breakeven Trailing: Shift SL to Entry + 0.15R positive fee buffer at +1.2R MFE
Autonomous Loss Cooldown: 45 minutes timeout per coin following a stopout
Multi-Timeframe Trend Gating: Strictly no short positions against 1h bullish EMA drift
```

---

## 📂 Repository Directory Layout

```text
.
├── futures_bot.py              # 24/7 autonomous trading loop daemon
├── smc_lib.py                  # SMC/ICT quantitative indicators (FVG, Sweeps, Killzones)
├── futures_dashboard.py        # Real-time FastAPI terminal & API gateway
├── calendar_gen.py             # WIB-based daily PnL calendar generator
├── versions_gen.py             # Version release & performance report builder
├── versions_style.py           # Editorial dark-mode aesthetic styling
├── versions.json               # Immutable release catalog and trade performance ledgers
├── strategy_config.json        # Production configuration, asset parameters & risk rules
├── engine.py                   # Vectorized backtesting simulator & candle ingestion
├── stratlib.py                 # Technical indicator mathematics library
├── check_state.py              # CLI state viewer for active books and margins
├── close_all.py                # Emergency position flattener
├── sharpe.py                   # Historical Sharpe, Sortino, and Calmar metrics calculator
├── static/                     # Static production assets
│   ├── about.html              # System philosophy and methodology page
│   ├── calendar.html           # Rendered daily PnL performance calendar
│   └── versions.html           # Rendered version release history
├── archive/                    # Deprecated research prototypes
└── tests & research/           # Walk-forward analysis and parameter robustness tests
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

---

## 📜 Release Cadence

- **`v1.3` (Current Active)**: Delisted toxic chop assets (`HYPE`, `PUMP`), upgraded scale-out ratio to 33% @ 1.0R (67% runner), deployed 45m loss cooldown, and normalized 10-asset universe.
- **`v1.2` (Superseded)**: Dynamic Scale-Out (50% partial at 1.0R), calibrated RR 1:2.0, positive fee-buffered Breakeven trailing, and strict 1h short filtering.
- **`v1.1` (Superseded)**: SMC/ICT Silver Bullet integration, Killzone time filtering, and universe expansion to 12 assets (including Gold PAXG).
- **`v1.0` (Archived)**: Multi-timeframe breakout baseline (157 closed trades, documented in `/versions`).

For detailed changelogs and audit metrics, visit the [Version Registry](https://rawry.cyou/versions).

---

## ⚖️ License

Distributed under the [MIT License](LICENSE).

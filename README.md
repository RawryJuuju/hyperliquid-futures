# Hyperliquid Futures Trading System

> Quantitative futures trading engine, backtesting suite, and real-time monitoring terminal built for Hyperliquid L1 perpetuals.

---

## 🏛️ System Overview

This repository contains the end-to-end systematic trading infrastructure developed for Hyperliquid perpetual contracts:

1. **Trading Engine (`futures_bot.py`)**: 24/7 autonomous execution engine running multi-timeframe breakout strategies across liquid perps with strict risk gating.
2. **Real-time Terminal (`futures_dashboard.py`)**: Web-based monitoring terminal powered by FastAPI, TradingView Lightweight Charts, real-time exposure calculations, and system controls.
3. **PnL Calendar (`calendar_gen.py`)**: Calendar dashboard tracking net daily performance, win rates, and trade counts in Western Indonesia Time (WIB, UTC+7).
4. **Version Registry (`versions_gen.py`, `versions_style.py`, `versions.json`)**: Immutable release tracking system logging all system versions, performance metrics, configuration snapshots, and full trade ledgers.
5. **Research & Backtest Suite (`engine.py`, `stratlib.py`, `research*.py`)**: Walk-forward optimization (in-sample / out-of-sample), parameter sensitivity analysis, correlation clustering, and leverage modeling.
6. **Archive (`archive/`)**: Historical prototypes including early paper-trade watchers, orderbook scalpers, and execution tools.

---

## ⚙️ Strategy Architecture (v1.0 Baseline)

- **Execution Model**: Multi-timeframe volatility breakout with ATR-based volatility-adaptive stops.
- **Universe (7 Coins)**: `WLD`, `INJ`, `ZEC`, `NEAR`, `HYPE`, `ENA`, `PUMP`.
- **Horizons & Targets**:
  - `5m`: Fast expansion layer (RR 1:5.0)
  - `15m`: Core workhorse layer (RR 1:4.0)
  - `1h`: Structural high-conviction layer (RR 1:4.0)
  - Total: 21 concurrent strategy slots
- **Risk Budget**:
  - Base risk per trade: `0.25%` of equity
  - Aggregate open risk ceiling: `2.25%`
  - Max concurrent positions: `15`
  - Correlation cluster cap: Maximum `2` concurrent positions per asset cluster
  - Leverage: Uniform `10x` isolated/cross buffer

---

## 📁 Repository Structure

```text
.
├── futures_bot.py              # Main autonomous trading daemon
├── futures_dashboard.py        # FastAPI dashboard server & API gateway
├── calendar_gen.py             # WIB-based daily PnL calendar generator
├── versions_gen.py             # Version release & performance report builder
├── versions_style.py           # Editorial stylesheet matching /about
├── versions.json               # Canonical version registry ledger
├── strategy_config.json        # Active configuration, risk model & clusters
├── engine.py                   # Backtest simulation & vector engine
├── stratlib.py                 # Core technical indicator & signal library
├── check_state.py              # CLI utility to inspect current bot state
├── close_all.py                # Emergency market flattener script
├── sharpe.py                   # Risk-adjusted return & Sharpe/Sortino calculator
├── DEEP_ANALYSIS.md            # Forensic research and walk-forward findings
├── static/                     # Web assets (charts, favicons, static HTML)
│   ├── about.html              # System methodology and trader profile
│   ├── calendar.html           # Generated calendar report
│   └── versions.html           # Generated version release registry
├── archive/                    # Deprecated prototypes & early research
└── tests & research scripts    # test_*.py, research_*.py, study_leverage.py
```

---

## 🚀 Running the Services

### Prerequisites
- Python 3.12+ (isolated virtual environment recommended via `uv` or `venv`)
- Systemd for continuous background supervision

### Installation
```bash
# Set up virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install fastapi uvicorn hyperliquid-python-sdk eth-account requests
```

### Dashboard Authentication
```bash
# Create control PIN file
echo "YOUR_PIN_HERE" > .control_pin
chmod 600 .control_pin
```

### Systemd Services
Unit files are included in the repo:
- `futures-bot.service`: Manages the automated trading loop
- `futures-dashboard.service`: Manages the web dashboard on port `8899`

```bash
sudo cp futures-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now futures-dashboard
```

---

## 🔒 Security & OPSEC

- Credentials (Telegram bot token, private keys) are never committed to this repository. They are resolved via external local credential paths (`chmod 600`).
- The dashboard control endpoint `/api/control` is protected by cryptographic PIN verification.
- All public-facing API endpoints strip internal backtest notes, rationales, and infrastructure paths.

---

## 📜 Version History

- **v1.0 (Baseline Breakout)**: Archived 23 Oct 2026. 157 closed trades, -9.06% net return, 0.78 profit factor. Documented as the reference baseline in `/versions`.

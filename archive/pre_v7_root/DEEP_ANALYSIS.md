# SYSTEMATIC TRADING: WHY LIVE ≠ BACKTEST
## Deep Analysis for the HL Futures System

---

## PART 1: TAXONOMY OF SYSTEMATIC FAILURE

### 1.1 Overfitting (Curve Fitting)
**Definition:** parameters tuned on historical data until they look "perfect" on that data,
but carries no predictive power on new data.

**Gejala:**
- Backtest PF > 2.0 (too good)
- Small sample (< 50 trades)
- very specific parameters (look=7, atr=1.37, body=0.43)
- Performance collapses out of sample

**that kita alami:**
- sweep_fade backtest PF 1.6-2.4 → live PF 0.25
- **Diagnosis: overfit.** 14 trade live, WR 7.1% vs backtest 40%

**Mitigasi:**
- Walk-forward (already)
- parameters must be "round" (look 10/20, not 7)
- Minimum 100 trade per konfigurasi
- Sensitivity test: shift parameters ±20%, PF must stay > 1.0

---

### 1.2 Look-Ahead Bias
**Definition:** using information that was not yet available when the decision was made.

**Bentuk umum:**
- entry at the signal candle close (we only know the close AFTER it closes)
- using high/low candle that sama for check SL/TP
- Indikator dihitung with data future

**that kita alami:**
- Backtest entry di `cur["c"]` = close candle signal
- Reality: the bot detects only AFTER the close, sends the order, fills at the next open
- **This bias has not been measured until now**

**Mitigasi:**
- entry at `next_open`, not `close`
- SL/TP check mulai bar SETELAH entry
- Shift every indicator by 1 bar

---

### 1.3 Survivorship Bias
**Definition:** only analysing assets that still exist, ignoring those already delisted.

**that kita alami:**
- We picked 11 coins from today's top-volume list
- Coins that were top before but are dead now never entered the sample
- **Moderate bias** — crypto delistings are rarer than equity delistings

---

### 1.4 Transaction Cost Underestimation
**Definition:** a backtest using fees lower than reality.

**that kita using:**
- Fee 0.04% × 2 = 0.08% round-trip
- **Realita Hyperliquid:** taker 0.045%, maker 0.015%
- if entry market: 0.045% + exit 0.045% = **0.09%**
- **Underestimate 12.5%**

**Impact:** at a 0.3% SL, a 0.09% fee is 30% of risk (not 26.7%)

**Mitigasi:**
- uses a 0.05% per-side fee (conservative)
- Tambah slippage 0.02-0.05%

---

### 1.5 Slippage & Market Impact
**Definition:** the fill price differs from the expected price.

**Faktor:**
- Spread bid-ask
- Kedalaman orderbook
- Volatility at order entry
- Order size relative to available liquidity

**Hyperliquid spesifik:**
- Spread BTC/ETH: 1-2 bps
- Spread altcoin: 5-15 bps
- Order $500 di altcoin = can slippage 10+ bps

**that kita alami:**
- entry market di close candle → slippage not dimodelkan
- Notional $300-1000 per trade → slippage signifikan di altcoin

---

### 1.6 Regime Change
**Definition:** market conditions changed between the backtest period and live.

**Example:**
- Backtest: trending kuat (bull run)
- Live: choppy/ranging
- trend-following strategies collapse

**that kita alami:**
- The 120d backtest includes a trending period
- Live 17 hours: a ranging market -> breakout failed repeatedly

**Mitigasi:**
- Regime filter (already dicoba, slope 1.5 ATR membantu)
- Adaptive position sizing berdasarkan ATR percentile
- Reduce exposure saat ADX low... **but test kita bilang ADX filter merusak**

---

### 1.7 Execution Latency
**Definition:** the delay between signal and execution.

**that kita alami:**
- Scan interval 20 detik
- Candle 5m = 300 detik
- Latency maksimal 20 detik = 6.7% from candle
- **Bias moderat**

**Mitigasi:**
- WebSocket for real-time price
- Pre-compute indikator
- Kurangi scan interval

---

### 1.8 data Quality
**Definition:** backtest data differs from live data.

**that kita alami:**
- Backtest: candle from API historis
- Live: candle from API that sama
- **Bias minimal** ✅

---

## PART 2: COMPONENT IMPORTANCE HIERARCHY

Berdasarkan literatur & pengalaman, urutan kontribusi terhadap profit:

| Rank | Komponen | Kontribusi | Status kita |
|---|---|---|---|
| 1 | **Position Sizing** | 40% | ✅ Fixed-fractional 0.25% |
| 2 | **Risk Management** | 25% | ✅ ATR SL, max 6 position |
| 3 | **exit Strategy** | 15% | ⚠️ TP fixed R, not yet trailing |
| 4 | **entry Timing** | 12% | ⚠️ Breakout, ada look-ahead |
| 5 | **Asset Selection** | 8% | ✅ 7 coin filtered |

**Insight:** Kita fokus 90% waktu di entry (rank 4), padahal kontribusinya cuma 12%.

---

## PART 3: WHAT WE HAVE NOT DONE YET

### 3.1 Trailing Stop (not BE)
**BE lock failed** because it cut winners too early.
**Trailing stop** is different: it follows price instead of staying fixed at entry.

**Example:**
- entry $100, SL $97 (risk $3)
- price rises to $106 (+2R)
- Trailing: SL rises to $103 (locks +1R)
- price rises to $112 (+4R)
- Trailing: SL rises to $109 (locks +3R)

**Bedanya with BE:** BE kunci di $100 (0R). Trailing kunci di +1R, +3R, dst.

**not yet dites.** Ini prioritas berikutnya.

---

### 3.2 Pyramiding (Add to Winner)
**Concept:** if a position is profitable, add size.
**Risk:** it can turn a profit into a loss if price reverses.

**not yet dites.**

---

### 3.3 Correlation-Adjusted Sizing
**Concept:** positions in highly correlated assets mean smaller size.
**Status:** Cluster guard ada (max 2), but size not disesuaikan.

**Example:** HYPE + ENA (corr 0.94) → if buka dua, size masing-masing 50%.

**not yet diimplementasi.**

---

### 3.4 Volatility Targeting
**Concept:** a constant dollar risk target rather than a percentage.
**Status:** ATR SL already menormalkan risk per trade, but not yet target portfolio volatility.

**not yet diimplementasi.**

---

### 3.5 Monte Carlo Position Sizing
**Concept:** simulate 1000 scenarios to find the optimal size.
**Status:** already dilakukan sekali (MM research), result: 0.75% optimal for DD -16%.

**done, but needs an update after any strategy change.**

---

### 3.6 Kelly Criterion (Fractional)
**Formula:** f = (p×b - q) / b
- p = win rate
- b = avg win / avg loss
- q = 1-p

**from data kita:**
- 15m: p=0.30, b=4.0 → f = (0.30×4 - 0.70)/4 = **0.125** (12.5%)
- Half-Kelly = 6.25% per trade

**We are using 0.25%.** Well below Kelly. **Conservative, and that is good.**

---

## PART 4: FATAL MISTAKES TO AVOID

### 4.1 Menambah strategy Saat loss
**Psychology:** "this strategy failed, try another one."
**Reality:** every strategy needs a large sample to evaluate. Switching strategies resets the sample.

**that kita alami:**
- sweep_fade → bollinger → breakout
- Every switch means 0 new trades of evidence
- **We already switched strategies 3x in a single day**

**Rule:** do not evaluate a strategy before 50 trades.

---

### 4.2 Menurunkan RR Saat Sering SL
**Psychology:** "the TP is too far, lower it so it triggers more often."
**Reality:** high RR needs low WR. Lowering RR does not raise expectancy.

**Bukti kita:** RR 1:2 PF 0.54, RR 1:5 PF 1.02. **RR high better.**

---

### 4.3 Menambah Filter Saat loss
**Psikologi:** "Tambah filter so that lebih selektif."
**Realita:** Filter = kurangi sample = kurangi edge.

**Bukti kita:** ADX filter −157R, ATR filter −140R. **Filter merusak.**

---

### 4.4 Revenge Trading
**Psikologi:** "Kena SL, masuk lagi langsung so that balik modal."
**Realita:** Cooldown ada alasannya.

**Kita cabut cooldown.** Ini berisiko. data: ENA kena SL 4x berturut.

---

## PART 5: GO-LIVE SYSTEM CHECKLIST

| Kriteria | Standar | Status kita |
|---|---|---|
| Sample backtest | > 200 trade | ⚠️ 695 (15m) ✅, 604 (5m) ✅ |
| Out-of-sample | PF > 1.2 | ✅ 15m PF 1.34 |
| Sensitivity test | parameter ±20% tetap profit | ❌ **not yet** |
| Execution model | next_open + slippage | ❌ **not yet** |
| Fee realistic | 0.09% round-trip | ⚠️ using 0.08% |
| Max DD acceptable | < 25% | ✅ 21.5% |
| Sharpe > 1.0 | | ❌ not yet dihitung |
| Live sample | > 100 trade | ❌ new 48 |
| Regime filter | | ✅ slope 1.5 |
| Position sizing | Fixed-fractional | ✅ 0.25% |

**Score: 6/10.** not yet siap live penuh.

---

## PART 6: REMEDIATION ROADMAP

### Phase 1: Validasi Eksekusi (SEKARANG)
- [ ] Test execution model (running)
- [ ] Sensitivity test parameter
- [ ] compute Sharpe ratio

### Phase 2: Perbaiki exit
- [ ] Trailing stop (bukan BE)
- [ ] Partial TP bertingkat
- [ ] Time-based exit

### Phase 3: Portfolio Level
- [ ] Correlation-adjusted sizing
- [ ] Volatility targeting
- [ ] Max portfolio DD guard

### Phase 4: Live Validation
- [ ] 100 trade shadow
- [ ] Compare live vs backtest per trade
- [ ] Adjust if PF live < 0.8 × PF backtest

---

## KESIMPULAN JUJUR

**Kita not yet punya sistem that "win terus".** none that punya.

that kita punya:
- strategy with edge **small** (PF 1.34)
- Eksekusi that **not yet tervalidasi** (look-ahead bias mungkin)
- Sample live **terlalu small** (48 trade)
- 3x ganti strategy dalam 1 days (**red flag**)

that must dilakukan:
1. **Berhenti ganti strategy.** Biarkan breakout 15m jalan 100 trade.
2. **measure execution gap** (test currently jalan).
3. **do not tambah filter.**
4. **Trailing stop** = prioritas berikutnya.

> Sistematic trading bukan tentang menemukan strategy sempurna.
> Ini tentang **disiplin menjalankan satu strategy cukup old** for tahu apakah edge-nya nyata.

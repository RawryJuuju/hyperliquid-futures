# SYSTEMATIC TRADING: WHY LIVE ≠ BACKTEST
## Analisa Mendalam untuk Sistem HL Futures

---

## BAGIAN 1: TAXONOMY KEGAGALAN SISTEMATIK

### 1.1 Overfitting (Curve Fitting)
**Definisi:** Parameter dioptimasi pada data historis sampai "sempurna" di data itu,
tapi tidak punya predictive power di data baru.

**Gejala:**
- PF backtest > 2.0 (terlalu bagus)
- Sample kecil (< 50 trade)
- Parameter sangat spesifik (look=7, atr=1.37, body=0.43)
- Performa hancur di out-of-sample

**Yang kita alami:**
- sweep_fade backtest PF 1.6-2.4 → live PF 0.25
- **Diagnosis: overfit.** 14 trade live, WR 7.1% vs backtest 40%

**Mitigasi:**
- Walk-forward (sudah)
- Parameter harus "bulat" (look 10/20, bukan 7)
- Minimum 100 trade per konfigurasi
- Sensitivity test: parameter digeser ±20%, PF harus tetap > 1.0

---

### 1.2 Look-Ahead Bias
**Definisi:** Menggunakan informasi yang belum tersedia pada saat keputusan dibuat.

**Bentuk umum:**
- Entry di close candle sinyal (kita tahu close SETELAH candle tutup)
- Pakai high/low candle yang sama untuk cek SL/TP
- Indikator dihitung dengan data future

**Yang kita alami:**
- Backtest entry di `cur["c"]` = close candle sinyal
- Realitanya: bot baru deteksi SETELAH close, kirim order, fill di open berikutnya
- **Ini bias yang belum diukur sampai sekarang**

**Mitigasi:**
- Entry di `next_open`, bukan `close`
- SL/TP cek mulai bar SETELAH entry
- Shift semua indikator 1 bar

---

### 1.3 Survivorship Bias
**Definisi:** Hanya menganalisa aset yang masih ada, mengabaikan yang sudah delisted.

**Yang kita alami:**
- Kita pilih 11 coin dari top volume SEKARANG
- Coin yang dulu top tapi sekarang mati tidak masuk sample
- **Bias moderat** — crypto delisting lebih jarang dari saham

---

### 1.4 Transaction Cost Underestimation
**Definisi:** Backtest pakai fee lebih rendah dari realita.

**Yang kita pakai:**
- Fee 0.04% × 2 = 0.08% round-trip
- **Realita Hyperliquid:** taker 0.045%, maker 0.015%
- Kalau entry market: 0.045% + exit 0.045% = **0.09%**
- **Underestimate 12.5%**

**Dampak:** di SL 0.3%, fee 0.09% = 30% dari risk (bukan 26.7%)

**Mitigasi:**
- Pakai fee 0.05% per side (konservatif)
- Tambah slippage 0.02-0.05%

---

### 1.5 Slippage & Market Impact
**Definisi:** Harga fill berbeda dari harga yang diharapkan.

**Faktor:**
- Spread bid-ask
- Kedalaman orderbook
- Volatilitas saat order masuk
- Ukuran order relatif terhadap liquidity

**Hyperliquid spesifik:**
- Spread BTC/ETH: 1-2 bps
- Spread altcoin: 5-15 bps
- Order $500 di altcoin = bisa slippage 10+ bps

**Yang kita alami:**
- Entry market di close candle → slippage tidak dimodelkan
- Notional $300-1000 per trade → slippage signifikan di altcoin

---

### 1.6 Regime Change
**Definisi:** Kondisi pasar berubah dari periode backtest ke live.

**Contoh:**
- Backtest: trending kuat (bull run)
- Live: choppy/ranging
- Strategi trend-following hancur

**Yang kita alami:**
- Backtest 120d termasuk periode trending
- Live 17 jam: pasar ranging → breakout gagal terus

**Mitigasi:**
- Regime filter (sudah dicoba, slope 1.5 ATR membantu)
- Adaptive position sizing berdasarkan ATR percentile
- Reduce exposure saat ADX rendah... **TAPI tes kita bilang ADX filter merusak**

---

### 1.7 Execution Latency
**Definisi:** Delay antara sinyal dan eksekusi.

**Yang kita alami:**
- Scan interval 20 detik
- Candle 5m = 300 detik
- Latency maksimal 20 detik = 6.7% dari candle
- **Bias moderat**

**Mitigasi:**
- WebSocket untuk real-time price
- Pre-compute indikator
- Kurangi scan interval

---

### 1.8 Data Quality
**Definisi:** Data backtest berbeda dari data live.

**Yang kita alami:**
- Backtest: candle dari API historis
- Live: candle dari API yang sama
- **Bias minimal** ✅

---

## BAGIAN 2: HIERARKI PENTINGNYA KOMPONEN

Berdasarkan literatur & pengalaman, urutan kontribusi terhadap profit:

| Rank | Komponen | Kontribusi | Status kita |
|---|---|---|---|
| 1 | **Position Sizing** | 40% | ✅ Fixed-fractional 0.25% |
| 2 | **Risk Management** | 25% | ✅ ATR SL, max 6 posisi |
| 3 | **Exit Strategy** | 15% | ⚠️ TP fixed R, belum trailing |
| 4 | **Entry Timing** | 12% | ⚠️ Breakout, ada look-ahead |
| 5 | **Asset Selection** | 8% | ✅ 7 coin filtered |

**Insight:** Kita fokus 90% waktu di entry (rank 4), padahal kontribusinya cuma 12%.

---

## BAGIAN 3: YANG BELUM KITA LAKUKAN

### 3.1 Trailing Stop (bukan BE)
**BE lock gagal** karena memotong winner terlalu awal.
**Trailing stop** berbeda: mengikuti harga, bukan fixed di entry.

**Contoh:**
- Entry $100, SL $97 (risk $3)
- Harga naik ke $106 (+2R)
- Trailing: SL naik ke $103 (lock +1R)
- Harga naik ke $112 (+4R)
- Trailing: SL naik ke $109 (lock +3R)

**Bedanya dengan BE:** BE kunci di $100 (0R). Trailing kunci di +1R, +3R, dst.

**Belum dites.** Ini prioritas berikutnya.

---

### 3.2 Pyramiding (Add to Winner)
**Konsep:** Kalau posisi profit, tambah size.
**Risiko:** Bisa membalik profit jadi loss kalau harga balik.

**Belum dites.**

---

### 3.3 Correlation-Adjusted Sizing
**Konsep:** Posisi di aset berkorelasi tinggi = kurangi size.
**Status:** Cluster guard ada (max 2), tapi size tidak disesuaikan.

**Contoh:** HYPE + ENA (corr 0.94) → kalau buka dua, size masing-masing 50%.

**Belum diimplementasi.**

---

### 3.4 Volatility Targeting
**Konsep:** Target risk konstan dalam dollar, bukan persen.
**Status:** ATR SL sudah menormalkan risk per trade, tapi belum target portfolio volatility.

**Belum diimplementasi.**

---

### 3.5 Monte Carlo Position Sizing
**Konsep:** Simulasi 1000 skenario untuk cari size optimal.
**Status:** Sudah dilakukan sekali (MM research), hasil: 0.75% optimal untuk DD -16%.

**Sudah, tapi perlu update setelah perubahan strategi.**

---

### 3.6 Kelly Criterion (Fractional)
**Formula:** f = (p×b - q) / b
- p = win rate
- b = avg win / avg loss
- q = 1-p

**Dari data kita:**
- 15m: p=0.30, b=4.0 → f = (0.30×4 - 0.70)/4 = **0.125** (12.5%)
- Half-Kelly = 6.25% per trade

**Kita pakai 0.25%.** Jauh di bawah Kelly. **Konservatif, bagus.**

---

## BAGIAN 4: KESALAHAN FATAL YANG HARUS DIHINDARI

### 4.1 Menambah Strategi Saat Rugi
**Psikologi:** "Strategi ini gagal, coba yang lain."
**Realita:** Setiap strategi butuh sample besar untuk evaluasi. Ganti strategi = reset sample.

**Yang kita alami:**
- sweep_fade → bollinger → breakout
- Setiap ganti = 0 trade baru
- **Kita sudah 3x ganti strategi dalam 1 hari**

**Aturan:** Jangan evaluasi strategi sebelum 50 trade.

---

### 4.2 Menurunkan RR Saat Sering SL
**Psikologi:** "TP terlalu jauh, turunkan biar sering kena."
**Realita:** RR tinggi butuh WR rendah. Menurunkan RR tidak menaikkan expectancy.

**Bukti kita:** RR 1:2 PF 0.54, RR 1:5 PF 1.02. **RR tinggi lebih baik.**

---

### 4.3 Menambah Filter Saat Rugi
**Psikologi:** "Tambah filter biar lebih selektif."
**Realita:** Filter = kurangi sample = kurangi edge.

**Bukti kita:** ADX filter −157R, ATR filter −140R. **Filter merusak.**

---

### 4.4 Revenge Trading
**Psikologi:** "Kena SL, masuk lagi langsung biar balik modal."
**Realita:** Cooldown ada alasannya.

**Kita cabut cooldown.** Ini berisiko. Data: ENA kena SL 4x berturut.

---

## BAGIAN 5: CHECKLIST SISTEM YANG SIAP LIVE

| Kriteria | Standar | Status kita |
|---|---|---|
| Sample backtest | > 200 trade | ⚠️ 695 (15m) ✅, 604 (5m) ✅ |
| Out-of-sample | PF > 1.2 | ✅ 15m PF 1.34 |
| Sensitivity test | Parameter ±20% tetap profit | ❌ **belum** |
| Execution model | next_open + slippage | ❌ **belum** |
| Fee realistic | 0.09% round-trip | ⚠️ pakai 0.08% |
| Max DD acceptable | < 25% | ✅ 21.5% |
| Sharpe > 1.0 | | ❌ belum dihitung |
| Live sample | > 100 trade | ❌ baru 48 |
| Regime filter | | ✅ slope 1.5 |
| Position sizing | Fixed-fractional | ✅ 0.25% |

**Score: 6/10.** Belum siap live penuh.

---

## BAGIAN 6: ROADMAP PERBAIKAN

### Phase 1: Validasi Eksekusi (SEKARANG)
- [ ] Test execution model (running)
- [ ] Sensitivity test parameter
- [ ] Hitung Sharpe ratio

### Phase 2: Perbaiki Exit
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

**Kita belum punya sistem yang "win terus".** Tidak ada yang punya.

Yang kita punya:
- Strategi dengan edge **kecil** (PF 1.34)
- Eksekusi yang **belum tervalidasi** (look-ahead bias mungkin)
- Sample live **terlalu kecil** (48 trade)
- 3x ganti strategi dalam 1 hari (**red flag**)

Yang harus dilakukan:
1. **Berhenti ganti strategi.** Biarkan breakout 15m jalan 100 trade.
2. **Ukur execution gap** (test sedang jalan).
3. **Jangan tambah filter.**
4. **Trailing stop** = prioritas berikutnya.

> Sistematic trading bukan tentang menemukan strategi sempurna.
> Ini tentang **disiplin menjalankan satu strategi cukup lama** untuk tahu apakah edge-nya nyata.

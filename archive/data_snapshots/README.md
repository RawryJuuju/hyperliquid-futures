# Trade data Snapshots

Immutable trade history archives, one per major version milestone.

| File | Version | Trades | Period |
|---|---|---|---|
| `fut_trades_v1.0_157trades.jsonl` | v1.0 baseline | 157 | Oct 20, 2026 |
| `fut_trades_v1.6_511trades.jsonl` | v1.6 final (pre-v1.7) | 511 | Oct 20 – Nov 15, 2026 |
| `equity_curve_v1.6.jsonl` | v1.6 final equity | 967 points | Oct 20 – Nov 15, 2026 |

Live trade log continues at repo root (`fut_trades.jsonl`).

Snapshot policy: taken at every version supersede event, before strategy parameter changes.

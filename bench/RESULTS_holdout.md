# Benchmark results (holdout)

| Numbers in the answer | Cases | number-receipts | string match | rounding set |
|---|---:|---:|---:|---:|
| correct, exact | 35 | 94% | 100% | 100% |
| correct, rounded | 13 | 100% | 0% | 38% |
| correct, hedged | 8 | 100% | 0% | 0% |
| correct, derived | 9 | 100% | 0% | 0% |
| wrong, fabricated | 22 | 100% | 100% | 100% |
| wrong, swapped | 13 | 77% | 38% | 0% |
| wrong, wrong metric | 6 | 100% | 0% | 0% |
| wrong, bad math | 8 | 88% | 100% | 100% |
| **Correct numbers passed** | 65 | **97%** | **54%** | **62%** |
| **Wrong numbers caught** | 49 | **92%** | **71%** | **61%** |

114 cases. Swapped or wrong-metric numbers reported as MISMATCH with the value the sentence should have used: 16/19.

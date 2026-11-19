# Benchmark results (cases)

| Numbers in the answer | Cases | number-receipts | string match | rounding set |
|---|---:|---:|---:|---:|
| correct, exact | 60 | 100% | 100% | 100% |
| correct, rounded | 16 | 100% | 0% | 50% |
| correct, hedged | 16 | 100% | 0% | 6% |
| correct, derived | 30 | 100% | 0% | 0% |
| correct, count | 8 | 100% | 0% | 0% |
| wrong, fabricated | 29 | 100% | 100% | 100% |
| wrong, swapped | 36 | 100% | 42% | 42% |
| wrong, wrong metric | 13 | 100% | 0% | 0% |
| wrong, transposed | 8 | 100% | 100% | 100% |
| wrong, bad math | 16 | 100% | 100% | 100% |
| wrong, wrong scale | 8 | 100% | 100% | 100% |
| **Correct numbers passed** | 130 | **100%** | **46%** | **53%** |
| **Wrong numbers caught** | 110 | **100%** | **69%** | **69%** |

240 cases. Swapped or wrong-metric numbers reported as MISMATCH with the value the sentence should have used: 49/49.

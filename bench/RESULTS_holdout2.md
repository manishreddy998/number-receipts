# Benchmark results (holdout2)

| Numbers in the answer | Cases | number-receipts | string match | rounding set |
|---|---:|---:|---:|---:|
| correct, exact | 50 | 100% | 100% | 100% |
| correct, rounded | 16 | 100% | 0% | 0% |
| correct, derived | 11 | 100% | 0% | 0% |
| wrong, fabricated | 23 | 91% | 87% | 87% |
| wrong, swapped | 18 | 100% | 44% | 44% |
| wrong, bad math | 5 | 100% | 100% | 100% |
| **Correct numbers passed** | 77 | **100%** | **65%** | **65%** |
| **Wrong numbers caught** | 46 | **96%** | **72%** | **72%** |

123 cases. Swapped or wrong-metric numbers reported as MISMATCH with the value the sentence should have used: 18/18.

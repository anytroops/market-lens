# Results

## Calibration (Phase 3)

Forecast = last market price at the stated horizon before close
(point-in-time, no lookahead). Outcome = 1 when the market's
proposition resolved YES. Kalshi no-trade candles use the bid/ask
midpoint when the closing spread is at most 0.20, else the market
drops out of that horizon's sample.

### Headline table

| Platform | Horizon | N | Brier | Reliability (cal. error) | Resolution | Uncertainty | Base rate |
|---|---|---|---|---|---|---|---|
| polymarket | 7d | 5,616 | 0.1343 | 0.0016 | 0.0705 | 0.2040 | 0.285 |
| polymarket | 24h | 14,658 | 0.1258 | 0.0001 | 0.0787 | 0.2051 | 0.288 |
| kalshi | 7d | 2,656 | 0.0708 | 0.0004 | 0.1074 | 0.1781 | 0.232 |
| kalshi | 24h | 10,661 | 0.1092 | 0.0002 | 0.0849 | 0.1947 | 0.265 |

![](figures/calibration_polymarket_7d.png)
![](figures/calibration_polymarket_24h.png)
![](figures/calibration_kalshi_7d.png)
![](figures/calibration_kalshi_24h.png)

### Do markets sharpen as resolution approaches? (paired sample)

Same markets scored at both horizons, so composition cannot
explain the difference. Sharpening means higher resolution and a
lower Brier at 24h than at 7d.

| Platform | N (paired) | Brier 7d | Brier 24h | Resolution 7d | Resolution 24h |
|---|---|---|---|---|---|
| polymarket | 5,616 | 0.1343 | 0.1144 | 0.0705 | 0.0892 |
| kalshi | 2,656 | 0.0708 | 0.0537 | 0.1074 | 0.1252 |

### Favorite-longshot bias (24h horizon)

| Platform | Segment | N | Mean implied prob | Empirical YES rate | Wilson 95% CI |
|---|---|---|---|---|---|
| polymarket | longshots (p < 0.10) | 5,318 | 0.021 | 0.017 | [0.014, 0.021] |
| polymarket | favorites (p > 0.90) | 625 | 0.971 | 0.982 | [0.969, 0.990] |
| kalshi | longshots (p < 0.10) | 4,568 | 0.031 | 0.023 | [0.019, 0.028] |
| kalshi | favorites (p > 0.90) | 581 | 0.967 | 0.974 | [0.958, 0.984] |

### Calibration by category (24h horizon, reliability component)

| Platform | Category | N | Brier | Reliability |
|---|---|---|---|---|
| polymarket | crypto | 1,262 | 0.0690 | 0.0011 |
| polymarket | econ | 259 | 0.0858 | 0.0032 |
| polymarket | entertainment | 745 | 0.0510 | 0.0014 |
| polymarket | other | 1,019 | 0.0799 | 0.0009 |
| polymarket | politics | 1,102 | 0.0601 | 0.0018 |
| polymarket | sports | 8,019 | 0.1725 | 0.0001 |
| polymarket | weather | 2,110 | 0.0744 | 0.0012 |
| kalshi | econ | 614 | 0.0629 | 0.0024 |
| kalshi | entertainment | 725 | 0.0444 | 0.0029 |
| kalshi | mentions | 476 | 0.1568 | 0.0019 |
| kalshi | politics | 570 | 0.0327 | 0.0019 |
| kalshi | sports | 7,228 | 0.1240 | 0.0003 |
| kalshi | weather | 981 | 0.1037 | 0.0014 |

### Calibration by volume tercile (24h horizon)

| Platform | Tercile | N | Brier | Reliability |
|---|---|---|---|---|
| polymarket | thin | 4,886 | 0.1159 | 0.0014 |
| polymarket | middle | 4,886 | 0.1222 | 0.0002 |
| polymarket | deep | 4,886 | 0.1394 | 0.0009 |
| kalshi | thin | 3,554 | 0.0547 | 0.0022 |
| kalshi | middle | 3,553 | 0.1206 | 0.0006 |
| kalshi | deep | 3,554 | 0.1523 | 0.0005 |

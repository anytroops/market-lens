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
| polymarket | 7d | 5,611 | 0.1344 | 0.0016 | 0.0705 | 0.2041 | 0.286 |
| polymarket | 24h | 14,638 | 0.1258 | 0.0001 | 0.0788 | 0.2052 | 0.288 |
| kalshi | 7d | 2,649 | 0.0709 | 0.0004 | 0.1076 | 0.1785 | 0.233 |
| kalshi | 24h | 10,643 | 0.1092 | 0.0002 | 0.0849 | 0.1948 | 0.265 |

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
| polymarket | 5,611 | 0.1344 | 0.1145 | 0.0705 | 0.0893 |
| kalshi | 2,649 | 0.0709 | 0.0538 | 0.1076 | 0.1254 |

### Favorite-longshot bias (24h horizon)

| Platform | Segment | N | Mean implied prob | Empirical YES rate | Wilson 95% CI |
|---|---|---|---|---|---|
| polymarket | longshots (p < 0.10) | 5,307 | 0.021 | 0.018 | [0.014, 0.021] |
| polymarket | favorites (p > 0.90) | 625 | 0.971 | 0.982 | [0.969, 0.990] |
| kalshi | longshots (p < 0.10) | 4,556 | 0.031 | 0.023 | [0.019, 0.027] |
| kalshi | favorites (p > 0.90) | 581 | 0.967 | 0.974 | [0.958, 0.984] |

### Calibration by category (24h horizon, reliability component)

| Platform | Category | N | Brier | Reliability |
|---|---|---|---|---|
| polymarket | crypto | 1,262 | 0.0690 | 0.0011 |
| polymarket | econ | 259 | 0.0858 | 0.0032 |
| polymarket | entertainment | 745 | 0.0510 | 0.0014 |
| polymarket | other | 1,019 | 0.0799 | 0.0009 |
| polymarket | politics | 1,098 | 0.0603 | 0.0018 |
| polymarket | sports | 8,004 | 0.1725 | 0.0001 |
| polymarket | weather | 2,110 | 0.0744 | 0.0012 |
| kalshi | econ | 614 | 0.0629 | 0.0024 |
| kalshi | entertainment | 725 | 0.0444 | 0.0029 |
| kalshi | mentions | 476 | 0.1568 | 0.0019 |
| kalshi | politics | 567 | 0.0328 | 0.0020 |
| kalshi | sports | 7,214 | 0.1240 | 0.0003 |
| kalshi | weather | 981 | 0.1037 | 0.0014 |

### Calibration by volume tercile (24h horizon)

| Platform | Tercile | N | Brier | Reliability |
|---|---|---|---|---|
| polymarket | thin | 4,879 | 0.1157 | 0.0014 |
| polymarket | middle | 4,879 | 0.1223 | 0.0002 |
| polymarket | deep | 4,880 | 0.1394 | 0.0009 |
| kalshi | thin | 3,548 | 0.0546 | 0.0021 |
| kalshi | middle | 3,547 | 0.1206 | 0.0005 |
| kalshi | deep | 3,548 | 0.1524 | 0.0005 |

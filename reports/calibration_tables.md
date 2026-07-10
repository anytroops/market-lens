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
| polymarket | 7d | 5,134 | 0.1493 | 0.0027 | 0.0603 | 0.2078 | 0.295 |
| polymarket | 24h | 14,189 | 0.1444 | 0.0001 | 0.0742 | 0.2192 | 0.325 |
| kalshi | 7d | 1,762 | 0.0754 | 0.0008 | 0.1105 | 0.1854 | 0.246 |
| kalshi | 24h | 8,944 | 0.1157 | 0.0005 | 0.0846 | 0.2007 | 0.278 |

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
| polymarket | 5,134 | 0.1493 | 0.1249 | 0.0603 | 0.0827 |
| kalshi | 1,762 | 0.0754 | 0.0561 | 0.1105 | 0.1291 |

### Favorite-longshot bias (24h horizon)

| Platform | Segment | N | Mean implied prob | Empirical YES rate | Wilson 95% CI |
|---|---|---|---|---|---|
| polymarket | longshots (p < 0.10) | 4,394 | 0.020 | 0.017 | [0.013, 0.021] |
| polymarket | favorites (p > 0.90) | 529 | 0.971 | 0.981 | [0.966, 0.990] |
| kalshi | longshots (p < 0.10) | 3,622 | 0.031 | 0.024 | [0.020, 0.030] |
| kalshi | favorites (p > 0.90) | 555 | 0.968 | 0.957 | [0.936, 0.971] |

### Calibration by category (24h horizon, reliability component)

| Platform | Category | N | Brier | Reliability |
|---|---|---|---|---|
| polymarket | crypto | 2,710 | 0.1657 | 0.0006 |
| polymarket | econ | 264 | 0.0909 | 0.0021 |
| polymarket | entertainment | 536 | 0.0479 | 0.0018 |
| polymarket | other | 1,119 | 0.0960 | 0.0016 |
| polymarket | politics | 732 | 0.0753 | 0.0034 |
| polymarket | sports | 6,580 | 0.1859 | 0.0001 |
| polymarket | weather | 2,111 | 0.0742 | 0.0013 |
| kalshi | econ | 629 | 0.0651 | 0.0036 |
| kalshi | entertainment | 610 | 0.0573 | 0.0064 |
| kalshi | mentions | 526 | 0.1609 | 0.0022 |
| kalshi | politics | 246 | 0.0374 | 0.0091 |
| kalshi | sports | 5,861 | 0.1288 | 0.0007 |
| kalshi | weather | 1,007 | 0.1066 | 0.0017 |

### Calibration by volume tercile (24h horizon)

| Platform | Tercile | N | Brier | Reliability |
|---|---|---|---|---|
| polymarket | thin | 4,730 | 0.1287 | 0.0010 |
| polymarket | middle | 4,729 | 0.1449 | 0.0006 |
| polymarket | deep | 4,730 | 0.1597 | 0.0009 |
| kalshi | thin | 2,981 | 0.0601 | 0.0033 |
| kalshi | middle | 2,981 | 0.1192 | 0.0008 |
| kalshi | deep | 2,982 | 0.1677 | 0.0009 |

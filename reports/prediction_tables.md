# Prediction Tables (generated)

Logistic regression on logit(price) plus extra features, versus
the market price alone. Temporal split: train on markets
resolving through 2026-06-12 (n = 17,703), test on
those from 2026-06-12 onward (n = 7,578).

| Model | Log loss | Brier |
|---|---|---|
| Market price alone | 0.3509 | 0.1136 |
| Recalibrated price only | 0.3508 | 0.1136 |
| Logistic + features | 0.3512 | 0.1138 |
| Always base rate (0.248) | 0.5607 | n/a |

Paired log-loss gain over the raw price: **-0.00027 +/- 0.00056** (t = -0.48). Compared on the same test markets, so which markets happened to be easy cannot explain the difference.

Decomposing that gain:

- Recalibrating the price alone (fitted slope and intercept, no new information): 0.00016 (t = 0.42)
- What the extra features add ON TOP of recalibration: -0.00043 (t = -1.36)

Fitted coefficient on logit(price): **1.0796** (1.0 means the market price is used as-is), intercept -0.1598.

| Feature | Coefficient |
|---|---|
| logit_price | +1.0796 |
| bucket_science | +0.3639 |
| bucket_politics | +0.3255 |
| bucket_econ | +0.2870 |
| bucket_entertainment | +0.1894 |
| bucket_mentions | +0.1353 |
| bucket_weather | +0.0974 |
| platform_polymarket | +0.0951 |
| bucket_sports | +0.0784 |
| has_momentum | +0.0746 |
| momentum_7d | -0.0515 |
| bucket_other | +0.0146 |
| lifetime_days | -0.0024 |
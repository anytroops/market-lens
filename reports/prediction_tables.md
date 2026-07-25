# Prediction Tables (generated)

Logistic regression on logit(price) plus extra features, versus
the market price alone. Temporal split: train on markets
resolving through 2026-06-13 (n = 17,953), test on
those from 2026-06-13 onward (n = 7,695).

| Model | Log loss | Brier |
|---|---|---|
| Market price alone | 0.3600 | 0.1166 |
| Recalibrated price only | 0.3598 | 0.1165 |
| Logistic + features | 0.3598 | 0.1166 |
| Always base rate (0.253) | 0.5651 | n/a |

Paired log-loss gain over the raw price: **0.00022 +/- 0.00056** (t = 0.40). Compared on the same test markets, so which markets happened to be easy cannot explain the difference.

Decomposing that gain:

- Recalibrating the price alone (fitted slope and intercept, no new information): 0.00019 (t = 0.66)
- What the extra features add ON TOP of recalibration: 0.00003 (t = 0.08)

Fitted coefficient on logit(price): **1.0518** (1.0 means the market price is used as-is), intercept -0.2084.

| Feature | Coefficient |
|---|---|
| logit_price | +1.0518 |
| bucket_politics | +0.3497 |
| bucket_science | +0.3486 |
| bucket_econ | +0.2925 |
| bucket_mentions | +0.1883 |
| platform_polymarket | +0.1243 |
| bucket_sports | +0.0932 |
| momentum_7d | -0.0910 |
| bucket_weather | +0.0893 |
| has_momentum | +0.0635 |
| bucket_entertainment | +0.0417 |
| bucket_other | +0.0337 |
| lifetime_days | -0.0021 |
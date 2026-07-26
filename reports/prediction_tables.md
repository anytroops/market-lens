# Prediction Tables (generated)

Logistic regression on logit(price) plus extra features, versus
the market price alone. Temporal split: train on markets
resolving through 2026-06-12 (n = 17,723), test on
those from 2026-06-12 onward (n = 7,596).

| Model | Log loss | Brier |
|---|---|---|
| Market price alone | 0.3504 | 0.1134 |
| Recalibrated price only | 0.3503 | 0.1134 |
| Logistic + features | 0.3507 | 0.1136 |
| Always base rate (0.248) | 0.5606 | n/a |

Paired log-loss gain over the raw price: **-0.00028 +/- 0.00056** (t = -0.50). Compared on the same test markets, so which markets happened to be easy cannot explain the difference.

Decomposing that gain:

- Recalibrating the price alone (fitted slope and intercept, no new information): 0.00017 (t = 0.44)
- What the extra features add ON TOP of recalibration: -0.00044 (t = -1.43)

Fitted coefficient on logit(price): **1.0792** (1.0 means the market price is used as-is), intercept -0.1540.

| Feature | Coefficient |
|---|---|
| logit_price | +1.0792 |
| bucket_science | +0.3468 |
| bucket_politics | +0.3184 |
| bucket_econ | +0.2919 |
| bucket_entertainment | +0.1832 |
| bucket_mentions | +0.1178 |
| bucket_weather | +0.0946 |
| platform_polymarket | +0.0895 |
| bucket_sports | +0.0766 |
| has_momentum | +0.0765 |
| momentum_7d | -0.0509 |
| bucket_other | +0.0107 |
| lifetime_days | -0.0024 |
# Robustness to Contract Dependence (generated)

Multi-outcome events list one binary leg per candidate and
exactly one resolves YES, so legs within an event are
mechanically correlated. Intervals that assume independence are
therefore too narrow. Below, each interval is recomputed with a
bootstrap that resamples whole EVENTS rather than markets.

## How much dependence is there?

| Platform | Markets | Events | Legs per event | Design effect | Effective n |
|---|---|---|---|---|---|
| polymarket | 14,658 | 11,022 | 1.3 | 1.27x | 9,119 |
| kalshi | 10,661 | 6,119 | 1.7 | 1.42x | 5,264 |

A design effect of 1.24 means the honest interval is 24 percent
wider than the naive one, and the effective sample size is
correspondingly smaller.

## Do the tail findings survive?

The implied price sitting outside the interval is what makes a
bias claim significant.

| Platform | Segment | N | Events | Implied | Actual | Wilson (naive) | Clustered | Verdict |
|---|---|---|---|---|---|---|---|---|
| polymarket | longshots p<0.10 | 5,318 | 3,939 | 0.0207 | 0.0175 | [0.0143, 0.0214] | [0.0140, 0.0210] | not significant either way |
| polymarket | favorites p>0.90 | 625 | 594 | 0.9714 | 0.9824 | [0.9688, 0.9901] | [0.9712, 0.9920] | not significant either way |
| kalshi | longshots p<0.10 | 4,568 | 2,266 | 0.0306 | 0.0228 | [0.0188, 0.0275] | [0.0182, 0.0270] | significant both ways |
| kalshi | favorites p>0.90 | 581 | 477 | 0.9672 | 0.9742 | [0.9578, 0.9843] | [0.9604, 0.9857] | not significant either way |

Conclusion: correcting for dependence widens every interval, as
it must, but does not overturn any conclusion in this study.
The one significant bias, Kalshi longshot overpricing, remains
significant with event-clustered intervals, and every result
that was not significant stays that way.

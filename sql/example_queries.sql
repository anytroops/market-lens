-- Analytical queries used by market-lens. These back the data quality report
-- and later analysis phases, kept here as first-class SQL artifacts.
-- Statement separators appear only at the end of statements, never inside
-- a comment, so tooling can split this file safely.
-- Conventions: markets.*_ts are ISO 8601 UTC text, prices.ts is unix seconds,
-- prices are probabilities in [0, 1].

-- 1. Headline dataset size and outcome base rate per platform.
SELECT platform,
       COUNT(*)                                        AS markets,
       SUM(outcome = 'YES')                            AS yes_count,
       ROUND(AVG(outcome = 'YES'), 4)                  AS yes_share
FROM headline_markets
GROUP BY platform;

-- 2. Monthly close-date coverage with a running total (window function).
SELECT platform,
       substr(close_ts, 1, 7)                          AS month,
       COUNT(*)                                        AS markets,
       SUM(COUNT(*)) OVER (PARTITION BY platform
                           ORDER BY substr(close_ts, 1, 7)) AS cumulative
FROM headline_markets
GROUP BY platform, month
ORDER BY platform, month;

-- 3. Category breakdown with share of platform total (window function).
SELECT platform,
       COALESCE(category, '(none)')                    AS category,
       COUNT(*)                                        AS markets,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY platform), 2)
                                                       AS pct_of_platform
FROM headline_markets
GROUP BY platform, category
ORDER BY platform, markets DESC;

-- 4. Price coverage per market: daily rows observed vs lifetime days (join).
SELECT m.platform,
       m.market_id,
       m.title,
       COUNT(p.ts)                                     AS price_days,
       ROUND(julianday(m.close_ts) - julianday(m.open_ts), 1) AS lifetime_days,
       ROUND(MIN(1.0, COUNT(p.ts) /
             MAX(julianday(m.close_ts) - julianday(m.open_ts), 1.0)), 3)
                                                       AS coverage
FROM markets m
JOIN prices p ON p.platform = m.platform AND p.market_id = m.market_id
GROUP BY m.platform, m.market_id
ORDER BY coverage ASC;

-- 5. Last observed price before close vs final outcome (join + window
--    function). This is the seed of the calibration study: the final price
--    should approximate the resolution frequency within buckets.
WITH last_prices AS (
    SELECT p.platform,
           p.market_id,
           COALESCE(p.price, (p.bid + p.ask) / 2.0)    AS prob,
           ROW_NUMBER() OVER (PARTITION BY p.platform, p.market_id
                              ORDER BY p.ts DESC)      AS rn
    FROM prices p
)
SELECT h.platform,
       ROUND(lp.prob * 10) / 10.0                      AS price_bucket,
       COUNT(*)                                        AS markets,
       ROUND(AVG(h.outcome = 'YES'), 3)                AS empirical_yes_rate
FROM headline_markets h
JOIN last_prices lp ON lp.platform = h.platform
                   AND lp.market_id = h.market_id
                   AND lp.rn = 1
WHERE lp.prob IS NOT NULL
GROUP BY h.platform, price_bucket
ORDER BY h.platform, price_bucket;

-- 6. Volume terciles within platform (NTILE window function), used for the
--    "thin markets are worse calibrated" cut in Phase 3.
SELECT platform,
       NTILE(3) OVER (PARTITION BY platform ORDER BY volume) AS volume_tercile,
       market_id,
       volume
FROM headline_markets
WHERE volume IS NOT NULL;

"""Unit tests for the pure matching helpers."""

import datetime as dt
import json

from marketlens.matching import matcher
from marketlens.matching.matcher import Candidate, MatchInput


class TestNormalizeTitle:
    def test_lowercase_punctuation_whitespace(self):
        assert matcher.normalize_title("Will the Fed CUT rates?!") == \
            "will the fed cut rates"

    def test_collapses_spaces(self):
        assert matcher.normalize_title("a   b\tc") == "a b c"

    def test_empty_and_none(self):
        assert matcher.normalize_title("") == ""
        assert matcher.normalize_title(None) == ""


class TestCategoryBucket:
    def test_platform_specific_maps(self):
        assert matcher.category_bucket("polymarket", "Bitcoin") == "crypto"
        assert matcher.category_bucket("kalshi", "Crypto") == "crypto"
        assert matcher.category_bucket("polymarket", "Geopolitics") == "politics"
        assert matcher.category_bucket("kalshi", "Elections") == "politics"

    def test_unknown_goes_to_other(self):
        assert matcher.category_bucket("polymarket", "Weird New Tag") == "other"
        assert matcher.category_bucket("kalshi", None) == "other"


class TestKalshiMatchText:
    def test_appends_informative_subtitle(self):
        raw = json.dumps({"yes_sub_title": "Karen Bass"})
        text = matcher.kalshi_match_text("Who will win LA Mayor?", raw)
        assert "Karen Bass" in text

    def test_skips_redundant_subtitle(self):
        raw = json.dumps({"yes_sub_title": "Fed cut rates"})
        text = matcher.kalshi_match_text("Will the Fed cut rates?", raw)
        assert text == "Will the Fed cut rates?"

    def test_bad_json(self):
        assert matcher.kalshi_match_text("T", "not json") == "T"


class TestExtractNumbers:
    def test_thresholds_spreads_ranges(self):
        f = lambda s: matcher.extract_numbers(matcher.normalize_title(s))
        assert f("Points O/U 15.5") == {15.5}
        assert f("Spread: Mexico (-3.5)") == {3.5}
        assert f("between 84-85°F on May 31") == {84.0, 85.0, 31.0}
        assert f("1+ assists") == {1.0}

    def test_years_excluded(self):
        f = lambda s: matcher.extract_numbers(matcher.normalize_title(s))
        assert f("win the 2026 French Open") == set()
        assert f("UT-01 nominee") == {1.0}


class TestCompatible:
    """Each case reproduces a labeled false-match mode from the tuning sample."""

    def _c(self, a, b):
        return matcher.compatible(matcher.normalize_title(a),
                                  matcher.normalize_title(b))

    def test_threshold_mismatch_rejected(self):
        assert not self._c("OG Anunoby: Points O/U 15.5", "OG Anunoby: 15+ points")
        assert not self._c("O/U 9.5 Total Corners", "Brazil: 9+ corners")

    def test_range_off_by_one_rejected(self):
        assert not self._c("highest temperature between 100-101°F on May 31",
                           "maximum temperature 99-100° on May 31")

    def test_equivalent_spread_phrasing_kept(self):
        assert self._c("Spread: RC Strasbourg Alsace (-2.5)",
                       "Strasbourg Alsace wins by over 2.5 goals?")

    def test_max_vs_min_temperature_rejected(self):
        assert not self._c("Will the highest temperature in Miami be 84-85°F on May 29",
                           "Will the minimum temperature be 84-85° on May 29")

    def test_half_mismatch_rejected(self):
        assert not self._c("Argentina to win the second half?",
                           "Will Argentina win the 1st Half?")

    def test_toss_rejected_against_match_winner(self):
        assert not self._c("Lancashire vs Hampshire - Who wins the toss?",
                           "Lancashire Thunder vs Hampshire Winner?")

    def test_bare_matchup_needs_win_words(self):
        assert not self._c("Chicago Sky vs. Indiana Fever",
                           "Chicago vs Indiana: Overtime?")
        assert self._c("Edmonton Elks vs. Winnipeg Blue Bombers",
                       "Will Winnipeg Blue Bombers win the game?")

    def test_number_on_one_side_only_rejected(self):
        assert not self._c("Daizen Maeda: 3+ goals",
                           "Will Daizen Maeda score the most goals for Japan?")


class TestWeatherCityGuard:
    def test_known_series_requires_city_in_pm_title(self):
        pm = matcher.normalize_title("Will the highest temperature in Miami be 84-85°F?")
        assert matcher.weather_city_ok(pm, "KXHIGHMIA")
        assert not matcher.weather_city_ok(pm, "KXHIGHNY")

    def test_unknown_series_rejects(self):
        assert not matcher.weather_city_ok("anything", "KXHIGHXYZ")
        assert not matcher.weather_city_ok("anything", None)


def _mi(mid, text, day, bucket="politics", series=None):
    return MatchInput(market_id=mid, text=matcher.normalize_title(text),
                      close_date=dt.date.fromisoformat(day), bucket=bucket,
                      series=series)


class TestBuildCandidates:
    def test_finds_paraphrase_pair_at_generation_cutoff(self):
        # The spec's example paraphrase scores only ~54 on token_set_ratio
        # ("cut" vs "decreases", "September" vs "Sept"), which is why
        # candidates are GENERATED at a low cutoff and the acceptance
        # threshold is tuned on a labeled sample.
        pm = [_mi("p1", "Will the Fed cut rates in September?", "2026-06-10")]
        k = [_mi("k1", "Fed decreases rates at Sept meeting?", "2026-06-11")]
        out = matcher.build_candidates(pm, k, threshold=50)
        assert out == [Candidate("p1", "k1", out[0].score)]
        assert out[0].score >= 50

    def test_blocking_by_date(self):
        pm = [_mi("p1", "Fed cut rates September", "2026-06-01")]
        k = [_mi("k1", "Fed cut rates September", "2026-06-20")]
        assert matcher.build_candidates(pm, k, threshold=60, window_days=3) == []

    def test_sports_window_is_one_day(self):
        # Same title two days apart in sports is a different game.
        pm = [_mi("p1", "Will Jake Knapp finish top 10 at the Memorial?",
                  "2026-06-04", bucket="sports")]
        k = [_mi("k1", "The Memorial: Will Jake Knapp finish top 10?",
                 "2026-06-07", bucket="sports")]
        assert matcher.build_candidates(pm, k, threshold=60) == []

    def test_blocking_by_bucket(self):
        pm = [_mi("p1", "Lakers beat Celtics", "2026-06-10", bucket="sports")]
        k = [_mi("k1", "Lakers beat Celtics", "2026-06-10", bucket="politics")]
        assert matcher.build_candidates(pm, k, threshold=60) == []

    def test_threshold_cutoff(self):
        pm = [_mi("p1", "Completely unrelated question about weather", "2026-06-10")]
        k = [_mi("k1", "Fed decreases rates at Sept meeting?", "2026-06-10")]
        assert matcher.build_candidates(pm, k, threshold=85) == []

    def test_mutual_best_is_injective(self):
        # Two Kalshi strikes both resemble one PM market; only the better
        # one survives, never both.
        pm = [_mi("p1", "Fed cuts rates by 25bps at June meeting", "2026-06-10")]
        k = [
            _mi("k1", "Will the Fed cut rates by 25bps at their June meeting?", "2026-06-10"),
            _mi("k2", "Will the Fed cut rates by 50bps at their June meeting?", "2026-06-10"),
        ]
        out = matcher.build_candidates(pm, k, threshold=60)
        assert len(out) == 1
        assert out[0].kalshi_id == "k1"

    def test_empty_inputs(self):
        assert matcher.build_candidates([], [], threshold=60) == []

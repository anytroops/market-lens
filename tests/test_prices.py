"""Unit tests for the shared price-selection rule."""

import pytest

from marketlens.analysis.prices import usable_price


class TestTradeConsistentWithBook:
    def test_trade_inside_book_is_used(self):
        assert usable_price(0.55, 0.54, 0.56) == 0.55

    def test_trade_just_outside_book_within_tolerance_is_used(self):
        assert usable_price(0.60, 0.54, 0.56) == 0.60  # 4pts above ask

    def test_trade_with_no_book_is_trusted(self):
        assert usable_price(0.42, None, None) == 0.42


class TestStalePrints:
    def test_the_seoul_case_is_rejected(self):
        # Real row: last trade 0.96 while the book was 0.08 to 0.14. A 96
        # cent trade cannot be real against a 14 cent ask.
        assert usable_price(0.96, 0.08, 0.14) == pytest.approx(0.11)

    def test_stale_low_print_rejected(self):
        # Real row: last 0.01 while the book was 0.50 to 0.62.
        assert usable_price(0.01, 0.50, 0.62) == pytest.approx(0.56)

    def test_stale_print_with_wide_book_gives_nothing(self):
        # Contradicted by the book AND the book is too wide to substitute.
        assert usable_price(0.96, 0.05, 0.60) is None

    def test_trade_at_the_ask_of_an_empty_book_is_rejected(self):
        # Real row: book 0.00 to 0.97 with a 9-lot printing at 0.97. The
        # trade is "inside" the book but the book carries no information.
        assert usable_price(0.97, 0.0, 0.97) is None


class TestQuoteOnlyDays:
    def test_tight_quote_midpoint(self):
        assert usable_price(None, 0.40, 0.44) == pytest.approx(0.42)

    def test_wide_quote_rejected(self):
        assert usable_price(None, 0.10, 0.90) is None

    def test_empty_book_rejected(self):
        # An untraded book shows 0 to 1, whose midpoint is a meaningless 0.5.
        assert usable_price(None, 0.0, 1.0) is None

    def test_no_data_at_all(self):
        assert usable_price(None, None, None) is None

    def test_crossed_book_is_not_trusted(self):
        assert usable_price(None, 0.60, 0.40) is None

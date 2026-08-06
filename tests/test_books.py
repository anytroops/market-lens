"""Hand-computed tests for the order book depth model."""

import pytest

from marketlens.live.books import (Book, Level, executable_cost,
                                   parse_kalshi_book, parse_polymarket_book,
                                   slippage_points, walk_book)


class TestParseKalshi:
    # Real shape from KXPRESPARTY-2028-R: yes bids top out at 0.41, and the
    # NO ladder topping out at 0.58 mirrors to a 0.42 YES ask.
    PAYLOAD = {"orderbook_fp": {
        "yes_dollars": [["0.3900", "5210.08"], ["0.4000", "23555.92"],
                        ["0.4100", "19853.11"]],
        "no_dollars": [["0.5600", "7203.92"], ["0.5700", "1341.00"],
                       ["0.5800", "17002.75"]]}}

    def test_best_prices_match_the_quoted_touch(self):
        b = parse_kalshi_book(self.PAYLOAD)
        assert b.best_bid == pytest.approx(0.41)
        assert b.best_ask == pytest.approx(0.42)
        assert b.spread == pytest.approx(0.01)

    def test_no_ladder_is_mirrored_into_yes_asks(self):
        b = parse_kalshi_book(self.PAYLOAD)
        assert [round(a.price, 2) for a in b.asks] == [0.42, 0.43, 0.44]
        assert b.asks[0].size == pytest.approx(17002.75)

    def test_one_sided_book(self):
        b = parse_kalshi_book({"orderbook_fp": {"yes_dollars": [], "no_dollars":
                                                [["0.9900", "10"]]}})
        assert b.best_bid is None
        assert b.best_ask == pytest.approx(0.01)

    def test_empty(self):
        b = parse_kalshi_book({})
        assert b.bids == [] and b.asks == [] and b.spread is None


class TestParsePolymarket:
    PAYLOAD = {"bids": [{"price": "0.001", "size": "18435.64"},
                        {"price": "0.40", "size": "100"}],
               "asks": [{"price": "0.44", "size": "50"},
                        {"price": "0.42", "size": "80"}]}

    def test_sides_are_ordered_best_first(self):
        b = parse_polymarket_book(self.PAYLOAD)
        assert b.best_bid == pytest.approx(0.40)
        assert b.best_ask == pytest.approx(0.42)

    def test_zero_size_levels_dropped(self):
        b = parse_polymarket_book({"bids": [{"price": "0.4", "size": "0"}],
                                   "asks": []})
        assert b.bids == []


class TestWalkBook:
    LEVELS = [Level(0.50, 100.0), Level(0.60, 100.0)]  # $50 then $60 available

    def test_fill_inside_the_first_level(self):
        f = walk_book(self.LEVELS, 25.0)
        assert f.complete
        assert f.vwap == pytest.approx(0.50)
        assert f.contracts == pytest.approx(50.0)
        assert f.levels_consumed == 1

    def test_fill_crossing_two_levels(self):
        # $50 at 0.50 buys 100 contracts, then $30 at 0.60 buys 50 more.
        # VWAP = 80 dollars / 150 contracts.
        f = walk_book(self.LEVELS, 80.0)
        assert f.complete
        assert f.contracts == pytest.approx(150.0)
        assert f.vwap == pytest.approx(80.0 / 150.0)
        assert f.levels_consumed == 2

    def test_book_too_thin_reports_incomplete(self):
        f = walk_book(self.LEVELS, 500.0)
        assert not f.complete
        assert f.filled_notional == pytest.approx(110.0)

    def test_empty_book(self):
        f = walk_book([], 10.0)
        assert not f.complete and f.vwap is None

    def test_zero_target(self):
        assert walk_book(self.LEVELS, 0.0).complete


class TestExecutableCost:
    BOOK = Book(bids=[Level(0.40, 1000)],
                asks=[Level(0.42, 100), Level(0.50, 1000)])

    def test_small_order_pays_the_touch(self):
        assert executable_cost(self.BOOK, 10.0) == pytest.approx(0.42)
        assert slippage_points(self.BOOK, 10.0) == pytest.approx(0.0)

    def test_large_order_pays_up(self):
        # $42 clears the touch, the next $58 comes from the 0.50 level.
        vwap = executable_cost(self.BOOK, 100.0)
        assert vwap > 0.42
        assert slippage_points(self.BOOK, 100.0) > 0

    def test_unfillable_size_returns_none(self):
        assert executable_cost(self.BOOK, 10_000.0) is None
        assert slippage_points(self.BOOK, 10_000.0) is None


class TestNoSide:
    # Best YES bid 0.40 means the best NO you can buy costs 0.60.
    BOOK = Book(bids=[Level(0.40, 100), Level(0.30, 100)],
                asks=[Level(0.42, 100)])

    def test_no_ladder_mirrors_yes_bids_best_first(self):
        from marketlens.live.books import no_ask_ladder
        ladder = no_ask_ladder(self.BOOK)
        assert [round(l.price, 2) for l in ladder] == [0.60, 0.70]

    def test_small_no_order_pays_the_touch(self):
        from marketlens.live.books import executable_no_cost
        assert executable_no_cost(self.BOOK, 10.0) == pytest.approx(0.60)

    def test_yes_and_no_touch_sum_above_one_when_spread_positive(self):
        from marketlens.live.books import executable_no_cost
        yes = executable_cost(self.BOOK, 10.0)
        no = executable_no_cost(self.BOOK, 10.0)
        # 0.42 + 0.60 = 1.02: crossing both sides of one book always loses.
        assert yes + no > 1.0

    def test_unfillable_no_order(self):
        from marketlens.live.books import executable_no_cost
        assert executable_no_cost(self.BOOK, 99_999.0) is None

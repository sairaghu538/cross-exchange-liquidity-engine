"""Unit tests for OrderBook engine."""

import pytest
from src.engine.order_book import OrderBook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def book():
    """Return a fresh OrderBook instance."""
    return OrderBook("BTC-USD")


@pytest.fixture
def snapshot_data():
    """Sample snapshot updates matching Coinbase L2 format."""
    return [
        {"side": "bid", "price_level": "100.00", "new_quantity": "5.0"},
        {"side": "bid", "price_level": "99.50", "new_quantity": "3.0"},
        {"side": "bid", "price_level": "99.00", "new_quantity": "8.0"},
        {"side": "offer", "price_level": "100.50", "new_quantity": "4.0"},
        {"side": "offer", "price_level": "101.00", "new_quantity": "2.0"},
        {"side": "offer", "price_level": "101.50", "new_quantity": "6.0"},
    ]


# ---------------------------------------------------------------------------
# Snapshot Tests
# ---------------------------------------------------------------------------

class TestApplySnapshot:
    def test_populates_bids_and_asks(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)

        assert book.bid_count == 3
        assert book.ask_count == 3
        assert book.is_initialized is True

    def test_replaces_existing_state(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        # Apply a smaller snapshot — old levels should be gone
        book.apply_snapshot([
            {"side": "bid", "price_level": "50.00", "new_quantity": "1.0"},
            {"side": "offer", "price_level": "51.00", "new_quantity": "1.0"},
        ])

        assert book.bid_count == 1
        assert book.ask_count == 1

    def test_skips_zero_quantity(self, book):
        book.apply_snapshot([
            {"side": "bid", "price_level": "100.00", "new_quantity": "0"},
            {"side": "offer", "price_level": "101.00", "new_quantity": "5.0"},
        ])

        assert book.bid_count == 0
        assert book.ask_count == 1

    def test_apply_binance_partial(self, book):
        bids = [["100.00", "1.5"], ["99.50", "2.0"]]
        asks = [["100.50", "3.0"], ["101.00", "4.0"]]
        
        book.apply_binance_partial(bids, asks)
        
        assert book.bid_count == 2
        assert book.ask_count == 2
        assert book.bids["100.00"] == 1.5
        assert book.asks["101.00"] == 4.0
        assert book.is_initialized is True


# ---------------------------------------------------------------------------
# Update Tests
# ---------------------------------------------------------------------------

class TestApplyUpdate:
    def test_modify_existing_level(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        book.apply_update([
            {"side": "bid", "price_level": "100.00", "new_quantity": "10.0",
             "event_time": "2024-01-01T00:00:01Z"},
        ])

        assert book.bids["100.00"] == 10.0

    def test_add_new_level(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        book.apply_update([
            {"side": "bid", "price_level": "98.00", "new_quantity": "7.0",
             "event_time": "2024-01-01T00:00:02Z"},
        ])

        assert book.bid_count == 4
        assert book.bids["98.00"] == 7.0

    def test_remove_level_on_zero_quantity(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        book.apply_update([
            {"side": "bid", "price_level": "100.00", "new_quantity": "0",
             "event_time": "2024-01-01T00:00:03Z"},
        ])

        assert "100.00" not in book.bids
        assert book.bid_count == 2

    def test_remove_nonexistent_level_no_error(self, book):
        book.apply_snapshot([])
        book.apply_update([
            {"side": "bid", "price_level": "999.99", "new_quantity": "0",
             "event_time": "2024-01-01T00:00:04Z"},
        ])

        assert book.bid_count == 0  # no crash

    def test_updates_last_event_time(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        book.apply_update([
            {"side": "offer", "price_level": "100.50", "new_quantity": "9.0",
             "event_time": "2024-06-15T12:30:00Z"},
        ])

        assert book.last_update_time == "2024-06-15T12:30:00Z"


# ---------------------------------------------------------------------------
# Sorting Tests
# ---------------------------------------------------------------------------

class TestTopLevels:
    def test_top_bids_sorted_descending(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        top = book.get_top_bids(3)

        prices = [p for p, _ in top]
        assert prices == [100.00, 99.50, 99.00]

    def test_top_asks_sorted_ascending(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        top = book.get_top_asks(3)

        prices = [p for p, _ in top]
        assert prices == [100.50, 101.00, 101.50]

    def test_top_bids_fewer_than_n(self, book):
        book.apply_snapshot([
            {"side": "bid", "price_level": "50.00", "new_quantity": "1.0"},
        ])

        top = book.get_top_bids(10)
        assert len(top) == 1

    def test_top_asks_fewer_than_n(self, book):
        book.apply_snapshot([
            {"side": "offer", "price_level": "60.00", "new_quantity": "1.0"},
        ])

        top = book.get_top_asks(10)
        assert len(top) == 1


# ---------------------------------------------------------------------------
# Spread & Mid Price Tests
# ---------------------------------------------------------------------------

class TestSpreadAndMid:
    def test_spread_calculation(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        spread = book.get_spread()

        # best bid = 100.00, best ask = 100.50
        assert spread == 0.50

    def test_mid_price_calculation(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        mid = book.get_mid_price()

        # (100.00 + 100.50) / 2 = 100.25
        assert mid == 100.25

    def test_spread_empty_book(self, book):
        assert book.get_spread() is None

    def test_mid_price_empty_book(self, book):
        assert book.get_mid_price() is None

    def test_spread_only_bids(self, book):
        book.apply_snapshot([
            {"side": "bid", "price_level": "100.00", "new_quantity": "5.0"},
        ])
        assert book.get_spread() is None

    def test_mid_only_asks(self, book):
        book.apply_snapshot([
            {"side": "offer", "price_level": "101.00", "new_quantity": "5.0"},
        ])
        assert book.get_mid_price() is None


# ---------------------------------------------------------------------------
# Sequence Number Tests
# ---------------------------------------------------------------------------

class TestSequenceTracking:
    def test_first_sequence(self, book):
        assert book.update_sequence(0) is True
        assert book.sequence_num == 0

    def test_consecutive_sequence(self, book):
        book.update_sequence(0)
        assert book.update_sequence(1) is True

    def test_gap_detected(self, book):
        book.update_sequence(0)
        assert book.update_sequence(5) is False  # gap: expected 1


# ---------------------------------------------------------------------------
# Repr Test
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_string(self, book, snapshot_data):
        book.apply_snapshot(snapshot_data)
        r = repr(book)
        assert "BTC-USD" in r
        assert "bids=3" in r
        assert "asks=3" in r

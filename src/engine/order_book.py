"""
OrderBook — Stateful order book reconstruction engine.

Maintains in-memory bid/ask price levels from exchange snapshot
and incremental update events. Pure Python — no UI dependencies.

Thread-safe: all reads take a snapshot of internal state so concurrent
writes from the feed thread don't cause RuntimeError during iteration.
"""

import threading
from datetime import datetime
from typing import Optional


class OrderBook:
    """Maintains a real-time order book from snapshot + incremental updates."""

    def __init__(self, product_id: str = "BTC-USD", exchange: str = "coinbase"):
        self.product_id = product_id
        self.exchange = exchange
        self._lock = threading.Lock()
        self._bids: dict[str, float] = {}  # price_level -> quantity
        self._asks: dict[str, float] = {}  # price_level -> quantity
        self.last_update_time: Optional[str] = None
        self.sequence_num: int = -1
        self.is_initialized: bool = False

    def apply_binance_partial(self, bids: list[list[str]], asks: list[list[str]]) -> None:
        """
        Apply a partial book update (Binance format).
        Replaces the entire book with the provided bids and asks.
        """
        with self._lock:
            self._bids = {p: float(q) for p, q in bids if float(q) > 0}
            self._asks = {p: float(q) for p, q in asks if float(q) > 0}
            self.is_initialized = True
            self.last_update_time = datetime.now().isoformat() + "Z"

    # -- Public read-only aliases (snapshot copies for thread safety) --

    @property
    def bids(self) -> dict[str, float]:
        with self._lock:
            return dict(self._bids)

    @property
    def asks(self) -> dict[str, float]:
        with self._lock:
            return dict(self._asks)

    def apply_snapshot(self, updates: list[dict]) -> None:
        """
        Apply a full order book snapshot. Replaces all existing state.

        Each update: {"side": "bid"|"offer", "price_level": "...", "new_quantity": "..."}
        """
        with self._lock:
            self._bids.clear()
            self._asks.clear()

            for entry in updates:
                side = entry.get("side", "")
                price = entry.get("price_level", "")
                qty = float(entry.get("new_quantity", "0"))

                if qty > 0:
                    if side == "bid":
                        self._bids[price] = qty
                    elif side == "offer":
                        self._asks[price] = qty

            self.is_initialized = True

    def apply_update(self, updates: list[dict]) -> None:
        """
        Apply incremental updates to the order book.

        If new_quantity is "0", the price level is removed.
        Otherwise, the price level is added or updated.
        """
        with self._lock:
            for entry in updates:
                side = entry.get("side", "")
                price = entry.get("price_level", "")
                qty = float(entry.get("new_quantity", "0"))
                event_time = entry.get("event_time", "")

                if event_time:
                    self.last_update_time = event_time

                if side == "bid":
                    if qty == 0:
                        self._bids.pop(price, None)
                    else:
                        self._bids[price] = qty
                elif side == "offer":
                    if qty == 0:
                        self._asks.pop(price, None)
                    else:
                        self._asks[price] = qty

    def get_top_bids(self, n: int = 10) -> list[tuple[float, float]]:
        """
        Return top N bid levels sorted by price descending.

        Returns: [(price, quantity), ...]
        """
        with self._lock:
            snapshot = list(self._bids.items())
        sorted_bids = sorted(
            [(float(p), q) for p, q in snapshot],
            key=lambda x: x[0],
            reverse=True,
        )
        return sorted_bids[:n]

    def get_top_asks(self, n: int = 10) -> list[tuple[float, float]]:
        """
        Return top N ask levels sorted by price ascending.

        Returns: [(price, quantity), ...]
        """
        with self._lock:
            snapshot = list(self._asks.items())
        sorted_asks = sorted(
            [(float(p), q) for p, q in snapshot],
            key=lambda x: x[0],
        )
        return sorted_asks[:n]

    def get_best_bid(self) -> Optional[float]:
        """Return the highest bid price, or None if no bids."""
        with self._lock:
            if not self._bids:
                return None
            return max(float(p) for p in self._bids.keys())

    def get_best_ask(self) -> Optional[float]:
        """Return the lowest ask price, or None if no asks."""
        with self._lock:
            if not self._asks:
                return None
            return min(float(p) for p in self._asks.keys())

    def get_spread(self) -> Optional[float]:
        """
        Calculate the bid-ask spread.

        Returns: best_ask - best_bid, or None if book is incomplete.
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is None or best_ask is None:
            return None
        return round(best_ask - best_bid, 2)

    def get_mid_price(self) -> Optional[float]:
        """
        Calculate the mid price.

        Returns: (best_ask + best_bid) / 2, or None if book is incomplete.
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is None or best_ask is None:
            return None
        return round((best_ask + best_bid) / 2, 2)

    def update_sequence(self, seq: int) -> bool:
        """
        Update the sequence number. Returns True if sequence is valid
        (no gap detected), False otherwise.
        """
        if self.sequence_num == -1:
            self.sequence_num = seq
            return True

        expected = self.sequence_num + 1
        self.sequence_num = seq

        if seq != expected:
            return False  # Gap detected
        return True

    @property
    def bid_count(self) -> int:
        with self._lock:
            return len(self._bids)

    @property
    def ask_count(self) -> int:
        with self._lock:
            return len(self._asks)

    def __repr__(self) -> str:
        return (
            f"OrderBook({self.product_id}, "
            f"bids={self.bid_count}, asks={self.ask_count}, "
            f"spread={self.get_spread()}, mid={self.get_mid_price()})"
        )

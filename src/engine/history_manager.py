"""
History Manager — SQLite persistence for cross-exchange metrics.

Handles storage and retrieval of arbitrage gaps and best prices.
Uses WAL mode for high-frequency write performance.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class HistoryManager:
    def __init__(self, db_path: str = "data/history.db"):
        self.db_path = db_path
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        """Standard connection with WAL mode enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        """Initialize the history table."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS arbitrage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    product_id TEXT,
                    cb_bid REAL,
                    cb_ask REAL,
                    bn_bid REAL,
                    bn_ask REAL,
                    arb_gap REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_product_ts ON arbitrage_history (product_id, timestamp)")
            conn.commit()
        finally:
            conn.close()

    def record_gap(self, product_id: str, cb_bid: float, cb_ask: float, bn_bid: float, bn_ask: float):
        """Record a single point in time for both exchanges."""
        # Arbitrage Gap Calculation: 
        # Usually Buying on cheaper exchange and selling on more expensive one.
        # Arb = (Expensive Bid - Cheap Ask)
        # We'll store a raw gap for trend analysis: (Binance Bid - Coinbase Ask)
        arb_gap = bn_bid - cb_ask if bn_bid and cb_ask else 0
        
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO arbitrage_history (product_id, cb_bid, cb_ask, bn_bid, bn_ask, arb_gap)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (product_id, cb_bid, cb_ask, bn_bid, bn_ask, arb_gap))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to record history: {e}")
        finally:
            conn.close()

    def get_recent_history(self, product_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve the last N records for a specific product."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("""
                SELECT timestamp, arb_gap FROM arbitrage_history 
                WHERE product_id = ? 
                ORDER BY timestamp DESC LIMIT ?
            """, (product_id, limit))
            rows = cursor.fetchall()
            # Return in chronological order for charting
            return [dict(row) for row in reversed(rows)]
        finally:
            conn.close()

    def clear_history(self, product_id: str = None):
        """Wipe the history table."""
        conn = self._get_connection()
        try:
            if product_id:
                conn.execute("DELETE FROM arbitrage_history WHERE product_id = ?", (product_id,))
            else:
                conn.execute("DELETE FROM arbitrage_history")
            conn.commit()
        finally:
            conn.close()

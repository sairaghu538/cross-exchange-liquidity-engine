"""
Event Processor — Async consumer that reads events from the queue
and routes them to the OrderBook engine.

Handles snapshot initialization, incremental updates, sequence
number tracking, and connection status changes.
Supports periodic history recording for trend analysis.
"""

import asyncio
import logging
import time
from typing import Optional, Callable

from src.engine.order_book import OrderBook
from src.engine.history_manager import HistoryManager

logger = logging.getLogger(__name__)


async def process_events(
    queue: asyncio.Queue,
    order_books: dict[str, OrderBook],  # exchange -> OrderBook
    on_status_change: Optional[Callable[[str, str], None]] = None,  # (status, exchange)
    shutdown_event: Optional[asyncio.Event] = None,
    history_manager: Optional[HistoryManager] = None,
) -> None:
    """
    Continuously consume events from the queue and apply them
    to the appropriate order book.
    """
    last_record_time = 0
    record_interval = 1.0  # Record history every 1 second

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Shutdown event received, stopping processor.")
            break

        try:
            # Wait for next event with short timeout to allow for periodic history recording
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                # Periodic recording even if no events arriving
                if history_manager:
                    last_record_time = _maybe_record_history(
                        order_books, history_manager, last_record_time, record_interval
                    )
                continue

            event_type = event.get("type", "")
            exchange = event.get("exchange", "coinbase")
            order_book = order_books.get(exchange)

            if event_type == "connection_status":
                status = event.get("status", "unknown")
                logger.info(f"[{exchange}] Connection status: {status}")
                if on_status_change:
                    on_status_change(status, exchange)
                continue

            if not order_book:
                continue

            if event_type == "snapshot":
                _handle_snapshot(event, order_book)
            elif event_type == "update":
                _handle_update(event, order_book)
            elif event_type == "binance_partial":
                _handle_binance_partial(event, order_book)

            # Check if it's time to record state to DB after an event
            if history_manager:
                last_record_time = _maybe_record_history(
                    order_books, history_manager, last_record_time, record_interval
                )

            queue.task_done()

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)


def _maybe_record_history(order_books, history_manager, last_time, interval):
    """Throttled recording of best prices to SQLite."""
    current_time = time.time()
    if current_time - last_time < interval:
        return last_time

    cb = order_books.get("coinbase")
    bn = order_books.get("binance")

    if cb and bn and cb.is_initialized and bn.is_initialized:
        history_manager.record_gap(
            product_id=cb.product_id,
            cb_bid=cb.get_best_bid() or 0,
            cb_ask=cb.get_best_ask() or 0,
            bn_bid=bn.get_best_bid() or 0,
            bn_ask=bn.get_best_ask() or 0
        )
        return current_time
    
    return last_time


def _handle_snapshot(event: dict, order_book: OrderBook) -> None:
    """Process a snapshot event — full order book replacement."""
    updates = event.get("updates", [])
    seq = event.get("sequence_num", 0)

    logger.info(
        f"[{order_book.exchange}] Received snapshot for {event.get('product_id', '?')} "
        f"with {len(updates)} levels (seq={seq})"
    )

    order_book.apply_snapshot(updates)
    order_book.update_sequence(seq)
    order_book.last_update_time = event.get("timestamp", "")

    logger.info(
        f"[{order_book.exchange}] Order book initialized: {order_book.bid_count} bids, "
        f"{order_book.ask_count} asks, spread={order_book.get_spread()}"
    )


def _handle_update(event: dict, order_book: OrderBook) -> None:
    """Process an incremental update event."""
    if not order_book.is_initialized:
        return

    updates = event.get("updates", [])
    seq = event.get("sequence_num", 0)

    # Check sequence continuity
    prev_seq = order_book.sequence_num
    seq_ok = order_book.update_sequence(seq)
    if not seq_ok:
        logger.warning(
            f"[{order_book.exchange}] Sequence gap detected! Expected {prev_seq + 1}, "
            f"got {seq}. Data may be stale."
        )

    order_book.apply_update(updates)
    order_book.last_update_time = event.get("timestamp", "")


def _handle_binance_partial(event: dict, order_book: OrderBook) -> None:
    """Process a Binance partial book update."""
    bids = event.get("bids", [])
    asks = event.get("asks", [])
    
    order_book.apply_binance_partial(bids, asks)
    order_book.sequence_num = event.get("last_update_id", 0)

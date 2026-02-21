"""
Event Processor — Async consumer that reads events from the queue
and routes them to the OrderBook engine.

Handles snapshot initialization, incremental updates, sequence
number tracking, and connection status changes.
"""

import asyncio
import logging
from typing import Optional, Callable

from src.engine.order_book import OrderBook

logger = logging.getLogger(__name__)


async def process_events(
    queue: asyncio.Queue,
    order_books: dict[str, OrderBook],  # exchange -> OrderBook
    on_status_change: Optional[Callable[[str, str], None]] = None,  # (status, exchange)
    shutdown_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Continuously consume events from the queue and apply them
    to the appropriate order book.
    """
    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Shutdown event received, stopping processor.")
            break

        try:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
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

            queue.task_done()

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)


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
    # Binance partial events don't usually need sequence tracking in the same way 
    # as Coinbase since each message is a full reset of the top levels.
    order_book.sequence_num = event.get("last_update_id", 0)

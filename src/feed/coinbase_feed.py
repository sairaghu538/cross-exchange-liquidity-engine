"""
Coinbase Advanced Trade WebSocket feed — Level 2 order book channel.

Connects to the public market data endpoint (no API key required),
subscribes to the level2 channel, and pushes parsed events into
an asyncio.Queue for downstream processing.
"""

import asyncio
import json
import logging
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WS_URL = "wss://advanced-trade-ws.coinbase.com"


async def connect_and_stream(
    queue: asyncio.Queue,
    product_id: str = "BTC-USD",
    shutdown_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Connect to Coinbase WebSocket level2 channel and stream events
    into the provided asyncio queue.

    Automatically reconnects on disconnection with exponential backoff.

    Args:
        queue: asyncio.Queue to push parsed events into.
        product_id: Trading pair to subscribe to (e.g. "BTC-USD").
        shutdown_event: Optional event to signal graceful shutdown.
    """
    backoff = 1  # seconds

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Shutdown event received, stopping feed.")
            break

        try:
            logger.info(f"Connecting to Coinbase WebSocket for {product_id}...")
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                max_size=10 * 1024 * 1024,  # 10MB — BTC-USD snapshot can be ~1MB+
            ) as ws:
                # Subscribe to level2 channel (no auth needed for market data)
                subscribe_msg = {
                    "type": "subscribe",
                    "product_ids": [product_id],
                    "channel": "level2",
                }
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"Subscribed to level2 channel for {product_id}")

                # Reset backoff on successful connection
                backoff = 1

                # Push a connection status event
                await queue.put({
                    "type": "connection_status",
                    "status": "connected",
                    "product_id": product_id,
                })

                async for raw_message in ws:
                    if shutdown_event and shutdown_event.is_set():
                        break

                    try:
                        message = json.loads(raw_message)
                        parsed = _parse_message(message)
                        if parsed:
                            await queue.put(parsed)
                    except json.JSONDecodeError:
                        logger.warning("Received non-JSON message, skipping.")
                    except Exception as e:
                        logger.error(f"Error parsing message: {e}")

        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}. Reconnecting in {backoff}s...")
        except Exception as e:
            logger.error(f"WebSocket error: {e}. Reconnecting in {backoff}s...")

        # Push disconnected status
        await queue.put({
            "type": "connection_status",
            "status": "disconnected",
            "product_id": product_id,
        })

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)  # Cap at 30 seconds


def _parse_message(message: dict) -> Optional[dict]:
    """
    Parse a Coinbase WebSocket message into a structured event.

    Coinbase level2 messages have format:
    {
        "channel": "l2_data",
        "timestamp": "...",
        "sequence_num": 0,
        "events": [
            {
                "type": "snapshot" | "update",
                "product_id": "BTC-USD",
                "updates": [
                    {"side": "bid"|"offer", "price_level": "...",
                     "new_quantity": "...", "event_time": "..."}
                ]
            }
        ]
    }

    Returns a structured dict or None if message is not relevant.
    """
    channel = message.get("channel", "")

    if channel != "l2_data":
        # Could be subscriptions confirmation, heartbeats, etc.
        return None

    events = message.get("events", [])
    if not events:
        return None

    # Process first event (typically only one per message)
    event = events[0]
    event_type = event.get("type", "")
    product_id = event.get("product_id", "")
    updates = event.get("updates", [])

    if event_type not in ("snapshot", "update"):
        return None

    return {
        "type": event_type,
        "product_id": product_id,
        "updates": updates,
        "sequence_num": message.get("sequence_num", 0),
        "timestamp": message.get("timestamp", ""),
    }

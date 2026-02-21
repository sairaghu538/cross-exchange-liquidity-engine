"""
Binance WebSocket feed — Partial Book Depth stream.

Connects to the public Binance WebSocket API (no API key required)
and streams the top 20 bid/ask levels for a given symbol.
Pushes parsed "binance_partial" events into an asyncio.Queue.
"""

import asyncio
import json
import logging
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

logger = logging.getLogger(__name__)

# Base WebSocket URLs
WS_GLOBAL_URL = "wss://stream.binance.com:9443/ws"
WS_US_URL = "wss://stream.binance.us:9443/ws"


async def connect_and_stream_binance(
    queue: asyncio.Queue,
    product_id: str = "BTC-USD",
    shutdown_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Connect to Binance WebSocket partial depth stream and push to queue.

    Args:
        queue: asyncio.Queue to push parsed events into.
        product_id: Standard product ID (e.g. "BTC-USD"). 
                   Converted to Binance format (e.g. "btcusdt").
        shutdown_event: Optional event to signal graceful shutdown.
    """
    # Map BTC-USD -> btcusdt
    binance_symbol = product_id.replace("-", "").lower()
    if binance_symbol == "btcusd":
        binance_symbol = "btcusdt"  # Use USDT as the standard for USD comparisons on Binance
    elif binance_symbol.endswith("usd"):
        binance_symbol = binance_symbol + "t"  # Most Binance pairs are USDT

    # Stream name: <symbol>@depth20@100ms
    stream_name = f"{binance_symbol}@depth20@100ms"
    
    # Try global first, unless we already know we need US
    use_us_endpoint = False
    backoff = 1  # seconds

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info(f"Binance shutdown event received, stopping feed for {product_id}.")
            break

        base_url = WS_US_URL if use_us_endpoint else WS_GLOBAL_URL
        ws_url = f"{base_url}/{stream_name}"

        try:
            logger.info(f">>> [Binance] Attempting connection to: {ws_url}")
            async with websockets.connect(ws_url) as ws:
                logger.info("**************************************************")
                logger.info(f"*** BINANCE CONNECTED: {ws_url} ***")
                logger.info("**************************************************")
                
                # Reset backoff on successful connection
                backoff = 1

                # Push connection status event
                await queue.put({
                    "type": "connection_status",
                    "status": "connected",
                    "exchange": "binance",
                    "product_id": product_id,
                })

                async for raw_message in ws:
                    if shutdown_event and shutdown_event.is_set():
                        break

                    try:
                        message = json.loads(raw_message)
                        
                        # Partial book format: {"lastUpdateId": ..., "bids": [...], "asks": [...]}
                        # We wrap it in a standard event structure
                        await queue.put({
                            "type": "binance_partial",
                            "exchange": "binance",
                            "product_id": product_id,
                            "bids": message.get("bids", []),
                            "asks": message.get("asks", []),
                            "last_update_id": message.get("lastUpdateId", 0),
                        })
                    except Exception as e:
                        logger.error(f"Error parsing Binance message: {e}")

        except InvalidStatusCode as e:
            if e.status_code == 451:
                logger.warning("Binance Global rejected connection (HTTP 451). Switching to Binance US...")
                use_us_endpoint = True
                continue # Retry immediately with US endpoint
            else:
                logger.error(f"Binance WebSocket status error: {e}. Reconnecting in {backoff}s...")
        except ConnectionClosed as e:
            logger.warning(f"Binance WebSocket closed: {e}. Reconnecting in {backoff}s...")
        except Exception as e:
            err_msg = str(e)
            if "451" in err_msg:
                logger.warning(f"Binance Global rejected connection (HTTP 451 detected in message). Switching to Binance US...")
                use_us_endpoint = True
                continue
            logger.error(f"Binance WebSocket error: {e}. Reconnecting in {backoff}s...")

        # Push disconnected status
        await queue.put({
            "type": "connection_status",
            "status": "disconnected",
            "exchange": "binance",
            "product_id": product_id,
        })

        if shutdown_event and shutdown_event.is_set():
            break

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)

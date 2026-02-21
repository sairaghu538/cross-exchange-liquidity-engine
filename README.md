# Cross-Exchange Liquidity Engine

Real-time order book reconstruction and cross-exchange liquidity analytics engine using Coinbase and Binance WebSocket feeds. Built with asyncio, stateful event processing, and Streamlit visualization.

## 📸 Dashboard Preview

### Order Book Metrics & Top Levels
![Dashboard Top](assets/dashboard_top.png)

### Full Depth View & Statistics
![Dashboard Bottom](assets/dashboard_bottom.png)

## Level 2 — Multi-Exchange Comparison (Current)

The engine now streams real-time data from both **Coinbase** and **Binance** simultaneously to provide a unified view of market liquidity.

### New Features

- **Binance Integration** — Seamless connection to Binance Spot WebSocket API.
- **Global Best Price** — Aggregated best bid and best ask across both exchanges.
- **Arbitrage Tracking** — Automatic calculation of price gaps between exchanges.
- **Side-by-Side Visualization** — Compare depth and spread across platforms in real-time.
- **Automatic Symbol Mapping** — Handles exchange-specific naming conventions (e.g., BTC-USD vs btcusdt).

### Architecture (Level 2)

```
[Coinbase feed]  [Binance feed]
       \            /
     [asyncio.Queue]
            |
    [Event Processor]
       /            \
[Coinbase Book]  [Binance Book]
       \            /
    [Comparative UI]
```

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
python -m streamlit run app.py

# Run tests
pytest tests/ -v
```

### Project Structure

```
├── app.py                      # Streamlit entry point (sidebar + dashboard)
├── requirements.txt            # Dependencies
├── assets/                     # Screenshots
├── src/
│   ├── engine/
│   │   └── order_book.py       # Thread-safe OrderBook class
│   ├── feed/
│   │   └── coinbase_feed.py    # WebSocket listener (10MB max_size)
│   └── processor/
│       └── event_processor.py  # Async queue consumer
└── tests/
    └── test_order_book.py      # Unit tests (22 tests)
```

### Roadmap

- **Level 2** — Add Binance depth stream, compare liquidity across exchanges
- **Level 3** — Cross-exchange spread, arbitrage detection, liquidity imbalance metrics
- **Level 4** — Background worker + DB + separated Streamlit dashboard (Render + Streamlit Cloud)

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| WebSocket | `websockets` library |
| State Engine | Thread-safe Python (dict + Lock) |
| Queue | `asyncio.Queue` (in-process) |
| Dashboard | Streamlit + custom HTML/CSS |
| Tests | pytest |

### No API Key Required

The Coinbase Advanced Trade WebSocket market data endpoint (`wss://advanced-trade-ws.coinbase.com`) supports unauthenticated subscriptions for the `level2` channel. No API key or account needed.

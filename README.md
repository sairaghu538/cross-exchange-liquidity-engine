# Cross-Exchange Liquidity Engine

Real-time order book reconstruction and cross-exchange liquidity analytics engine using Coinbase and Binance WebSocket feeds. Built with asyncio, stateful event processing, and Streamlit visualization.

## 📸 Dashboard Preview

### Order Book Metrics & Top Levels
![Dashboard Top](assets/dashboard_top.png)

### Full Depth View & Statistics
![Dashboard Bottom](assets/dashboard_bottom.png)

## Level 1 — Coinbase Order Book (Current)

Real-time order book reconstruction from the Coinbase Advanced Trade Level 2 WebSocket feed with **multi-pair support**.

### Features

- **20 crypto pairs** — Switch instantly between BTC-USD, ETH-USD, SOL-USD, and 17 more via sidebar dropdown
- **Live order book reconstruction** — Snapshot + incremental updates from Coinbase
- **Top 10 bids/asks** — Sorted and displayed in real-time
- **Market metrics** — Spread, mid price, best bid/ask
- **Depth visualization** — Quantity depth bars per price level
- **Thread-safe engine** — Lock-protected OrderBook for concurrent UI/feed access
- **Auto-reconnect** — Exponential backoff on disconnection
- **Sequence tracking** — Gap detection for data integrity
- **Premium dark UI** — Glassmorphism cards, gradient theme, JetBrains Mono

### Supported Trading Pairs

| Pair | Pair | Pair | Pair |
|------|------|------|------|
| BTC-USD | ETH-USD | SOL-USD | XRP-USD |
| DOGE-USD | ADA-USD | AVAX-USD | DOT-USD |
| LINK-USD | MATIC-USD | UNI-USD | SHIB-USD |
| LTC-USD | NEAR-USD | ATOM-USD | ARB-USD |
| OP-USD | APT-USD | FIL-USD | PEPE-USD |

### Architecture

```
Coinbase WebSocket (wss://advanced-trade-ws.coinbase.com)
        ↓
  Async Producer Task → asyncio.Queue
        ↓
  Event Processor (snapshot/update routing)
        ↓
  OrderBook Engine (thread-safe bids/asks)
        ↓
  Streamlit Dashboard (sidebar pair selector + auto-refresh 1.5s)
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

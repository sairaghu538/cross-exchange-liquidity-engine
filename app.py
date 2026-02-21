"""
Cross-Exchange Liquidity Engine — Level 2
Real-time Coinbase + Binance Order Book Dashboard

Architecture:
  Background thread → asyncio event loop → WebSocket feeds (Coinbase/Binance) 
  → Queue → Event Processor → OrderBooks (per exchange)
  Streamlit UI → reads OrderBook states → Comparative Analytics
"""

import asyncio
import threading
import time
import logging
from datetime import datetime, timezone

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.engine.order_book import OrderBook
from src.feed.coinbase_feed import connect_and_stream
from src.feed.binance_feed import connect_and_stream_binance
from src.processor.event_processor import process_events

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Available Trading Pairs
# ---------------------------------------------------------------------------
CRYPTO_PAIRS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "DOGE-USD",
    "ADA-USD",
    "AVAX-USD",
    "DOT-USD",
    "LINK-USD",
    "MATIC-USD",
    "UNI-USD",
    "SHIB-USD",
    "LTC-USD",
    "NEAR-USD",
    "ATOM-USD",
    "ARB-USD",
    "OP-USD",
    "APT-USD",
    "FIL-USD",
    "PEPE-USD",
]


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Liquidity Engine — Order Book",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Custom CSS — Premium Dark Theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* ── Import Google Font ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

    /* ── Global ── */
    .stApp {
        background: linear-gradient(135deg, #0a0e1a 0%, #0d1321 40%, #111827 100%);
        font-family: 'Inter', sans-serif;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: rgba(10, 14, 26, 0.95) !important;
        border-right: 1px solid rgba(99, 102, 241, 0.15);
    }
    section[data-testid="stSidebar"] .stSelectbox label {
        color: #94a3b8 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
        font-size: 0.75rem !important;
    }
    .sidebar-title {
        font-size: 1.1rem;
        font-weight: 700;
        background: linear-gradient(135deg, #60a5fa, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
        letter-spacing: 0.5px;
    }
    .sidebar-divider {
        border-top: 1px solid rgba(99, 102, 241, 0.15);
        margin: 1rem 0;
    }

    /* ── Hero Header ── */
    .hero-header {
        text-align: center;
        padding: 1rem 0 0.5rem 0;
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #60a5fa, #f472b6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -1px;
        margin-bottom: 0.2rem;
    }

    /* ── Exchange Labels ── */
    .exchange-label {
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        padding: 2px 8px;
        border-radius: 4px;
        margin-bottom: 8px;
        display: inline-block;
    }
    .label-coinbase { background: #1652f0; color: white; }
    .label-binance { background: #f3ba2f; color: black; }

    /* ── Status Badge ── */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 50px;
        font-size: 0.75rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }
    .status-connected { background: rgba(16, 185, 129, 0.15); color: #10b981; }
    .status-disconnected { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
    
    .status-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    .dot-green { background: #10b981; }
    .dot-red { background: #ef4444; }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(0.8); }
    }

    /* ── Metric Cards ── */
    .metric-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 12px;
        padding: 1rem;
        backdrop-filter: blur(10px);
        margin-bottom: 10px;
    }
    .metric-label {
        font-size: 0.7rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.4rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        color: #e2e8f0;
    }
    .metric-value-tiny { font-size: 1.1rem; }
    .metric-best { color: #f472b6; border-color: #f472b6; }

    /* ── Order Book Table ── */
    .book-container {
        background: rgba(15, 23, 42, 0.4);
        border: 1px solid rgba(99, 102, 241, 0.1);
        border-radius: 12px;
        padding: 0.8rem;
        backdrop-filter: blur(5px);
    }
    .book-title {
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .book-title-bid { color: #10b981; }
    .book-title-ask { color: #ef4444; }

    table.book-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'JetBrains Mono', monospace;
    }
    table.book-table th {
        font-size: 0.65rem;
        color: #475569;
        text-align: right;
        padding: 4px 8px;
    }
    table.book-table th:first-child { text-align: left; }
    table.book-table td {
        padding: 4px 8px;
        font-size: 0.8rem;
        text-align: right;
        border-bottom: 1px solid rgba(255,255,255,0.02);
    }
    table.book-table td:first-child { text-align: left; }

    /* Bid/Ask highlighting */
    .bid-row td { color: #10b981; }
    .ask-row td { color: #ef4444; }
    
    .depth-bar {
        height: 2px;
        border-radius: 1px;
        margin-top: 2px;
    }
    .depth-bar-bid { background: #10b981; opacity: 0.3; }
    .depth-bar-ask { background: #ef4444; opacity: 0.3; }

    /* Comparisons */
    .arb-positive { background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; color: #10b981; }
    .arb-negative { background: rgba(239, 68, 68, 0.1); border: 1px solid #ef4444; color: #ef4444; }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Background Streaming Engine
# ---------------------------------------------------------------------------

def _run_async_engine(
    order_books: dict[str, OrderBook],
    status_holder: dict,
    product_id: str,
    shutdown_event: threading.Event,
):
    """Run multi-exchange feeds and processor."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    queue = asyncio.Queue(maxsize=10000)
    async_shutdown = asyncio.Event()

    def on_status_change(status: str, exchange: str):
        status_holder[exchange] = status

    async def watch_shutdown():
        while not shutdown_event.is_set():
            await asyncio.sleep(0.5)
        async_shutdown.set()

    async def engine():
        watcher = asyncio.create_task(watch_shutdown())
        
        # Coinbase Feed
        cb_task = asyncio.create_task(
            connect_and_stream(queue, product_id, async_shutdown)
        )
        
        # Binance Feed
        bn_task = asyncio.create_task(
            connect_and_stream_binance(queue, product_id, async_shutdown)
        )
        
        # Unified Processor
        proc_task = asyncio.create_task(
            process_events(queue, order_books, on_status_change, async_shutdown)
        )

        await watcher
        cb_task.cancel()
        bn_task.cancel()
        proc_task.cancel()
        await asyncio.gather(cb_task, bn_task, proc_task, return_exceptions=True)

    try:
        loop.run_until_complete(engine())
    except Exception as e:
        logger.error(f"Engine thread error: {e}")
    finally:
        loop.close()


def start_engine(product_id: str):
    """Initialize dual feeds for Coinbase and Binance."""
    current_pair = st.session_state.get("product_id")
    if current_pair == product_id and "cb_book" in st.session_state:
        return

    if current_pair:
        _stop_engine()

    cb_book = OrderBook(product_id=product_id, exchange="coinbase")
    bn_book = OrderBook(product_id=product_id, exchange="binance")
    status_holder = {"coinbase": "connecting", "binance": "connecting"}
    shutdown_event = threading.Event()

    st.session_state["cb_book"] = cb_book
    st.session_state["bn_book"] = bn_book
    st.session_state["status"] = status_holder
    st.session_state["product_id"] = product_id
    st.session_state["shutdown_event"] = shutdown_event

    thread = threading.Thread(
        target=_run_async_engine,
        args=({"coinbase": cb_book, "binance": bn_book}, status_holder, product_id, shutdown_event),
        daemon=True,
    )
    thread.start()
    st.session_state["engine_thread"] = thread


def _stop_engine():
    shutdown_event = st.session_state.get("shutdown_event")
    if shutdown_event:
        shutdown_event.set()
    thread = st.session_state.get("engine_thread")
    if thread:
        thread.join(timeout=2)
    for key in ["cb_book", "bn_book", "status", "product_id", "shutdown_event", "engine_thread"]:
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# UI Helpers
# ---------------------------------------------------------------------------

def render_status_badge(status: str) -> str:
    color = "green" if status == "connected" else "red"
    label = "CONNECTED" if status == "connected" else status.upper()
    return f'<span class="status-badge status-{status}"><span class="status-dot dot-{color}"></span>{label}</span>'


def render_book_table(book: OrderBook, side: str, n: int = 10):
    levels = book.get_top_bids(n) if side == "bid" else book.get_top_asks(n)
    if not levels: return "No data"
    
    max_qty = max(q for _, q in levels) if levels else 1
    row_class = "bid-row" if side == "bid" else "ask-row"
    bar_class = "depth-bar-bid" if side == "bid" else "depth-bar-ask"
    
    rows = ""
    for i, (p, q) in enumerate(levels):
        pct = (q / max_qty * 100)
        depth = f'<div class="depth-bar {bar_class}" style="width: {pct}%"></div>'
        rows += f'<tr class="{row_class}"><td>${p:,.2f}</td><td>{q:.4f}</td><td>{depth}</td></tr>'
        
    return f'<table class="book-table"><thead><tr><th>Price</th><th>Qty</th><th>Depth</th></tr></thead><tbody>{rows}</tbody></table>'


# ---------------------------------------------------------------------------
# Sidebar & Main
# ---------------------------------------------------------------------------

def main():
    st_autorefresh(interval=1500, key="refresh")

    with st.sidebar:
        st.markdown('<div class="sidebar-title">⚙️ Control Panel</div>', unsafe_allow_html=True)
        product_id = st.selectbox("Market Asset", options=CRYPTO_PAIRS)
        view_mode = st.radio("Display Mode", options=["Comparison", "Coinbase Only", "Binance Only"])
        
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        status = st.session_state.get("status", {})
        
        st.markdown('<div class="exchange-label label-coinbase">Coinbase</div>', unsafe_allow_html=True)
        st.markdown(render_status_badge(status.get("coinbase", "connecting")), unsafe_allow_html=True)
        
        st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)
        st.markdown('<div class="exchange-label label-binance">Binance</div>', unsafe_allow_html=True)
        st.markdown(render_status_badge(status.get("binance", "connecting")), unsafe_allow_html=True)

    start_engine(product_id)
    cb_book = st.session_state.get("cb_book")
    bn_book = st.session_state.get("bn_book")

    st.markdown(f'<div class="hero-header"><div class="hero-title">📊 Liquidity Engine Level 2</div><div style="color:#64748b; font-weight:700; font-family:JetBrains Mono">{product_id} Multi-Exchange Comparison</div></div>', unsafe_allow_html=True)

    if not cb_book or not bn_book or not (cb_book.is_initialized or bn_book.is_initialized):
        st.warning("Synchronizing feeds...")
        return

    # COMPARISON LOGIC
    best_cb_bid = cb_book.get_best_bid() or 0
    best_cb_ask = cb_book.get_best_ask() or 1e9
    best_bn_bid = bn_book.get_best_bid() or 0
    best_bn_ask = bn_book.get_best_ask() or 1e9
    
    global_best_bid = max(best_cb_bid, best_bn_bid)
    global_best_ask = min(best_cb_ask, best_bn_ask)
    bid_source = "Coinbase" if best_cb_bid >= best_bn_bid else "Binance"
    ask_source = "Coinbase" if best_cb_ask <= best_bn_ask else "Binance"

    # MAIN VIEW
    if view_mode == "Comparison":
        # Global Metrics
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Global Best Bid</div><div class="metric-value metric-best">${global_best_bid:,.2f}</div><div class="sidebar-info">{bid_source}</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Global Best Ask</div><div class="metric-value metric-best">${global_best_ask:,.2f}</div><div class="sidebar-info">{ask_source}</div></div>', unsafe_allow_html=True)
        with m3:
            spread = global_best_ask - global_best_bid
            st.markdown(f'<div class="metric-card"><div class="metric-label">Unified Spread</div><div class="metric-value">${spread:,.2f}</div></div>', unsafe_allow_html=True)
        with m4:
            arb = best_bn_bid - best_cb_ask # Buy CB, Sell BN
            st.markdown(f'<div class="metric-card"><div class="metric-label">Arbitrage Gap</div><div class="metric-value {"arb-positive" if arb > 0 else ""}">${arb:,.2f}</div></div>', unsafe_allow_html=True)

        # Comparative Books
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="exchange-label label-coinbase">Coinbase Liquidity</div>', unsafe_allow_html=True)
            sc1, sc2 = st.columns(2)
            with sc1: st.markdown('<div class="book-container"><div class="book-title book-title-bid">Bids</div>' + render_book_table(cb_book, "bid") + '</div>', unsafe_allow_html=True)
            with sc2: st.markdown('<div class="book-container"><div class="book-title book-title-ask">Asks</div>' + render_book_table(cb_book, "ask") + '</div>', unsafe_allow_html=True)
        
        with c2:
            st.markdown('<div class="exchange-label label-binance">Binance Liquidity</div>', unsafe_allow_html=True)
            sb1, sb2 = st.columns(2)
            with sb1: st.markdown('<div class="book-container"><div class="book-title book-title-bid">Bids</div>' + render_book_table(bn_book, "bid") + '</div>', unsafe_allow_html=True)
            with sb2: st.markdown('<div class="book-container"><div class="book-title book-title-ask">Asks</div>' + render_book_table(bn_book, "ask") + '</div>', unsafe_allow_html=True)

    else:
        # Single Exchange View
        active_book = cb_book if "Coinbase" in view_mode else bn_book
        source = "COINBASE" if active_book == cb_book else "BINANCE"
        
        m1, m2, m3 = st.columns(3)
        with m1: st.metric(f"{source} Best Bid", f"${active_book.get_best_bid():,.2f}")
        with m2: st.metric(f"{source} Best Ask", f"${active_book.get_best_ask():,.2f}")
        with m3: st.metric(f"{source} Spread", f"${active_book.get_spread():,.2f}")
        
        col_b, col_a = st.columns(2)
        with col_b: st.markdown(f'<div class="book-container"><div class="book-title book-title-bid">Bids</div>' + render_book_table(active_book, "bid", 20) + '</div>', unsafe_allow_html=True)
        with col_a: st.markdown(f'<div class="book-container"><div class="book-title book-title-ask">Asks</div>' + render_book_table(active_book, "ask", 20) + '</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()

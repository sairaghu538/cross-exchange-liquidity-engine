"""
Cross-Exchange Liquidity Engine — Level 1
Real-time Coinbase Order Book Dashboard with Multi-Pair Support

Architecture:
  Background thread → asyncio event loop → WebSocket + Queue + Processor → OrderBook
  Streamlit UI → reads OrderBook state → displays top 10 bids/asks, spread, mid price
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
# Available Trading Pairs (Coinbase Advanced Trade)
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
    .sidebar-info {
        font-size: 0.72rem;
        color: #475569;
        line-height: 1.5;
        font-family: 'JetBrains Mono', monospace;
    }
    .sidebar-label {
        font-size: 0.7rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 600;
        margin-bottom: 2px;
    }
    .sidebar-value {
        font-size: 0.9rem;
        color: #e2e8f0;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
    }

    /* ── Hero Header ── */
    .hero-header {
        text-align: center;
        padding: 1.5rem 0 1rem 0;
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #60a5fa, #a78bfa, #f472b6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
        margin-bottom: 0.2rem;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: #64748b;
        letter-spacing: 2px;
        text-transform: uppercase;
        font-weight: 500;
    }

    /* ── Status Badge ── */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 16px;
        border-radius: 50px;
        font-size: 0.8rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.5px;
    }
    .status-connected {
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #10b981;
    }
    .status-disconnected {
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #ef4444;
    }
    .status-connecting {
        background: rgba(251, 191, 36, 0.12);
        border: 1px solid rgba(251, 191, 36, 0.3);
        color: #fbbf24;
    }
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    .dot-green { background: #10b981; }
    .dot-red { background: #ef4444; }
    .dot-yellow { background: #fbbf24; }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(0.8); }
    }

    /* ── Metric Cards ── */
    .metric-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 16px;
        padding: 1.2rem 1.5rem;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        border-color: rgba(99, 102, 241, 0.4);
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(99, 102, 241, 0.1);
    }
    .metric-label {
        font-size: 0.75rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        color: #e2e8f0;
    }
    .metric-value-green { color: #10b981; }
    .metric-value-blue { color: #60a5fa; }
    .metric-value-purple { color: #a78bfa; }

    /* ── Order Book Table ── */
    .book-container {
        background: rgba(15, 23, 42, 0.5);
        border: 1px solid rgba(99, 102, 241, 0.1);
        border-radius: 16px;
        padding: 1.2rem;
        backdrop-filter: blur(10px);
    }
    .book-title {
        font-size: 1rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 0.8rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(99, 102, 241, 0.1);
    }
    .book-title-bid { color: #10b981; }
    .book-title-ask { color: #ef4444; }

    table.book-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0 4px;
        font-family: 'JetBrains Mono', monospace;
    }
    table.book-table th {
        font-size: 0.7rem;
        color: #475569;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
        padding: 8px 12px;
        text-align: right;
    }
    table.book-table th:first-child { text-align: left; }
    table.book-table td {
        padding: 8px 12px;
        font-size: 0.85rem;
        font-weight: 500;
        text-align: right;
    }
    table.book-table td:first-child { text-align: left; }

    /* Bid rows */
    .bid-row td {
        background: rgba(16, 185, 129, 0.06);
        color: #10b981;
    }
    .bid-row td:first-child {
        border-radius: 8px 0 0 8px;
    }
    .bid-row td:last-child {
        border-radius: 0 8px 8px 0;
    }
    .bid-row:hover td {
        background: rgba(16, 185, 129, 0.12);
    }

    /* Ask rows */
    .ask-row td {
        background: rgba(239, 68, 68, 0.06);
        color: #ef4444;
    }
    .ask-row td:first-child {
        border-radius: 8px 0 0 8px;
    }
    .ask-row td:last-child {
        border-radius: 0 8px 8px 0;
    }
    .ask-row:hover td {
        background: rgba(239, 68, 68, 0.12);
    }

    /* ── Depth Bar ── */
    .depth-bar {
        height: 4px;
        border-radius: 2px;
        margin-top: 4px;
        transition: width 0.3s ease;
    }
    .depth-bar-bid { background: linear-gradient(90deg, transparent, #10b981); }
    .depth-bar-ask { background: linear-gradient(90deg, #ef4444, transparent); }

    /* ── Footer ── */
    .footer-text {
        text-align: center;
        color: #334155;
        font-size: 0.7rem;
        padding: 1rem 0;
        letter-spacing: 1px;
    }

    /* ── Hide Streamlit defaults ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* ── Streamlit metric overrides ── */
    [data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 16px;
        padding: 1rem 1.2rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Background Streaming Engine
# ---------------------------------------------------------------------------

def _run_async_engine(
    order_book: OrderBook,
    status_holder: dict,
    product_id: str,
    shutdown_event: threading.Event,
):
    """Run the async WebSocket + processor in a dedicated thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    queue = asyncio.Queue(maxsize=10000)
    async_shutdown = asyncio.Event()

    def on_status_change(status: str):
        status_holder["status"] = status

    async def watch_shutdown():
        """Bridge threading.Event → asyncio.Event."""
        while not shutdown_event.is_set():
            await asyncio.sleep(0.5)
        async_shutdown.set()

    async def engine():
        watcher = asyncio.create_task(watch_shutdown())
        feed_task = asyncio.create_task(
            connect_and_stream(
                queue,
                product_id=product_id,
                shutdown_event=async_shutdown,
            )
        )
        processor_task = asyncio.create_task(
            process_events(
                queue,
                order_book,
                on_status_change=on_status_change,
                shutdown_event=async_shutdown,
            )
        )

        # Wait until shutdown is signaled
        await watcher
        feed_task.cancel()
        processor_task.cancel()

        try:
            await asyncio.gather(feed_task, processor_task, return_exceptions=True)
        except Exception:
            pass

    try:
        loop.run_until_complete(engine())
    except Exception as e:
        logger.error(f"Engine thread error: {e}")
    finally:
        loop.close()
        logger.info(f"Engine thread for {product_id} stopped.")


def start_engine(product_id: str = "BTC-USD"):
    """Initialize and start the background engine. Restarts if pair changed."""
    current_pair = st.session_state.get("product_id", None)

    # If same pair is already running, do nothing
    if current_pair == product_id and "order_book" in st.session_state:
        return

    # If different pair, stop old engine first
    if current_pair and current_pair != product_id:
        _stop_engine()

    order_book = OrderBook(product_id=product_id)
    status_holder = {"status": "connecting"}
    shutdown_event = threading.Event()

    st.session_state["order_book"] = order_book
    st.session_state["status"] = status_holder
    st.session_state["product_id"] = product_id
    st.session_state["shutdown_event"] = shutdown_event

    thread = threading.Thread(
        target=_run_async_engine,
        args=(order_book, status_holder, product_id, shutdown_event),
        daemon=True,
    )
    thread.start()
    st.session_state["engine_thread"] = thread
    logger.info(f"Engine started for {product_id}")


def _stop_engine():
    """Signal the background engine to stop."""
    shutdown_event = st.session_state.get("shutdown_event")
    if shutdown_event:
        shutdown_event.set()
        logger.info("Shutdown signal sent to engine.")

    # Wait briefly for thread to finish
    thread = st.session_state.get("engine_thread")
    if thread and thread.is_alive():
        thread.join(timeout=3)

    # Clear old state
    for key in ["order_book", "status", "product_id", "shutdown_event", "engine_thread"]:
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# UI Rendering Helpers
# ---------------------------------------------------------------------------

def render_status_badge(status: str) -> str:
    """Return HTML for the connection status badge."""
    if status == "connected":
        return (
            '<span class="status-badge status-connected">'
            '<span class="status-dot dot-green"></span>CONNECTED</span>'
        )
    elif status == "disconnected":
        return (
            '<span class="status-badge status-disconnected">'
            '<span class="status-dot dot-red"></span>DISCONNECTED</span>'
        )
    else:
        return (
            '<span class="status-badge status-connecting">'
            '<span class="status-dot dot-yellow"></span>CONNECTING</span>'
        )


def render_order_table(levels: list[tuple[float, float]], side: str, max_qty: float) -> str:
    """Render an HTML table for bid or ask levels with depth bars."""
    row_class = "bid-row" if side == "bid" else "ask-row"
    bar_class = "depth-bar-bid" if side == "bid" else "depth-bar-ask"

    rows = ""
    for i, (price, qty) in enumerate(levels):
        pct = (qty / max_qty * 100) if max_qty > 0 else 0
        depth_bar = f'<div class="depth-bar {bar_class}" style="width: {pct}%"></div>'
        rows += f"""
        <tr class="{row_class}">
            <td>{i + 1}</td>
            <td>${price:,.2f}</td>
            <td>{qty:.6f}</td>
            <td>{depth_bar}</td>
        </tr>"""

    return f"""
    <table class="book-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Price</th>
                <th>Quantity</th>
                <th>Depth</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> str:
    """Render sidebar with trading pair selector. Returns selected product_id."""
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-title">⚙️ Configuration</div>',
            unsafe_allow_html=True,
        )

        # Trading pair dropdown
        selected_pair = st.selectbox(
            "Trading Pair",
            options=CRYPTO_PAIRS,
            index=CRYPTO_PAIRS.index(
                st.session_state.get("product_id", "BTC-USD")
            ) if st.session_state.get("product_id", "BTC-USD") in CRYPTO_PAIRS else 0,
            key="pair_selector",
            help="Select a cryptocurrency pair to stream the order book for.",
        )

        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        # Connection info
        status_holder = st.session_state.get("status", {})
        status = status_holder.get("status", "connecting")
        order_book = st.session_state.get("order_book")

        st.markdown(
            '<div class="sidebar-label">Connection</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="sidebar-value">{"🟢" if status == "connected" else "🔴" if status == "disconnected" else "🟡"} '
            f'{status.upper()}</div>',
            unsafe_allow_html=True,
        )

        if order_book and order_book.is_initialized:
            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

            st.markdown(
                '<div class="sidebar-label">Book Depth</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="sidebar-value">{order_book.bid_count:,} bids / '
                f'{order_book.ask_count:,} asks</div>',
                unsafe_allow_html=True,
            )

            st.markdown(
                '<div class="sidebar-label" style="margin-top: 0.5rem">Sequence</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="sidebar-value">#{order_book.sequence_num:,}</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        st.markdown(
            '<div class="sidebar-info">'
            '📡 Coinbase Advanced Trade<br>'
            '🔓 No API key required<br>'
            '🔄 Auto-refresh: 1.5s<br>'
            '📊 Channel: level2'
            '</div>',
            unsafe_allow_html=True,
        )

    return selected_pair


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

def main():
    # Auto-refresh every 1.5 seconds
    st_autorefresh(interval=1500, limit=None, key="refresh")

    # Sidebar — pair selector
    selected_pair = render_sidebar()

    # Start or switch engine based on selection
    start_engine(selected_pair)

    # Get state
    order_book: OrderBook = st.session_state.get("order_book")
    status_holder = st.session_state.get("status", {})
    status = status_holder.get("status", "connecting")
    product_id = st.session_state.get("product_id", selected_pair)

    # ── Header ──
    st.markdown("""
    <div class="hero-header">
        <div class="hero-title">📊 Liquidity Engine</div>
        <div class="hero-subtitle">Real-Time Order Book Analytics</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Status + Product Badge ──
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        badge_html = render_status_badge(status)
        st.markdown(
            f'<div style="text-align:center; margin-bottom: 1rem;">'
            f'{badge_html}'
            f'<span style="margin-left: 12px; color: #94a3b8; font-family: JetBrains Mono; '
            f'font-size: 0.85rem; font-weight: 600;">{product_id}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if not order_book or not order_book.is_initialized:
        st.markdown(
            f'<div style="text-align:center; color:#64748b; padding: 3rem; font-size: 1.1rem;">'
            f'⏳ Waiting for order book snapshot for <strong style="color:#a78bfa">'
            f'{product_id}</strong> from Coinbase...</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Metrics Row ──
    spread = order_book.get_spread()
    mid_price = order_book.get_mid_price()
    best_bid = order_book.get_best_bid()
    best_ask = order_book.get_best_ask()
    last_time = order_book.last_update_time or "—"

    # Format timestamp
    if last_time and last_time != "—":
        try:
            dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
            last_time = dt.strftime("%H:%M:%S.%f")[:-3]
        except (ValueError, AttributeError):
            pass

    m1, m2, m3, m4, m5 = st.columns(5)

    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Best Bid</div>
            <div class="metric-value metric-value-green">${best_bid:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Best Ask</div>
            <div class="metric-value" style="color: #ef4444;">${best_ask:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Spread</div>
            <div class="metric-value metric-value-blue">${spread:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Mid Price</div>
            <div class="metric-value metric-value-purple">${mid_price:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Last Update</div>
            <div class="metric-value" style="font-size: 1.1rem; color: #94a3b8;">{last_time}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ── Order Book Tables ──
    top_bids = order_book.get_top_bids(10)
    top_asks = order_book.get_top_asks(10)

    # Find max quantity for depth bar scaling
    all_qtys = [q for _, q in top_bids] + [q for _, q in top_asks]
    max_qty = max(all_qtys) if all_qtys else 1

    col_bid, col_spacer, col_ask = st.columns([5, 0.3, 5])

    with col_bid:
        st.markdown("""
        <div class="book-container">
            <div class="book-title book-title-bid">🟢 Top 10 Bids (Buy Orders)</div>
        """, unsafe_allow_html=True)
        st.markdown(render_order_table(top_bids, "bid", max_qty), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_ask:
        st.markdown("""
        <div class="book-container">
            <div class="book-title book-title-ask">🔴 Top 10 Asks (Sell Orders)</div>
        """, unsafe_allow_html=True)
        st.markdown(render_order_table(top_asks, "ask", max_qty), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Book Stats ──
    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center;">
            <div class="metric-label">Total Bid Levels</div>
            <div class="metric-value" style="font-size:1.3rem; color:#10b981;">
                {order_book.bid_count:,}
            </div>
        </div>""", unsafe_allow_html=True)
    with s2:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center;">
            <div class="metric-label">Total Ask Levels</div>
            <div class="metric-value" style="font-size:1.3rem; color:#ef4444;">
                {order_book.ask_count:,}
            </div>
        </div>""", unsafe_allow_html=True)
    with s3:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center;">
            <div class="metric-label">Sequence #</div>
            <div class="metric-value" style="font-size:1.3rem; color:#a78bfa;">
                {order_book.sequence_num:,}
            </div>
        </div>""", unsafe_allow_html=True)

    # ── Footer ──
    st.markdown(
        '<div class="footer-text">CROSS-EXCHANGE LIQUIDITY ENGINE • LEVEL 1 • COINBASE L2 FEED</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

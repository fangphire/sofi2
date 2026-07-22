from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime, date, timedelta
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import time

from backend.database import get_connection, init_db
from backend.yfin import seed_all_stocks, refresh_prices, fetch_stock_data, upsert_stock, fetch_price_history, upsert_price_history, TICKERS
from backend.models import StockFundamentals, StockPrice, PriceHistory, MarketSummary

app = FastAPI(
    title="FinPulse API",
    description="Stock market monitoring platform for Indian equities",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/dashboard")
def dashboard():
    return FileResponse("frontend/index.html")

# allow frontend to call backend from a different domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── startup ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """
    Runs once when the server starts.
    Initialises the database tables, then seeds stock data
    if the database is empty.
    """
    print("FinPulse API starting up...")
    init_db()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM stocks")
    count = cursor.fetchone()["count"]
    cursor.execute("SELECT DISTINCT ticker FROM price_history")
    history_tickers = {row["ticker"] for row in cursor.fetchall()}
    conn.close()

    if count == 0:
        print("Database empty — running initial seed...")
        seed_all_stocks()
    else:
        missing_history = [
            symbol for symbol in TICKERS
            if f"{symbol}.NS" not in history_tickers
        ]
        print(f"Database has {count} stocks")
        if missing_history:
            print(f"Backfilling price history for {len(missing_history)} stocks...")
            for symbol in missing_history:
                history = fetch_price_history(symbol)
                upsert_price_history(history)
                # Keep NSE requests comfortably below its documented throttle.
                time.sleep(1)
        else:
            print("Price history is already loaded — skipping seed")

# ─── root ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "message": "FinPulse API is running",
        "version": "1.0.0",
        "endpoints": [
            "/stocks",
            "/stocks/{ticker}",
            "/market-summary",
            "/stocks/{ticker}/history",
            "/stocks/{ticker}/refresh",
            "/sectors",
            "/docs"
        ]
    }

# ─── core endpoints (MVP) ───────────────────────────────────────────────────

@app.get("/stocks")
def get_all_stocks(
    sector: Optional[str] = None,
    min_pe: Optional[float] = None,
    max_pe: Optional[float] = None,
    min_roe: Optional[float] = None,
    sort_by: Optional[str] = "market_cap",
    order: Optional[str] = "desc"
):
    """
    Returns all tracked stocks with key metrics.
    Supports optional filtering by sector, PE range, ROE floor.
    Supports sorting by any numeric column.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT ticker, company_name, sector, industry,
               current_price, day_high, day_low,
               market_cap, pe_ratio, eps, last_updated
        FROM stocks
        WHERE 1=1
    """
    params = []

    if sector:
        query += " AND LOWER(sector) = LOWER(?)"
        params.append(sector)
    if min_pe is not None:
        query += " AND pe_ratio >= ?"
        params.append(min_pe)
    if max_pe is not None:
        query += " AND pe_ratio <= ?"
        params.append(max_pe)
    allowed_sort_columns = [
        "market_cap", "pe_ratio", "current_price"
    ]
    if sort_by in allowed_sort_columns:
        direction = "DESC" if order == "desc" else "ASC"
        query += f" ORDER BY {sort_by} {direction} NULLS LAST"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return {
        "count": len(rows),
        "stocks": [dict(row) for row in rows]
    }


@app.get("/stocks/{ticker}")
def get_stock(ticker: str):
    """
    Returns full fundamentals for a single stock.
    Ticker should include .NS suffix e.g. RELIANCE.NS
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker.upper(),))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker} not found. Make sure to include .NS suffix e.g. RELIANCE.NS"
        )

    return dict(row)


@app.get("/market-summary")
def get_market_summary():
    """
    Computed overview of all tracked stocks.
    Calculates the summary metrics supported by the available data.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total_companies,
            COUNT(DISTINCT sector) as sectors_covered,
            ROUND(AVG(pe_ratio), 2) as avg_pe_ratio,
            ROUND(SUM(market_cap) / 1e7, 2) as total_market_cap_cr
        FROM stocks
        WHERE current_price IS NOT NULL
    """)
    summary = dict(cursor.fetchone())

    # sector breakdown
    cursor.execute("""
        SELECT sector, COUNT(*) as count,
               ROUND(AVG(pe_ratio), 2) as avg_pe
        FROM stocks
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY count DESC
    """)
    sectors = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        **summary,
        "sector_breakdown": sectors,
        "last_updated": datetime.now().isoformat()
    }

# ─── bonus endpoints ─────────────────────────────────────────────────────────

@app.get("/stocks/{ticker}/history")
def get_price_history(
    ticker: str,
    period: Optional[str] = "1y"
):
    """
    Returns historical OHLCV price data for one stock.
    Period options: 1mo, 3mo, 6mo, 1y
    Powers the price chart on the dashboard.
    """
    allowed_periods = ["1mo", "3mo", "6mo", "1y"]
    if period not in allowed_periods:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period. Choose from: {allowed_periods}"
        )

    period_days = {
        "1mo": 31,
        "3mo": 92,
        "6mo": 183,
        "1y": 366,
    }
    start_date = (date.today() - timedelta(days=period_days[period])).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM price_history
        WHERE ticker = ? AND date >= ?
        ORDER BY date ASC
    """, (ticker.upper(), start_date))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No price history found for {ticker}"
        )

    return {
        "ticker": ticker,
        "period": period,
        "data_points": len(rows),
        "history": [dict(row) for row in rows]
    }


@app.get("/sectors")
def get_sectors():
    """
    Returns list of all sectors with stock count and avg metrics.
    Used to populate the sector filter dropdown on the dashboard.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            sector,
            COUNT(*) as stock_count,
            ROUND(AVG(pe_ratio), 2) as avg_pe,
            ROUND(SUM(market_cap) / 1e7, 2) as total_market_cap_cr
        FROM stocks
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY stock_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return {
        "sectors": [dict(row) for row in rows]
    }


@app.post("/stocks/{ticker}/refresh")
def refresh_single_stock(ticker: str, background_tasks: BackgroundTasks):
    """
    Triggers a fresh data fetch for one stock.
    Runs in the background so the API responds immediately.
    """
    ticker = ticker.upper()
    if ticker not in TICKERS:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker} is not in the tracked list"
        )

    def do_refresh():
        data = fetch_stock_data(ticker)
        if data:
            upsert_stock(data)
            history = fetch_price_history(ticker)
            upsert_price_history(history)
            print(f"Refreshed {ticker}")

    background_tasks.add_task(do_refresh)

    return {
        "message": f"Refresh started for {ticker}",
        "status": "processing"
    }


@app.get("/compare")
def compare_stocks(tickers: str, metrics: Optional[str] = None):
    """
    Compare multiple stocks side by side.
    tickers = comma separated e.g. ?tickers=RELIANCE.NS,TCS.NS,INFY.NS
    metrics = comma separated e.g. ?metrics=pe_ratio,eps
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",")]

    default_metrics = [
        "company_name", "sector", "current_price", "market_cap", "pe_ratio", "eps"
    ]
    metric_list = [m.strip() for m in metrics.split(",")] if metrics else default_metrics

    conn = get_connection()
    cursor = conn.cursor()

    result = {}
    for ticker in ticker_list:
        cursor.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        if row:
            row_dict = dict(row)
            result[ticker] = {m: row_dict.get(m) for m in metric_list}
        else:
            result[ticker] = {"error": "not found"}

    conn.close()

    return {
        "metrics": metric_list,
        "comparison": result
    }

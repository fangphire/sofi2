import time
from datetime import datetime, date, timedelta
from pathlib import Path
from nse import NSE
from backend.database import get_connection

TICKERS = [
    # Large cap — IT
    "TCS", "INFY", "HCLTECH", "WIPRO",
    # Large cap — Banking & Finance
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "BAJFINANCE",
    # Large cap — Consumer
    "HINDUNILVR", "NESTLEIND", "TITAN", "ASIANPAINT",
    # Mid cap — Capital Goods & Infra
    "LT", "CUMMINSIND",
    # Mid cap — Pharma
    "SUNPHARMA", "DIVISLAB",
    # Mid cap — Auto
    "MARUTI", "BAJAJFINSV",
    # Mid cap — Chemicals & Energy
    "PIDILITIND", "RELIANCE"
]

COOKIE_DIR = Path("/tmp/nse_cookies")
COOKIE_DIR.mkdir(exist_ok=True)

def fetch_stock_data(symbol):
    print(f"Fetching {symbol}...")
    try:
        with NSE(download_folder=COOKIE_DIR, server=True) as nse:
            quote = nse.quote(symbol)
            time.sleep(1)
            meta = nse.equityMetaInfo(symbol)

        meta_data  = quote.get("metaData", {})
        trade_info = quote.get("tradeInfo", {})
        price_info = quote.get("priceInfo", {})
        sec_info   = quote.get("secInfo", {})

        current_price = meta_data.get("lastPrice") or trade_info.get("lastPrice")
        pe            = float(sec_info["pdSymbolPe"]) if sec_info.get("pdSymbolPe") else None
        industry_pe   = float(sec_info["pdSectorPe"]) if sec_info.get("pdSectorPe") else None
        eps           = round(current_price / pe, 2) if current_price and pe else None

        data = {
            "ticker":                  f"{symbol}.NS",
            "company_name":            meta_data.get("companyName", symbol),
            "sector":                  sec_info.get("sector"),
            "industry":                sec_info.get("basicIndustry"),
            "current_price":           current_price,
            "day_high":                meta_data.get("dayHigh"),
            "day_low":                 meta_data.get("dayLow"),
            "fifty_two_week_high":     price_info.get("yearHigh"),
            "fifty_two_week_low":      price_info.get("yearLow"),
            "previous_close":          meta_data.get("previousClose"),
            "market_cap":              trade_info.get("totalMarketCap"),
            "pe_ratio":                pe,
            "industry_pe":             industry_pe,
            "peg_ratio":               None,
            "price_to_book":           None,
            "ev_ebitda":               None,
            "enterprise_value":        None,
            "eps":                     eps,
            "book_value_per_share":    None,
            "dividend_yield":          None,
            "face_value":              trade_info.get("faceValue"),
            "roe":                     None,
            "roce":                    None,
            "roe_3yr":                 None,
            "opm":                     None,
            "opm_last_year":           None,
            "npm":                     None,
            "npm_last_year":           None,
            "gross_margin":            None,
            "ebitda_margin":           None,
            "sales_growth":            None,
            "sales_growth_3yr":        None,
            "profit_growth":           None,
            "profit_growth_3yr":       None,
            "earnings_growth_yoy":     None,
            "revenue_growth_yoy":      None,
            "debt_to_equity":          None,
            "interest_coverage":       None,
            "current_ratio":           None,
            "quick_ratio":             None,
            "total_debt":              None,
            "cash_and_equivalents":    None,
            "promoter_holding":        None,
            "promoter_holding_change": None,
            "pledged_percentage":      None,
            "fii_holding":             None,
            "dii_holding":             None,
            "free_cashflow":           None,
            "operating_cashflow":      None,
            "analyst_target_price":    None,
            "analyst_recommendation":  None,
            "beta":                    None,
            "last_updated":            datetime.now().isoformat()
        }
        # enrich with screener.in fundamentals
        time.sleep(1)
        screener = fetch_screener_data(symbol)
        data.update({k: v for k, v in screener.items() if v is not None})

        return data

    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None

def fetch_price_history(symbol, days=365):
    """
    Fetch daily OHLCV history directly from NSE.

    The dashboard only needs daily candles, so these are stored locally after
    the initial fetch instead of requesting NSE whenever someone opens a chart.
    """
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        with NSE(download_folder=COOKIE_DIR, server=True) as nse:
            history_rows = nse.fetch_equity_historical_data(
                symbol,
                from_date=start_date,
                to_date=end_date,
                series="EQ"
            )

        if not history_rows:
            print(f"  No history returned for {symbol}")
            return []

        records = []
        for row in history_rows:
            try:
                # CH_TIMESTAMP is an ISO date in NSE's historical response.
                trade_date = date.fromisoformat(str(row["CH_TIMESTAMP"]))
                records.append({
                    "ticker":      f"{symbol}.NS",
                    "date":        trade_date.isoformat(),
                    "open_price":  round(float(row["CH_OPENING_PRICE"]), 2),
                    "high_price":  round(float(row["CH_TRADE_HIGH_PRICE"]), 2),
                    "low_price":   round(float(row["CH_TRADE_LOW_PRICE"]), 2),
                    "close_price": round(float(row["CH_CLOSING_PRICE"]), 2),
                    "volume":      int(row["CH_TOT_TRADED_QTY"])
                })
            except (KeyError, TypeError, ValueError) as row_error:
                print(f"  Skipping malformed history row for {symbol}: {row_error}")
                continue

        print(f"  Got {len(records)} days of history for {symbol}")
        return records

    except Exception as e:
        print(f"  Price history error for {symbol}: {e}")
        return []

def fetch_screener_data(symbol):
    """
    Scrapes key fundamentals from screener.in public company page.
    NSE doesn't provide ROE, ROCE, OPM, NPM, D/E — screener does.
    """
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        )
    }

    # Try consolidated page first, then standalone
    for url in [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]:
        try:
            r = requests.get(url, headers=headers, timeout=10)

            if r.status_code == 200 and "top-ratios" in r.text:
                break

        except Exception:
            continue
    else:
        print(f"  Screener: no page found for {symbol}")
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    ratios = {}

    top = soup.find("ul", id="top-ratios")
    if top:
        for li in top.find_all("li"):
            name_tag = li.find("span", class_="name")
            value_tag = li.find("span", class_="value")

            if name_tag and value_tag:
                key = name_tag.get_text(strip=True)
                val = (
                    value_tag.get_text(strip=True)
                    .replace(",", "")
                    .replace("%", "")
                    .replace("₹", "")
                    .strip()
                )
                ratios[key] = val

    def to_float(val):
        try:
            if val in (None, "", "—", "-"):
                return None
            return float(val)
        except Exception:
            return None

    return {
        "roe": to_float(ratios.get("ROE")),
        "roce": to_float(ratios.get("ROCE")),
        "pe_ratio": to_float(ratios.get("Stock P/E")),
        "dividend_yield": to_float(ratios.get("Dividend Yield")),
        "book_value_per_share": to_float(ratios.get("Book Value")),
        "opm": None,
        "debt_to_equity": None,
        "ev_ebitda": None,
        "sales_growth": None,
        "profit_growth": None,
    }


def upsert_stock(data):
    conn = get_connection()
    cursor = conn.cursor()
    columns      = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    cursor.execute(f"""
        INSERT OR REPLACE INTO stocks ({columns})
        VALUES ({placeholders})
    """, list(data.values()))
    conn.commit()
    conn.close()

def upsert_price_history(records):
    if not records:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR IGNORE INTO price_history
        (ticker, date, open_price, high_price, low_price, close_price, volume)
        VALUES (:ticker, :date, :open_price, :high_price, :low_price, :close_price, :volume)
    """, records)
    conn.commit()
    conn.close()

def seed_all_stocks():
    print(f"Seeding {len(TICKERS)} stocks...")
    success = 0
    failed  = []

    for symbol in TICKERS:
        data = fetch_stock_data(symbol)
        if data:
            upsert_stock(data)
            history = fetch_price_history(symbol)
            upsert_price_history(history)
            success += 1
            print(f"  ✓ {symbol} — {data['company_name']}")
        else:
            failed.append(symbol)
        time.sleep(1)

    print(f"Seeding complete: {success}/{len(TICKERS)} loaded")
    if failed:
        print(f"Failed: {failed}")

def refresh_prices():
    for symbol in TICKERS:
        data = fetch_stock_data(symbol)
        if data:
            upsert_stock(data)
        time.sleep(1)

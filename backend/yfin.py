import time
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from nse import NSE
from backend.database import get_connection

# lxml is faster but optional — fall back to the stdlib html.parser if missing
try:
    import lxml  # noqa: F401
    _lxml_available = True
except ImportError:
    _lxml_available = False

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
        # Quarterly results + promoter holding from NSE (free, no rate limit issues)
        data.update(fetch_nse_fundamentals(symbol))

        # Valuation ratios not published by NSE — scraped from screener.in.
        # fetch_screener_data never raises; it returns {} on any failure.
        # We sleep briefly before the request to stay well below screener's
        # informal throttle (they don't publish a limit, but 1–2 req/sec is safe).
        time.sleep(1)
        screener_data = fetch_screener_data(symbol)
        # Only overwrite fields that screener found — don't clobber NSE values
        for key, value in screener_data.items():
            if value is not None:
                data[key] = value

        return data

    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None


def fetch_nse_fundamentals(symbol):
    """Fetch free quarterly growth and promoter-holding data from NSE."""
    try:
        with NSE(download_folder=COOKIE_DIR, server=True) as nse:
            comparison = nse.results_comparison(symbol)
            # NSE documents a three-request-per-second throttle.
            time.sleep(0.5)
            shareholding_rows = nse.shareholding(symbol)
    except Exception as e:
        print(f"  NSE fundamentals unavailable for {symbol}: {e}")
        return {}

    def number(value):
        if value in (None, "", "-", "—"):
            return None
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def nse_date(value):
        if not value:
            return None
        value = str(value).split()[0]
        for date_format in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
        return None

    result_rows = comparison.get("resCmpData", []) if isinstance(comparison, dict) else []
    quarters = []
    for row in result_rows:
        report_date = nse_date(row.get("re_to_dt"))
        if report_date:
            quarters.append({
                "date": report_date,
                "revenue": number(row.get("re_total_inc")),
                "profit": number(row.get("re_net_profit")),
            })

    quarters.sort(key=lambda row: row["date"], reverse=True)

    def yoy_growth(metric):
        if not quarters:
            return None
        latest = quarters[0]
        current = latest[metric]
        if current is None:
            return None
        try:
            prior_year_date = latest["date"].replace(year=latest["date"].year - 1)
        except ValueError:  # 29 February
            prior_year_date = latest["date"].replace(year=latest["date"].year - 1, day=28)
        candidates = [row for row in quarters if row[metric] is not None]
        if not candidates:
            return None
        prior = min(candidates, key=lambda row: abs((row["date"] - prior_year_date).days))
        if abs((prior["date"] - prior_year_date).days) > 45 or prior[metric] == 0:
            return None
        return round(((current / prior[metric]) - 1) * 100, 2)

    holdings = []
    for row in shareholding_rows if isinstance(shareholding_rows, list) else []:
        report_date = nse_date(row.get("date"))
        holding = number(row.get("pr_and_prgrp"))
        if report_date and holding is not None:
            holdings.append((report_date, holding))
    holdings.sort(reverse=True)

    promoter_holding = holdings[0][1] if holdings else None
    promoter_change = (
        round(holdings[0][1] - holdings[1][1], 2)
        if len(holdings) > 1 else None
    )
    revenue_yoy = yoy_growth("revenue")
    profit_yoy = yoy_growth("profit")

    return {
        "sales_growth": revenue_yoy,
        "revenue_growth_yoy": revenue_yoy,
        "profit_growth": profit_yoy,
        "earnings_growth_yoy": profit_yoy,
        "promoter_holding": promoter_holding,
        "promoter_holding_change": promoter_change,
    }

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

        def read_value(row, *keys):
            """Return the first populated field from NSE's versioned responses."""
            for key in keys:
                value = row.get(key)
                if value not in (None, ""):
                    return value
            raise KeyError(" / ".join(keys))

        def parse_trade_date(value):
            value = str(value)
            # Current NSE responses use mTIMESTAMP (e.g. 01-Apr-2025); some
            # versions expose CH_TIMESTAMP (e.g. 2025-04-01) instead.
            # ISO dates may be followed by a time; NSE's display date is 11 chars.
            date_portion = value[:10] if len(value) > 4 and value[4] == "-" else value[:11]
            for date_format in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(date_portion, date_format).date()
                except ValueError:
                    continue
            raise ValueError(f"Unrecognised NSE trade date: {value}")

        records = []
        skipped_rows = 0
        for row in history_rows:
            try:
                trade_date = parse_trade_date(read_value(
                    row, "mtimestamp", "mTIMESTAMP", "CH_TIMESTAMP", "TIMESTAMP", "date"
                ))
                records.append({
                    "ticker":      f"{symbol}.NS",
                    "date":        trade_date.isoformat(),
                    "open_price":  round(float(read_value(row, "chOpeningPrice", "CH_OPENING_PRICE", "open")), 2),
                    "high_price":  round(float(read_value(row, "chTradeHighPrice", "CH_TRADE_HIGH_PRICE", "high")), 2),
                    "low_price":   round(float(read_value(row, "chTradeLowPrice", "CH_TRADE_LOW_PRICE", "low")), 2),
                    "close_price": round(float(read_value(row, "chClosingPrice", "CH_CLOSING_PRICE", "close")), 2),
                    "volume":      int(float(read_value(row, "chTotTradedQty", "CH_TOT_TRADED_QTY", "volume")))
                })
            except (KeyError, TypeError, ValueError) as row_error:
                skipped_rows += 1
                if skipped_rows == 1:
                    print(
                        f"  Skipping malformed history rows for {symbol}: {row_error}. "
                        f"Available fields: {', '.join(row.keys())}"
                    )
                continue

        if skipped_rows:
            print(f"  Skipped {skipped_rows} malformed history rows for {symbol}")
        print(f"  Got {len(records)} days of history for {symbol}")
        return records

    except Exception as e:
        print(f"  Price history error for {symbol}: {e}")
        return []

def fetch_screener_data(symbol):
    """
    Scrapes key fundamentals from screener.in public company page.
    NSE doesn't provide ROE, ROCE, OPM, D/E, EV/EBITDA — screener does.

    Tries consolidated view first, falls back to standalone.
    Returns a dict of floats ready to merge into the stock record.
    Never raises — returns {} on any failure so the rest of the pipeline continues.
    """
    import requests
    from bs4 import BeautifulSoup

    # Rotate a couple of common UA strings to reduce 403s
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    response = None
    for url in [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200 and "top-ratios" in r.text:
                response = r
                break
            # 404 → standalone might still work; anything else is a hard failure
        except requests.exceptions.Timeout:
            print(f"  Screener: timeout for {symbol}, skipping")
            return {}
        except Exception as exc:
            print(f"  Screener: request error for {symbol}: {exc}")
            return {}

    if response is None:
        print(f"  Screener: no usable page for {symbol}")
        return {}

    soup = BeautifulSoup(response.text, "lxml" if _lxml_available else "html.parser")

    # ── parse #top-ratios ────────────────────────────────────────────────────
    # Each <li> looks like:
    #   <li>
    #     <span class="name">ROE <span class="sub">#</span></span>
    #     <span class="number">%<span class="value">15.23</span></span>
    #   </li>
    # Some older layouts put the number directly in a <span class="value">.

    raw: dict[str, str] = {}

    top = soup.find("ul", id="top-ratios")
    if top:
        for li in top.find_all("li"):
            name_tag = li.find("span", class_="name")
            if not name_tag:
                continue
            # The name may have a nested <span class="sub"> — ignore it
            label = name_tag.get_text(" ", strip=True).split("#")[0].strip()

            # Try <span class="value"> first, then the whole number span
            value_tag = li.find("span", class_="value") or li.find("span", class_="number")
            if not value_tag:
                continue

            val = (
                value_tag.get_text(strip=True)
                .replace(",", "")
                .replace("%", "")
                .replace("₹", "")
                .replace("Cr.", "")
                .replace("Cr", "")
                .strip()
            )
            raw[label] = val

    def to_float(val: str | None) -> float | None:
        if val in (None, "", "—", "-", "N/A"):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    # ── key label mappings (screener uses different spellings occasionally) ──
    def pick(*labels) -> float | None:
        for label in labels:
            v = to_float(raw.get(label))
            if v is not None:
                return v
        return None

    # ── parse the 10-year P&L table for OPM if top-ratios misses it ─────────
    # Screener puts current-year OPM in the P&L table under "OPM %"
    opm_from_table: float | None = None
    try:
        pl_section = soup.find("section", id="profit-loss")
        if pl_section:
            rows = pl_section.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if not cells:
                    continue
                row_label = cells[0].get_text(strip=True)
                if "OPM" in row_label or "Operating Profit Margin" in row_label:
                    # Last non-empty cell is TTM / most recent
                    values = [
                        c.get_text(strip=True).replace("%", "").replace(",", "").strip()
                        for c in cells[1:]
                        if c.get_text(strip=True) not in ("", "—", "-")
                    ]
                    if values:
                        opm_from_table = to_float(values[-1])
                    break
    except Exception:
        pass

    result = {
        # valuation
        "pe_ratio":           pick("Stock P/E", "P/E"),
        "price_to_book":      pick("Price to Book", "Price to book value", "P/B"),
        "ev_ebitda":          pick("EV/EBITDA", "EV / EBITDA"),
        # profitability
        "roe":                pick("ROE", "Return on Equity"),
        "roce":               pick("ROCE", "Return on Capital Employed"),
        "opm":                pick("OPM", "Operating Profit Margin") or opm_from_table,
        # per-share / income
        "dividend_yield":     pick("Dividend Yield"),
        "book_value_per_share": pick("Book Value"),
        # leverage
        "debt_to_equity":     pick("Debt to Equity", "Debt / Equity"),
    }

    # Log what we got so failures are easy to diagnose
    found = [k for k, v in result.items() if v is not None]
    missing = [k for k, v in result.items() if v is None]
    print(f"  Screener {symbol}: got {found}" + (f" | missing {missing}" if missing else ""))

    return result


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

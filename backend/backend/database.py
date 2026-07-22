import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "stocks.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            -- identification
            ticker TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            sector TEXT,
            industry TEXT,

            -- price data
            current_price REAL,
            day_high REAL,
            day_low REAL,
            fifty_two_week_high REAL,
            fifty_two_week_low REAL,
            previous_close REAL,

            -- valuation ratios
            market_cap REAL,
            pe_ratio REAL,
            industry_pe REAL,
            peg_ratio REAL,
            price_to_book REAL,
            ev_ebitda REAL,
            enterprise_value REAL,

            -- per share data
            eps REAL,
            book_value_per_share REAL,
            dividend_yield REAL,
            face_value REAL,

            -- profitability
            roe REAL,
            roce REAL,
            roe_3yr REAL,
            opm REAL,
            opm_last_year REAL,
            npm REAL,
            npm_last_year REAL,
            gross_margin REAL,
            ebitda_margin REAL,

            -- growth metrics
            sales_growth REAL,
            sales_growth_3yr REAL,
            profit_growth REAL,
            profit_growth_3yr REAL,
            earnings_growth_yoy REAL,
            revenue_growth_yoy REAL,

            -- leverage and liquidity
            debt_to_equity REAL,
            interest_coverage REAL,
            current_ratio REAL,
            quick_ratio REAL,
            total_debt REAL,
            cash_and_equivalents REAL,

            -- ownership (sourced from NSE/screener.in)
            promoter_holding REAL,
            promoter_holding_change REAL,
            pledged_percentage REAL,
            fii_holding REAL,
            dii_holding REAL,

            -- cash flow
            free_cashflow REAL,
            operating_cashflow REAL,

            -- analyst data
            analyst_target_price REAL,
            analyst_recommendation TEXT,
            beta REAL,

            -- metadata
            last_updated TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL,
            volume INTEGER,
            FOREIGN KEY (ticker) REFERENCES stocks (ticker),
            UNIQUE(ticker, date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ownership_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            promoter_holding REAL,
            fii_holding REAL,
            dii_holding REAL,
            public_holding REAL,
            pledged_percentage REAL,
            FOREIGN KEY (ticker) REFERENCES stocks (ticker),
            UNIQUE(ticker, quarter)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fundamentals_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            fiscal_year TEXT NOT NULL,
            revenue REAL,
            net_profit REAL,
            ebitda REAL,
            eps REAL,
            roe REAL,
            roce REAL,
            debt_to_equity REAL,
            opm REAL,
            npm REAL,
            FOREIGN KEY (ticker) REFERENCES stocks (ticker),
            UNIQUE(ticker, fiscal_year)
        )
    """)
    
    # clean up any bad history rows with empty dates
    cursor.execute("DELETE FROM price_history WHERE date = '' OR date IS NULL")

    conn.commit()
    conn.close()
    print("Database initialised successfully")



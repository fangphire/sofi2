from pydantic import BaseModel
from typing import Optional

class StockBase(BaseModel):
    ticker: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None

class StockPrice(BaseModel):
    ticker: str
    company_name: str
    current_price: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    previous_close: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    market_cap: Optional[float] = None
    last_updated: Optional[str] = None

class StockFundamentals(BaseModel):
    ticker: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None

    # price
    current_price: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    previous_close: Optional[float] = None

    # valuation
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    industry_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    ev_ebitda: Optional[float] = None
    enterprise_value: Optional[float] = None

    # per share
    eps: Optional[float] = None
    book_value_per_share: Optional[float] = None
    dividend_yield: Optional[float] = None

    # profitability
    roe: Optional[float] = None
    roce: Optional[float] = None
    roe_3yr: Optional[float] = None
    opm: Optional[float] = None
    opm_last_year: Optional[float] = None
    npm: Optional[float] = None
    npm_last_year: Optional[float] = None
    gross_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None

    # growth
    sales_growth: Optional[float] = None
    sales_growth_3yr: Optional[float] = None
    profit_growth: Optional[float] = None
    profit_growth_3yr: Optional[float] = None

    # leverage
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None

    # ownership
    promoter_holding: Optional[float] = None
    promoter_holding_change: Optional[float] = None
    pledged_percentage: Optional[float] = None
    fii_holding: Optional[float] = None
    dii_holding: Optional[float] = None

    # cashflow
    free_cashflow: Optional[float] = None
    operating_cashflow: Optional[float] = None

    # analyst
    analyst_target_price: Optional[float] = None
    analyst_recommendation: Optional[str] = None
    beta: Optional[float] = None

    last_updated: Optional[str] = None

    class Config:
        from_attributes = True

class PriceHistory(BaseModel):
    ticker: str
    date: str
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    volume: Optional[int] = None

class MarketSummary(BaseModel):
    total_companies: int
    sectors_covered: int
    avg_pe_ratio: Optional[float] = None
    avg_roe: Optional[float] = None
    avg_roce: Optional[float] = None
    total_market_cap_cr: Optional[float] = None
    top_gainer: Optional[str] = None
    top_loser: Optional[str] = None
    last_updated: Optional[str] = None

class StockComparison(BaseModel):
    tickers: list[str]
    metrics: list[str]
    data: dict

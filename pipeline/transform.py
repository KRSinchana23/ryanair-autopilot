"""
pipeline/transform.py
Cleans and structures raw yfinance data into typed, validated models.
Uses Pydantic for data validation - production mindset.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime


# Typed Models (Pydantic)

class CompanyProfile(BaseModel):
    name: str
    ticker: str
    sector: str
    industry: str
    country: str
    website: str
    description: str
    currency: str
    exchange: str
    fetched_at: str


class MarketData(BaseModel):
    current_price: Optional[float] = None
    market_cap_eur_bn: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    shares_outstanding: Optional[float] = None
    analyst_target_price: Optional[float] = None
    analyst_recommendation: Optional[float] = None  # 1=strong buy, 5=sell
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    price_to_book: Optional[float] = None


class IncomeMetrics(BaseModel):
    """Key P&L metrics extracted from income statement."""
    total_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    earnings_growth_pct: Optional[float] = None


class BalanceMetrics(BaseModel):
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    total_cash: Optional[float] = None
    net_debt: Optional[float] = None
    book_value_per_share: Optional[float] = None
    return_on_equity_pct: Optional[float] = None


class StructuredCompanyData(BaseModel):
    profile: CompanyProfile
    market: MarketData
    income: IncomeMetrics
    balance: BalanceMetrics
    price_history: Dict[str, float] = Field(default_factory=dict)
    analyst_recommendations: List[Dict] = Field(default_factory=list)


# Transform Functions

def safe_float(value, divisor=1) -> Optional[float]:
    """Safely convert to float, return None on failure."""
    try:
        if value is None:
            return None
        return round(float(value) / divisor, 4)
    except (TypeError, ValueError):
        return None


def safe_pct(value) -> Optional[float]:
    """Convert decimal ratio to percentage."""
    try:
        if value is None:
            return None
        return round(float(value) * 100, 2)
    except (TypeError, ValueError):
        return None


def transform(raw: dict) -> StructuredCompanyData:
    """
    Transform raw ingest data into clean, validated StructuredCompanyData.
    This is the T in ingest → Transform → validate → output.
    """
    print("[TRANSFORM] Structuring raw data...")

    info = raw.get("info", {})
    market_cap = info.get("marketCap")

    profile = CompanyProfile(
        name=info.get("longName", "Ryanair Holdings PLC"),
        ticker=raw.get("ticker", "RYA.L"),
        sector=info.get("sector", "Industrials"),
        industry=info.get("industry", "Airlines"),
        country=info.get("country", "Ireland"),
        website=info.get("website", "https://www.ryanair.com"),
        description=info.get("longBusinessSummary", "Europe's largest ultra-low-cost carrier."),
        currency=info.get("currency", "GBp"),
        exchange=info.get("exchange", "LSE"),
        fetched_at=raw.get("fetched_at", datetime.now().isoformat()),
    )

    market = MarketData(
        current_price=safe_float(info.get("currentPrice")),
        market_cap_eur_bn=safe_float(market_cap, divisor=1_000_000_000),
        fifty_two_week_high=safe_float(info.get("fiftyTwoWeekHigh")),
        fifty_two_week_low=safe_float(info.get("fiftyTwoWeekLow")),
        shares_outstanding=safe_float(info.get("sharesOutstanding")),
        analyst_target_price=safe_float(info.get("targetMeanPrice")),
        analyst_recommendation=safe_float(info.get("recommendationMean")),
        trailing_pe=safe_float(info.get("trailingPE")),
        forward_pe=safe_float(info.get("forwardPE")),
        price_to_book=safe_float(info.get("priceToBook")),
    )

    income = IncomeMetrics(
        total_revenue=safe_float(info.get("totalRevenue")),
        ebitda=safe_float(info.get("ebitda")),
        operating_margin_pct=safe_pct(info.get("operatingMargins")),
        net_margin_pct=safe_pct(info.get("profitMargins")),
        revenue_growth_pct=safe_pct(info.get("revenueGrowth")),
        earnings_growth_pct=safe_pct(info.get("earningsGrowth")),
    )

    total_debt = safe_float(info.get("totalDebt"))
    total_cash = safe_float(info.get("totalCash"))
    net_debt = None
    if total_debt is not None and total_cash is not None:
        net_debt = round(total_debt - total_cash, 2)

    balance = BalanceMetrics(
        total_debt=total_debt,
        total_cash=total_cash,
        net_debt=net_debt,
        book_value_per_share=safe_float(info.get("bookValue")),
        return_on_equity_pct=safe_pct(info.get("returnOnEquity")),
    )

    structured = StructuredCompanyData(
        profile=profile,
        market=market,
        income=income,
        balance=balance,
        price_history=raw.get("price_history", {}),
        analyst_recommendations=raw.get("analyst_recommendations", []),
    )

    print(f"[TRANSFORM] Data structured for {profile.name}")
    return structured


if __name__ == "__main__":
    from pipeline.ingest import load_cached_data
    raw = load_cached_data()
    data = transform(raw)
    print(data.model_dump_json(indent=2))

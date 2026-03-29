"""
pipeline/ingest.py
Pulls Ryanair financial data from public sources using yfinance.
All data is publicly available - no scraping violations.
"""

import yfinance as yf
import json
import os
from datetime import datetime
from typing import Dict, Any


TICKER = "RYA.L"  # Ryanair on London Stock Exchange
DATA_CACHE_PATH = "data/ryanair_raw.json"


def fetch_ryanair_data() -> Dict[str, Any]:
    """
    Ingest all publicly available Ryanair financial data.
    Uses yfinance which wraps Yahoo Finance's public API.
    Returns a structured dict ready for transformation.
    """
    print("[INGEST] Fetching Ryanair data from Yahoo Finance...")

    ticker = yf.Ticker(TICKER)

    #  Core financials
    try:
        income_stmt = ticker.financials
        income_dict = income_stmt.to_dict() if income_stmt is not None and not income_stmt.empty else {}
        # Convert datetime keys to strings for JSON serialisation
        income_dict = {str(k): v for k, v in income_dict.items()}
    except Exception as e:
        print(f"  [WARN] Income statement failed: {e}")
        income_dict = {}

    try:
        balance = ticker.balance_sheet
        balance_dict = balance.to_dict() if balance is not None and not balance.empty else {}
        balance_dict = {str(k): v for k, v in balance_dict.items()}
    except Exception as e:
        print(f"  [WARN] Balance sheet failed: {e}")
        balance_dict = {}

    try:
        cashflow = ticker.cashflow
        cashflow_dict = cashflow.to_dict() if cashflow is not None and not cashflow.empty else {}
        cashflow_dict = {str(k): v for k, v in cashflow_dict.items()}
    except Exception as e:
        print(f"  [WARN] Cashflow failed: {e}")
        cashflow_dict = {}

    # --- Stock price history (5 years) ---
    try:
        history = ticker.history(period="5y")
        history_dict = history["Close"].tail(60).to_dict()
        history_dict = {str(k): float(v) for k, v in history_dict.items()}
    except Exception as e:
        print(f"  [WARN] Price history failed: {e}")
        history_dict = {}

    # --- Company info/metadata ---
    try:
        info = ticker.info
        # Only keep serialisable fields we care about
        safe_info = {
            "longName": info.get("longName", "Ryanair Holdings PLC"),
            "sector": info.get("sector", "Industrials"),
            "industry": info.get("industry", "Airlines"),
            "country": info.get("country", "Ireland"),
            "website": info.get("website", "https://www.ryanair.com"),
            "longBusinessSummary": info.get("longBusinessSummary", ""),
            "marketCap": info.get("marketCap"),
            "totalRevenue": info.get("totalRevenue"),
            "ebitda": info.get("ebitda"),
            "totalDebt": info.get("totalDebt"),
            "totalCash": info.get("totalCash"),
            "operatingMargins": info.get("operatingMargins"),
            "profitMargins": info.get("profitMargins"),
            "returnOnEquity": info.get("returnOnEquity"),
            "currentPrice": info.get("currentPrice"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "recommendationMean": info.get("recommendationMean"),
            "currency": info.get("currency", "GBp"),
            "exchange": info.get("exchange", "LSE"),
            "sharesOutstanding": info.get("sharesOutstanding"),
            "bookValue": info.get("bookValue"),
            "priceToBook": info.get("priceToBook"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "earningsGrowth": info.get("earningsGrowth"),
            "revenueGrowth": info.get("revenueGrowth"),
        }
    except Exception as e:
        print(f"  [WARN] Company info failed: {e}")
        safe_info = {"longName": "Ryanair Holdings PLC"}

    # --- Analyst recommendations ---
    try:
        recs = ticker.recommendations
        if recs is not None and not recs.empty:
            latest_recs = recs.tail(5).to_dict(orient="records")
            recs_list = [{str(k): v for k, v in r.items()} for r in latest_recs]
        else:
            recs_list = []
    except Exception as e:
        print(f"  [WARN] Recommendations failed: {e}")
        recs_list = []

    raw_data = {
        "fetched_at": datetime.now().isoformat(),
        "ticker": TICKER,
        "info": safe_info,
        "income_statement": income_dict,
        "balance_sheet": balance_dict,
        "cashflow": cashflow_dict,
        "price_history": history_dict,
        "analyst_recommendations": recs_list,
    }

    # Cache to disk so we don't hammer the API repeatedly
    os.makedirs("data", exist_ok=True)
    with open(DATA_CACHE_PATH, "w") as f:
        json.dump(raw_data, f, indent=2, default=str)

    print(f"[INGEST] Data fetched and cached to {DATA_CACHE_PATH}")
    return raw_data


def load_cached_data() -> Dict[str, Any]:
    """Load from cache if available, otherwise fetch fresh."""
    if os.path.exists(DATA_CACHE_PATH):
        print("[INGEST] Loading from cache...")
        with open(DATA_CACHE_PATH, "r") as f:
            return json.load(f)
    return fetch_ryanair_data()


if __name__ == "__main__":
    data = fetch_ryanair_data()
    print(f"Keys available: {list(data.keys())}")
    print(f"Company: {data['info'].get('longName')}")
    print(f"Market Cap: {data['info'].get('marketCap')}")

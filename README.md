# Ryanair Corporate Finance Autopilot

An AI-powered corporate finance analysis pipeline built for the Assiduous Hackathon 2025.

> ⚠️ **Disclaimer:** This tool is for educational purposes only. All outputs are NOT investment advice. Data sourced from publicly available sources. Label all uncertainty and cite sources.

---

## What It Does

Picks up **Ryanair Holdings PLC (RYA.L)** and automatically:

1. **Ingests** public financial data (Yahoo Finance via `yfinance`)
2. **Transforms & validates** it into typed Pydantic models
3. **Builds a 3-scenario financial model** (Base / Upside / Downside) with linked formulas
4. **Runs a multi-step AI agent** (Claude) that gathers data, reasons about it, and writes sections
5. **Generates outputs:** Excel financial model + PDF shareholder report

---

## How to Run (3 steps)

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd ryanair-autopilot

# 2. Add your Anthropic API key
cp .env.example .env
# Edit .env and paste your key: ANTHROPIC_API_KEY=sk-ant-...

# 3. Run it
bash run.sh
```

Then open **http://localhost:8000** in your browser and click **Run Pipeline**.

---

## Architecture

```
[yfinance API]
     │
     ▼
pipeline/ingest.py       ← Fetches & caches raw financial data
     │
     ▼
pipeline/transform.py    ← Cleans data, validates with Pydantic models
     │
     ▼
pipeline/financial_model.py  ← 3-scenario model (linked formulas)
     │
     ▼
pipeline/agent.py        ← Multi-step Claude agent with tool-calling
     │                      (observable: every step is logged)
     ▼
outputs/report_generator.py  ← Excel (openpyxl) + PDF (reportlab)
     │
     ▼
main.py (FastAPI)        ← REST API + Web dashboard
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web dashboard |
| POST | `/analyze` | Run the full pipeline |
| GET | `/status` | Pipeline status + current step |
| GET | `/scenarios` | Get financial model scenario results |
| GET | `/download/excel` | Download Excel financial model |
| GET | `/download/pdf` | Download PDF report |
| GET | `/download/summary` | Download JSON pipeline summary |
| GET | `/health` | Health check |

---

## Financial Model

Three scenarios built on Ryanair's key operational drivers:

| Driver | Base | Upside | Downside |
|--------|------|--------|----------|
| Passenger Growth | +5% | +12% | -3% |
| Fuel Cost Change | 0% | -10% | +20% |
| Yield (Rev/Pax) | +2% | +5% | -3% |

All formulas are linked and transparent — no hardcoded outputs.

---

## AI Agent (Observable)

The agent uses Claude with **tool-calling** — not a single opaque prompt. Steps:

1. `get_company_profile` → fetch company info
2. `get_market_data` → price, PE, analyst targets
3. `get_financial_metrics` → revenue, margins, debt
4. `get_scenario(base/upside/downside)` → model projections
5. `calculate_valuation` → EV/EBITDA implied range
6. `generate_section(×6)` → AI writes each report section

Every tool call is logged. The `/status` endpoint returns the full trace.

---

## Tech Stack

| Library | Why |
|---------|-----|
| `FastAPI` | Fast async API, auto docs, production-ready |
| `yfinance` | Free public Yahoo Finance data (no scraping) |
| `pydantic` | Data validation and typed models |
| `anthropic` | Claude API for AI agent with tool-calling |
| `openpyxl` | Excel generation without needing Excel installed |
| `reportlab` | PDF generation, open source |
| `pandas` | Data manipulation for financial timeseries |

---

## Data Sources

- **Yahoo Finance** (via `yfinance`) — stock prices, financials, balance sheet
- **Ryanair Investor Relations** (public) — operational stats reference
- All sources are publicly available. No authentication or scraping violations.

---

## Limitations

- `yfinance` data can lag by 24-48 hours for some metrics
- Ryanair reports in EUR; Yahoo Finance may return GBp for LSE listing — converted where possible
- Financial model uses simplified driver-based approach (not a full DCF)
- AI-generated text sections may contain errors — always verify independently
- Valuation output is a rough range only, not a price target

---

## What I'd Do With Another Week

1. Add SEC EDGAR / Euronext direct filing parser for more reliable data
2. Build a full DCF model (WACC, terminal value)
3. Add competitor comparison (easyJet, Wizz Air)
4. Deploy to Railway/Fly.io with persistent storage
5. Add evaluation layer to score AI output quality
6. Real-time streaming of agent steps via Server-Sent Events

---

## Prompts Used (Hackathon Transparency)

- Claude (claude.ai) used to help architect the multi-step agent pattern
- Prompt for agent system: "Work through steps IN ORDER using tools. Be thorough. Label uncertainty."
- Section generation prompts are in `pipeline/agent.py` → `execute_tool()` → `generate_section`

---

*Assiduous Hackathon 2025 — Solo submission — Educational purposes only*

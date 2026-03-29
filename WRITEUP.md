# One-Page Write-Up: Ryanair Corporate Finance Autopilot

## Problem

Manual corporate finance analysis is slow, expensive, and inconsistent. Analysts spend hours gathering data from scattered sources, building models in Excel, and writing reports — work that could be partially automated using modern AI and open-source tooling.

## Approach

I built a **5-stage pipeline** that automatically analyses Ryanair (RYA.L) using publicly available data:

1. **Ingest** — `yfinance` pulls stock data, financials, balance sheet from Yahoo Finance's public API. Data is cached to avoid hammering the API.

2. **Transform** — Raw dicts are validated into typed `Pydantic` models (`StructuredCompanyData`). Every field is explicitly typed. Validation errors surface early rather than silently corrupting outputs.

3. **Financial Model** — A 3-scenario model (Base / Upside / Downside) built on Ryanair's key operational drivers: passenger growth, fuel cost delta, revenue per passenger (yield). All formulas are linked — change an assumption and everything flows through.

4. **AI Agent** — A multi-step `Claude` agent with 6 tools (`get_company_profile`, `get_market_data`, `get_financial_metrics`, `get_scenario`, `calculate_valuation`, `generate_section`). The agent is **not** one opaque prompt — every tool call is logged and returned in the API response so judges can trace every step.

5. **Outputs** — `openpyxl` generates a colour-coded, formula-linked Excel model. `reportlab` generates a professional PDF shareholder report. Both are downloadable from the web dashboard.

## Trade-offs

| Decision | Trade-off |
|----------|-----------|
| `yfinance` for data | Free and legal, but can lag 24-48h and currency inconsistencies (GBp vs EUR) require handling |
| Driver-based financial model vs DCF | Faster to build and easier to inspect; a full DCF would need WACC assumptions that are harder to source reliably |
| FastAPI + background tasks | Simple to run locally; for production I'd use Celery + Redis for the pipeline queue |
| Single company (Ryanair) | Depth over breadth; the pipeline is company-agnostic and could be extended |

## What I'd Do With Another Week

1. **SEC EDGAR / Euronext API** for structured filing data (more reliable than Yahoo Finance)
2. **Full DCF model** with WACC, terminal value, sensitivity tables
3. **Competitor benchmarking** (easyJet, Wizz Air, IAG)
4. **Output evaluation layer** — score AI-written sections against source data for factual accuracy
5. **Deploy to Fly.io** with persistent storage and a job queue
6. **Streaming agent trace** via Server-Sent Events so users see the agent reasoning in real-time

## AI Tools Used

- **Claude (claude.ai)** — Used to help architect the multi-step agent pattern and review code structure
- **Anthropic Python SDK** — For the tool-calling agent loop in `pipeline/agent.py`
- All prompts used are visible in the source code

## Key Prompts (Transparency)

Agent system prompt (in `pipeline/agent.py`):
> "Work through these steps IN ORDER using the available tools... Be thorough and use ALL tools. Always label uncertainty. This is educational only, not investment advice."

Section generation prompt structure (in `execute_tool` → `generate_section`):
> "You are a senior equity research analyst... Be specific with numbers where provided. Label all uncertainty clearly. Do not present guesses as facts."

---

*Assiduous Hackathon 2025 | Educational purposes only | Not investment advice*

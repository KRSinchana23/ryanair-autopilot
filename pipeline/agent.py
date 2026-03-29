"""
pipeline/agent.py
Multi-step AI agent using Claude with tool-calling.
Every step is logged so judges can see the agent reasoning.
This is the key differentiator - NOT a single opaque prompt.
"""

import json
import os
from typing import Dict, Any, List
from datetime import datetime
import anthropic
from pipeline.transform import StructuredCompanyData
from pipeline.financial_model import FinancialModel


#  Tool Definitions
# These tell Claude what actions it can take

TOOLS = [
    {
        "name": "get_company_profile",
        "description": "Get Ryanair's company profile, sector, and business description.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_market_data",
        "description": "Get current market data: price, market cap, PE ratio, analyst targets.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_financial_metrics",
        "description": "Get income statement and balance sheet key metrics.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_scenario",
        "description": "Get the financial model projections for a specific scenario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "enum": ["base", "upside", "downside"],
                    "description": "Which scenario to retrieve"
                }
            },
            "required": ["scenario"]
        }
    },
    {
        "name": "calculate_valuation",
        "description": "Calculate an implied valuation range using EV/EBITDA multiples.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ebitda_eur_bn": {
                    "type": "number",
                    "description": "EBITDA in EUR billions"
                },
                "multiple_low": {
                    "type": "number",
                    "description": "Low end EV/EBITDA multiple (e.g. 5)"
                },
                "multiple_high": {
                    "type": "number",
                    "description": "High end EV/EBITDA multiple (e.g. 9)"
                }
            },
            "required": ["ebitda_eur_bn", "multiple_low", "multiple_high"]
        }
    },
    {
        "name": "generate_section",
        "description": "Write a specific section of the financial report.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": [
                        "executive_summary",
                        "business_overview",
                        "financial_analysis",
                        "risk_factors",
                        "investment_thesis",
                        "strategic_options"
                    ],
                    "description": "Which section to generate"
                },
                "context": {
                    "type": "string",
                    "description": "Key data points to include in this section"
                }
            },
            "required": ["section", "context"]
        }
    }
]


# Tool Executor 

def execute_tool(
    tool_name: str,
    tool_input: Dict,
    company_data: StructuredCompanyData,
    financial_model: FinancialModel,
    generated_sections: Dict[str, str],
    client: anthropic.Anthropic
) -> str:
    """Execute a tool call and return the result as a string."""

    if tool_name == "get_company_profile":
        p = company_data.profile
        return json.dumps({
            "name": p.name,
            "ticker": p.ticker,
            "sector": p.sector,
            "industry": p.industry,
            "country": p.country,
            "website": p.website,
            "description": p.description[:500] + "..." if len(p.description) > 500 else p.description,
        })

    elif tool_name == "get_market_data":
        m = company_data.market
        return json.dumps({
            "current_price": m.current_price,
            "market_cap_eur_bn": m.market_cap_eur_bn,
            "52w_high": m.fifty_two_week_high,
            "52w_low": m.fifty_two_week_low,
            "analyst_target": m.analyst_target_price,
            "analyst_recommendation_score": m.analyst_recommendation,
            "trailing_pe": m.trailing_pe,
            "forward_pe": m.forward_pe,
            "price_to_book": m.price_to_book,
            "note": "Recommendation: 1=Strong Buy, 3=Hold, 5=Strong Sell"
        })

    elif tool_name == "get_financial_metrics":
        i = company_data.income
        b = company_data.balance
        return json.dumps({
            "income": {
                "total_revenue_eur": i.total_revenue,
                "ebitda_eur": i.ebitda,
                "operating_margin_pct": i.operating_margin_pct,
                "net_margin_pct": i.net_margin_pct,
                "revenue_growth_pct": i.revenue_growth_pct,
                "earnings_growth_pct": i.earnings_growth_pct,
            },
            "balance": {
                "total_debt_eur": b.total_debt,
                "total_cash_eur": b.total_cash,
                "net_debt_eur": b.net_debt,
                "return_on_equity_pct": b.return_on_equity_pct,
            }
        })

    elif tool_name == "get_scenario":
        scenario_key = tool_input.get("scenario", "base")
        scenario = financial_model.scenarios.get(scenario_key)
        if not scenario:
            return json.dumps({"error": f"Unknown scenario: {scenario_key}"})
        return json.dumps({
            "label": scenario.label,
            "description": scenario.description,
            "assumptions": scenario.assumptions,
            "projections": [p.model_dump() for p in scenario.projections],
            "summary": scenario.summary,
        })

    elif tool_name == "calculate_valuation":
        ebitda = tool_input.get("ebitda_eur_bn", 0)
        low = tool_input.get("multiple_low", 5)
        high = tool_input.get("multiple_high", 9)
        net_debt = (company_data.balance.net_debt or 0) / 1_000_000_000
        shares = (company_data.market.shares_outstanding or 1_000_000_000) / 1_000_000_000  # in bn

        ev_low =ebitda * low
        ev_high = ebitda * high
        equity_low = ev_low -net_debt
        equity_high = ev_high -net_debt
        price_low = round(equity_low / shares, 2) if shares > 0 else None
        price_high = round(equity_high / shares, 2) if shares > 0 else None

        return json.dumps({
            "ebitda_eur_bn": ebitda,
            "ev_range_eur_bn": {"low": round(ev_low, 2), "high": round(ev_high, 2)},
            "net_debt_eur_bn": round(net_debt, 2),
            "implied_equity_eur_bn": {"low": round(equity_low, 2), "high": round(equity_high, 2)},
            "implied_price_per_share": {"low": price_low, "high": price_high},
            "note": "This is a simplified EV/EBITDA valuation. NOT investment advice. Uncertainty is high.",
            "multiples_used": f"{low}x - {high}x (airline sector range)"
        })

    elif tool_name == "generate_section":
        section = tool_input.get("section")
        context = tool_input.get("context", "")

        section_prompts = {
            "executive_summary": "Write a 2-paragraph executive summary for a Ryanair financial report.",
            "business_overview": "Write a business overview covering Ryanair's model, competitive position, and market.",
            "financial_analysis": "Write a financial analysis section covering revenue, margins, and key metrics.",
            "risk_factors": "Write a risk factors section covering 4-5 key risks for Ryanair.",
            "investment_thesis": "Write a balanced investment thesis with bull and bear cases.",
            "strategic_options": "Write a strategic options section covering Ryanair's funding and growth options.",
        }

        prompt = f"""
You are a senior equity research analyst writing a professional report on Ryanair (RYA.L).
Section to write: {section_prompts.get(section, section)}

Key data to incorporate:
{context}

Important:
- Be specific with numbers where provided
- Label all uncertainty clearly
- Do not present guesses as facts
- Keep it professional and concise (2-3 paragraphs max)
- This is for educational purposes only, NOT investment advice
"""
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        section_text = response.content[0].text
        generated_sections[section] = section_text
        return section_text

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


#  Main Agent

def run_agent(
    company_data: StructuredCompanyData,
    financial_model: FinancialModel,
) -> Dict[str, Any]:
    """
    Run the multi-step AI agent.
    Returns: final report content + observable trace of all steps.
    """
    print("[AGENT] Starting multi-step analysis agent")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    agent_trace = []      # Observable steps log
    generated_sections = {}

    system_prompt = """You are a corporate finance AI agent analysing Ryanair Holdings PLC.
Your job is to systematically gather data, run financial models, and write a professional report.

Work through these steps IN ORDER using the available tools:
1. Get company profile
2. Get market data  
3. Get financial metrics
4. Get all 3 scenario projections (base, upside, downside)
5. Calculate a valuation using the base case EBITDA
6. Generate each report section: executive_summary, business_overview, financial_analysis, risk_factors, investment_thesis, strategic_options

Be thorough and use ALL tools. The report must include all sections.
Always label uncertainty. This is educational only, not investment advice."""

    messages = [
        {"role": "user", "content": "Please conduct a full financial analysis of Ryanair and generate a complete report with all sections."}
    ]

    max_iterations = 25  # Safety limit
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"[AGENT] Step {iteration}...")

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        step_log = {
            "step": iteration,
            "timestamp": datetime.now().isoformat(),
            "stop_reason": response.stop_reason,
            "actions": []
        }

        # Processing content blocks
        assistant_content = []
        tool_calls_made = []

        for block in response.content:
            assistant_content.append(block)

            if block.type == "text" and block.text:
                step_log["actions"].append({"type": "reasoning", "content": block.text[:200]})

            elif block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                print(f"  [AGENT] Tool call: {tool_name}({json.dumps(tool_input)[:80]})")

                step_log["actions"].append({
                    "type": "tool_call",
                    "tool": tool_name,
                    "input": tool_input
                })
                tool_calls_made.append((block.id, tool_name, tool_input))

        agent_trace.append(step_log)
        messages.append({"role": "assistant", "content": assistant_content})

        # If no tool calls, agent is done
        if response.stop_reason == "end_turn" or not tool_calls_made:
            print("[AGENT] ✓ Agent completed analysis")
            break

        # Execute tool calls and feed results back
        tool_results = []
        for tool_use_id, tool_name, tool_input in tool_calls_made:
            result = execute_tool(
                tool_name, tool_input,
                company_data, financial_model,
                generated_sections, client
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result
            })
            step_log["actions"].append({
                "type": "tool_result",
                "tool": tool_name,
                "result_preview": result[:150] + "..." if len(result) > 150 else result
            })

        messages.append({"role": "user", "content": tool_results})

    # Extract final text response
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    print(f"[AGENT] ✓ Generated {len(generated_sections)} report sections, {len(agent_trace)} steps logged")

    return {
        "sections": generated_sections,
        "agent_trace": agent_trace,
        "final_summary": final_text,
        "steps_count": len(agent_trace),
    }

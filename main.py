"""
main.py
FastAPI application - orchestrator for the full Corporate Finance Autopilot pipeline.

Endpoints:
  GET  /              -> Extraordinary web dashboard with charts
  POST /analyze       -> Run full pipeline (background task)
  GET  /status        -> Live pipeline status + step log
  GET  /scenarios     -> Financial model scenario data (with projections)
  GET  /market        -> Market + financial metrics
  GET  /report        -> AI-generated report sections + agent trace
  GET  /download/{f}  -> Download outputs
  GET  /health        -> Health check
"""

import os
import json
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

from pipeline.ingest import fetch_ryanair_data, load_cached_data
from pipeline.transform import transform
from pipeline.financial_model import build_financial_model
from pipeline.agent import run_agent
from outputs.report_generator import generate_excel, generate_pdf

app = FastAPI(
    title="Ryanair Corporate Finance Autopilot",
    description="AI-powered corporate finance pipeline — Assiduous Hackathon 2025",
    version="2.0.0"
)

#  Global state
pipeline_status = {
    "status": "idle",
    "current_step": "",
    "steps_log": [],
    "started_at": None,
    "completed_at": None,
    "error": None,
    "outputs": {}
}


# Pipeline

def log_step(msg: str):
    pipeline_status["current_step"] = msg
    pipeline_status["steps_log"].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "msg": msg
    })
    print(f"  {msg}")


def run_full_pipeline(use_cache: bool = True):
    global pipeline_status
    pipeline_status = {
        "status": "running",
        "current_step": "Initialising...",
        "steps_log": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "outputs": {}
    }
    try:
        print(f"\n{'='*60}\nPIPELINE START\n{'='*60}")

        log_step("Step 1/5 — Ingesting Ryanair public data (Yahoo Finance)")
        raw = load_cached_data() if use_cache else fetch_ryanair_data()

        log_step("Step 2/5 — Transforming & validating with Pydantic models")
        structured = transform(raw)

        log_step("Step 3/5 — Building 3-scenario financial model")
        model = build_financial_model(structured)

        log_step("Step 4/5 — Running multi-step Claude AI agent (tool-calling)")
        agent_results = run_agent(structured, model)

        log_step("Step 5/5 — Generating Excel model + PDF shareholder report")
        excel_path = generate_excel(structured, model)
        pdf_path   = generate_pdf(structured, model, agent_results)

        # Full summary for dashboard
        summary = {
            "company":        structured.profile.name,
            "ticker":         structured.profile.ticker,
            "generated_at":   datetime.now().isoformat(),
            "market":         structured.market.model_dump(),
            "income":         structured.income.model_dump(),
            "balance":        structured.balance.model_dump(),
            "scenarios": {
                k: {
                    **v.summary,
                    "projections":  [p.model_dump() for p in v.projections],
                    "assumptions":  v.assumptions,
                    "label":        v.label,
                    "color":        v.color,
                    "description":  v.description,
                }
                for k, v in model.scenarios.items()
            },
            "key_drivers":      model.key_drivers,
            "agent_sections":   agent_results.get("sections", {}),
            "agent_trace":      agent_results.get("agent_trace", []),
            "steps_count":      agent_results.get("steps_count", 0),
        }
        os.makedirs("data", exist_ok=True)
        with open("data/pipeline_summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)

        pipeline_status.update({
            "status":       "complete",
            "current_step": "Pipeline complete",
            "completed_at": datetime.now().isoformat(),
            "outputs": {
                "excel":         excel_path,
                "pdf":           pdf_path,
                "agent_steps":   agent_results.get("steps_count", 0),
                "sections":      len(agent_results.get("sections", {})),
            }
        })
        log_step(f"Done — {agent_results.get('steps_count',0)} agent steps, "
                 f"{len(agent_results.get('sections',{}))} report sections")

    except Exception as e:
        import traceback; traceback.print_exc()
        pipeline_status.update({
            "status":       "error",
            "current_step": f"Error: {e}",
            "error":        str(e)
        })


# API 

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now().isoformat(),
            "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.post("/analyze")
def analyze(background_tasks: BackgroundTasks, fresh: bool = False):
    if pipeline_status["status"] == "running":
        return JSONResponse(status_code=409, content={"error": "Already running"})
    background_tasks.add_task(run_full_pipeline, use_cache=not fresh)
    return {"message": "Pipeline started", "poll": "/status"}


@app.get("/status")
def status():
    return pipeline_status


@app.get("/scenarios")
def get_scenarios():
    path = "data/pipeline_summary.json"
    if not os.path.exists(path):
        raise HTTPException(404, "Run /analyze first")
    with open(path) as f:
        return json.load(f).get("scenarios", {})


@app.get("/market")
def get_market():
    path = "data/pipeline_summary.json"
    if not os.path.exists(path):
        raise HTTPException(404, "Run /analyze first")
    with open(path) as f:
        d = json.load(f)
    return {
        "market":   d.get("market", {}),
        "income":   d.get("income", {}),
        "balance":  d.get("balance", {}),
        "company":  d.get("company"),
        "ticker":   d.get("ticker"),
    }


@app.get("/report")
def get_report():
    path = "data/pipeline_summary.json"
    if not os.path.exists(path):
        raise HTTPException(404, "Run /analyze first")
    with open(path) as f:
        d = json.load(f)
    return {
        "sections": d.get("agent_sections", {}),
        "trace":    d.get("agent_trace", []),
    }


@app.get("/download/{filename}")
def download(filename: str):
    files = {
        "excel":   "outputs/ryanair_financial_model.xlsx",
        "pdf":     "outputs/ryanair_report.pdf",
        "summary": "data/pipeline_summary.json",
        "raw":     "data/ryanair_raw.json",
    }
    if filename not in files:
        raise HTTPException(404, f"Options: {list(files.keys())}")
    p = files[filename]
    if not os.path.exists(p):
        raise HTTPException(404, "File not ready — run /analyze first")
    return FileResponse(p, filename=os.path.basename(p))


#  Dashboard 

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ryanair · Corporate Finance Autopilot</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,400&family=JetBrains+Mono:wght@400;500&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{
  --navy:#08111f;--navy2:#0f1f35;--navy3:#162840;
  --blue:#2d7ef7;--blue2:#1a5fd4;--cyan:#06b6d4;
  --green:#10b981;--amber:#f59e0b;--red:#ef4444;
  --slate:#94a3b8;--border:rgba(148,163,184,0.15);
  --border2:rgba(148,163,184,0.08);--text:#e2e8f0;--text2:#94a3b8;
  --card:rgba(255,255,255,0.03);--card2:rgba(255,255,255,0.06);
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:'Inter',sans-serif;background:var(--navy);color:var(--text);min-height:100vh;overflow-x:hidden}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(ellipse 80% 50% at 20% 10%,rgba(45,126,247,0.08) 0%,transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 80%,rgba(6,182,212,0.06) 0%,transparent 50%);
}

/* Header */
header{
  position:sticky;top:0;z-index:100;
  background:rgba(8,17,31,0.92);backdrop-filter:blur(16px);
  border-bottom:1px solid var(--border);
  padding:0 2rem;display:flex;align-items:center;justify-content:space-between;height:60px;
}
.logo{font-family:'Playfair Display',serif;font-size:1.15rem;font-weight:700;letter-spacing:-0.01em}
.logo em{color:var(--blue);font-style:italic;font-weight:400}
.header-right{display:flex;align-items:center;gap:.8rem}
.pill{
  font-family:'JetBrains Mono',monospace;font-size:.68rem;font-weight:500;
  padding:4px 10px;border-radius:20px;
  background:rgba(45,126,247,.15);color:var(--blue);border:1px solid rgba(45,126,247,.3);
}
.pill.green{background:rgba(16,185,129,.12);color:var(--green);border-color:rgba(16,185,129,.25)}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);display:inline-block;margin-right:5px}

/* Layout */
main{max-width:1200px;margin:0 auto;padding:3rem 1.5rem;position:relative;z-index:1}

/* Hero */
.hero{text-align:center;padding:2rem 0 3rem}
.hero-eyebrow{
  font-family:'JetBrains Mono',monospace;font-size:.72rem;letter-spacing:.15em;text-transform:uppercase;
  color:var(--blue);margin-bottom:1.2rem;
  display:flex;align-items:center;justify-content:center;gap:8px;
}
.hero-eyebrow::before,.hero-eyebrow::after{content:'';height:1px;width:40px;background:linear-gradient(90deg,transparent,var(--blue))}
.hero-eyebrow::after{transform:scaleX(-1)}
.hero h1{
  font-family:'Playfair Display',serif;font-size:clamp(2.4rem,5.5vw,4rem);
  font-weight:700;line-height:1.05;letter-spacing:-.02em;margin-bottom:1.2rem;
}
.hero h1 span{color:transparent;background:linear-gradient(135deg,var(--blue),var(--cyan));-webkit-background-clip:text;background-clip:text}
.hero-sub{color:var(--text2);font-size:1rem;max-width:560px;margin:0 auto 2.5rem;line-height:1.8;font-weight:300}

/* Pipeline */
.pipeline{display:flex;align-items:center;justify-content:center;gap:4px;margin:0 auto 2.5rem;max-width:860px;flex-wrap:wrap}
.p-step{
  display:flex;align-items:center;gap:8px;background:var(--card2);
  border:1px solid var(--border);border-radius:8px;padding:9px 14px;
  font-size:.8rem;font-weight:500;color:var(--text2);transition:all .2s;
}
.p-step:hover{border-color:rgba(45,126,247,.4);color:var(--text);background:rgba(45,126,247,.08)}
.p-step .num{
  font-family:'JetBrains Mono',monospace;font-size:.65rem;
  background:rgba(45,126,247,.2);color:var(--blue);
  width:18px;height:18px;border-radius:4px;display:flex;align-items:center;justify-content:center;
}
.p-arrow{color:var(--border);font-size:1rem;padding:0 2px;flex-shrink:0}

/* Buttons */
.actions{display:flex;gap:.8rem;justify-content:center;flex-wrap:wrap;margin-bottom:2.5rem}
.btn{
  display:inline-flex;align-items:center;gap:8px;padding:.75rem 1.6rem;
  border:none;border-radius:8px;font-size:.9rem;font-weight:500;
  cursor:pointer;transition:all .2s;font-family:'Inter',sans-serif;
}
.btn-primary{background:linear-gradient(135deg,var(--blue),var(--blue2));color:white;box-shadow:0 4px 20px rgba(45,126,247,.3)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 6px 28px rgba(45,126,247,.45)}
.btn-ghost{background:var(--card2);color:var(--text2);border:1px solid var(--border)}
.btn-ghost:hover{border-color:rgba(45,126,247,.4);color:var(--text);background:rgba(45,126,247,.08)}
.btn:disabled{opacity:.4;cursor:not-allowed;transform:none!important;box-shadow:none!important}

/* Status */
.status-bar{
  background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:1rem 1.4rem;margin-bottom:1.2rem;display:flex;align-items:center;gap:1rem;
}
.status-dot{width:9px;height:9px;border-radius:50%;background:var(--slate);flex-shrink:0;transition:background .3s}
.status-dot.running{background:var(--blue);animation:blink 1s infinite}
.status-dot.complete{background:var(--green);box-shadow:0 0 8px var(--green)}
.status-dot.error{background:var(--red)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
#step-text{font-family:'JetBrains Mono',monospace;font-size:.82rem;color:var(--text);flex:1}
#timing{font-family:'JetBrains Mono',monospace;font-size:.72rem;color:var(--slate);flex-shrink:0}
.progress-steps{display:flex;gap:6px;margin-bottom:2.5rem;flex-wrap:wrap}
.ps{font-family:'JetBrains Mono',monospace;font-size:.68rem;padding:4px 10px;border-radius:4px;border:1px solid var(--border);color:var(--text2);background:var(--card);transition:all .3s}
.ps.done{background:rgba(16,185,129,.1);color:var(--green);border-color:rgba(16,185,129,.3)}
.ps.active{background:rgba(45,126,247,.1);color:var(--blue);border-color:rgba(45,126,247,.3);animation:blink 1s infinite}

/* Section heads */
.section-head{display:flex;align-items:baseline;gap:1rem;margin-bottom:1.4rem;margin-top:3rem}
.section-head h2{font-family:'Playfair Display',serif;font-size:1.45rem;font-weight:700;letter-spacing:-.01em}
.section-head .sh-line{flex:1;height:1px;background:var(--border2)}
.section-head .sh-tag{font-family:'JetBrains Mono',monospace;font-size:.65rem;color:var(--slate);text-transform:uppercase;letter-spacing:.1em;flex-shrink:0}

/* KPI grid */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:1rem;margin-bottom:2rem}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.1rem 1.2rem;position:relative;overflow:hidden;transition:border-color .2s}
.kpi:hover{border-color:rgba(45,126,247,.3)}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--blue),var(--cyan));opacity:0;transition:opacity .2s}
.kpi:hover::before{opacity:1}
.kpi-label{font-size:.7rem;color:var(--text2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.kpi-value{font-size:1.4rem;font-weight:600;color:var(--text);font-family:'JetBrains Mono',monospace;line-height:1}
.kpi-sub{font-size:.7rem;color:var(--slate);margin-top:4px}
.kpi-up{color:var(--green)}.kpi-down{color:var(--red)}

/* Charts */
.charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;margin-bottom:2rem}
@media(max-width:700px){.charts-grid{grid-template-columns:1fr}}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.4rem}
.chart-card h3{font-size:.75rem;font-weight:500;color:var(--text2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:1.2rem}
.chart-wrap{position:relative;height:220px}

/* Scenarios */
.scenario-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:2rem}
@media(max-width:680px){.scenario-grid{grid-template-columns:1fr}}
.sc-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.3rem;border-top:3px solid transparent;transition:transform .2s}
.sc-card:hover{transform:translateY(-3px)}
.sc-card.base{border-top-color:var(--blue)}
.sc-card.upside{border-top-color:var(--green)}
.sc-card.downside{border-top-color:var(--red)}
.sc-label{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px}
.sc-card.base .sc-label{color:var(--blue)}
.sc-card.upside .sc-label{color:var(--green)}
.sc-card.downside .sc-label{color:var(--red)}
.sc-rev{font-family:'JetBrains Mono',monospace;font-size:1.55rem;font-weight:500;line-height:1;margin-bottom:2px}
.sc-sub{font-size:.75rem;color:var(--slate);margin-bottom:1rem;line-height:1.5}
.sc-row{display:flex;justify-content:space-between;align-items:center;font-size:.8rem;padding:5px 0;border-bottom:1px solid var(--border2)}
.sc-row:last-child{border-bottom:none}
.sc-row span:last-child{font-family:'JetBrains Mono',monospace;font-weight:500;font-size:.82rem}
.assumption-tag{display:inline-block;font-size:.65rem;font-family:'JetBrains Mono',monospace;padding:2px 6px;border-radius:3px;margin:2px}
.sc-card.base .assumption-tag{background:rgba(45,126,247,.12);color:var(--blue)}
.sc-card.upside .assumption-tag{background:rgba(16,185,129,.12);color:var(--green)}
.sc-card.downside .assumption-tag{background:rgba(239,68,68,.12);color:var(--red)}

/* Report */
.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:2rem}
@media(max-width:680px){.report-grid{grid-template-columns:1fr}}
.report-section{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.3rem}
.report-section h4{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--blue);margin-bottom:.8rem}
.report-section p{font-size:.82rem;color:var(--text2);line-height:1.75;max-height:130px;overflow:hidden;-webkit-mask-image:linear-gradient(180deg,black 60%,transparent)}

/* Downloads */
.dl-grid{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem}
.dl-card{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1rem 1.3rem;text-decoration:none;color:var(--text);transition:all .2s;min-width:190px}
.dl-card:hover{border-color:rgba(45,126,247,.4);transform:translateY(-2px)}
.dl-icon{font-size:1.5rem}
.dl-name{font-weight:500;font-size:.9rem}
.dl-sub{font-size:.72rem;color:var(--slate);margin-top:2px}

/* Trace */
.trace{background:rgba(0,0,0,.4);border:1px solid var(--border);border-radius:10px;padding:1.2rem 1.5rem;font-family:'JetBrains Mono',monospace;font-size:.75rem;line-height:1.85;max-height:340px;overflow-y:auto;margin-bottom:2rem;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.t-step{color:var(--blue)}.t-tool{color:var(--amber)}.t-result{color:var(--green)}.t-time{color:var(--slate);font-size:.68rem}

/* Stack */
.stack-grid{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:3rem}
.stack-tag{font-family:'JetBrains Mono',monospace;font-size:.72rem;padding:5px 11px;border-radius:5px;background:var(--card2);border:1px solid var(--border);color:var(--text2)}

footer{text-align:center;padding:2rem;color:var(--text2);font-size:.75rem;border-top:1px solid var(--border2);margin-top:1rem;line-height:1.8}
footer strong{color:var(--text)}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>

<header>
  <div class="logo">RYA&nbsp;·&nbsp;<em>Finance Autopilot</em></div>
  <div class="header-right">
    <span class="pill green"><span class="live-dot"></span>Live</span>
  </div>
</header>

<main>

<div class="hero">
  <div class="hero-eyebrow">Corporate Finance Autopilot</div>
  <h1>AI-Powered <span>Financial Analysis</span><br>Pipeline for Ryanair</h1>
  <p class="hero-sub">Ingests public market data -> validates with Pydantic -> builds 3-scenario projections -> runs a multi-step Claude agent -> generates investor-grade Excel models and PDF reports. Automatically.</p>
</div>

<div class="pipeline">
  <div class="p-step"><span class="num">1</span>Ingest</div><div class="p-arrow">›</div>
  <div class="p-step"><span class="num">2</span>Transform</div><div class="p-arrow">›</div>
  <div class="p-step"><span class="num">3</span>Model</div><div class="p-arrow">›</div>
  <div class="p-step"><span class="num">4</span>AI Agent</div><div class="p-arrow">›</div>
  <div class="p-step"><span class="num">5</span>Output</div>
</div>

<div class="actions">
  <button class="btn btn-primary" id="run-btn" onclick="runPipeline(false)">▶&ensp;Run Pipeline</button>
  <button class="btn btn-ghost" onclick="runPipeline(true)">↺&ensp;Refresh Data</button>
  <button class="btn btn-ghost" onclick="checkStatus()">⬡&ensp;Ping Status</button>
</div>

<div class="status-bar">
  <div class="status-dot" id="status-dot"></div>
  <span id="step-text">Idle — click Run Pipeline to begin</span>
  <span id="timing"></span>
</div>
<div class="progress-steps">
  <span class="ps" id="ps1">1 · Ingest</span>
  <span class="ps" id="ps2">2 · Transform</span>
  <span class="ps" id="ps3">3 · Model</span>
  <span class="ps" id="ps4">4 · AI Agent</span>
  <span class="ps" id="ps5">5 · Output</span>
</div>

<!-- KPIs -->
<div id="kpi-section" style="display:none">
  <div class="section-head"><h2>Market Snapshot</h2><div class="sh-line"></div><span class="sh-tag">Yahoo Finance · Public Data</span></div>
  <div class="kpi-grid" id="kpi-grid"></div>
</div>

<!-- Charts -->
<div id="charts-section" style="display:none">
  <div class="section-head"><h2>Financial Visualisation</h2><div class="sh-line"></div><span class="sh-tag">3-Scenario Model</span></div>
  <div class="charts-grid">
    <div class="chart-card"><h3>Revenue Projections — 3 Scenarios (€bn)</h3><div class="chart-wrap"><canvas id="revenueChart"></canvas></div></div>
    <div class="chart-card"><h3>EBIT Margin % by Year</h3><div class="chart-wrap"><canvas id="marginChart"></canvas></div></div>
    <div class="chart-card"><h3>Passenger Volume (millions)</h3><div class="chart-wrap"><canvas id="paxChart"></canvas></div></div>
    <div class="chart-card"><h3>Cost Breakdown — Base Case Year 1 (€bn)</h3><div class="chart-wrap"><canvas id="costChart"></canvas></div></div>
  </div>
</div>

<!-- Scenarios -->
<div id="scenarios-section" style="display:none">
  <div class="section-head"><h2>Scenario Projections</h2><div class="sh-line"></div><span class="sh-tag">Base · Upside · Downside</span></div>
  <div class="scenario-grid" id="scenario-grid"></div>
</div>

<!-- AI Report -->
<div id="report-section" style="display:none">
  <div class="section-head"><h2>AI-Generated Report</h2><div class="sh-line"></div><span class="sh-tag">Claude · Multi-step Agent</span></div>
  <div class="report-grid" id="report-grid"></div>
</div>

<!-- Downloads -->
<div id="downloads-section" style="display:none">
  <div class="section-head"><h2>Downloads</h2><div class="sh-line"></div><span class="sh-tag">Generated Outputs</span></div>
  <div class="dl-grid">
    <a class="dl-card" href="/download/excel" download><span class="dl-icon">📗</span><div><div class="dl-name">Excel Model</div><div class="dl-sub">3-scenario financial model</div></div></a>
    <a class="dl-card" href="/download/pdf" download><span class="dl-icon">📕</span><div><div class="dl-name">PDF Report</div><div class="dl-sub">Full shareholder report</div></div></a>
    <a class="dl-card" href="/download/summary" download><span class="dl-icon">📋</span><div><div class="dl-name">JSON Summary</div><div class="dl-sub">Raw pipeline output</div></div></a>
    <a class="dl-card" href="/docs" target="_blank"><span class="dl-icon">📐</span><div><div class="dl-name">API Docs</div><div class="dl-sub">FastAPI auto-docs</div></div></a>
  </div>
</div>

<!-- Agent Trace -->
<div id="trace-section" style="display:none">
  <div class="section-head"><h2>Agent Trace</h2><div class="sh-line"></div><span class="sh-tag">Observable Steps · Not a Black Box</span></div>
  <div class="trace" id="trace-log"></div>
</div>

<!-- Tech Stack -->
<div class="section-head" style="margin-top:3rem"><h2>Tech Stack</h2><div class="sh-line"></div><span class="sh-tag">Open Source · Justified</span></div>
<div class="stack-grid">
  <span class="stack-tag">FastAPI — async REST API</span>
  <span class="stack-tag">yfinance — public financial data</span>
  <span class="stack-tag">Pydantic — typed data validation</span>
  <span class="stack-tag">anthropic SDK — Claude tool-calling</span>
  <span class="stack-tag">openpyxl — Excel generation</span>
  <span class="stack-tag">reportlab — PDF generation</span>
  <span class="stack-tag">pandas — timeseries data</span>
  <span class="stack-tag">Chart.js — data visualisation</span>
  <span class="stack-tag">Docker — containerised run</span>
  <span class="stack-tag">python-dotenv — secrets handling</span>
</div>

</main>

<footer>
  <strong>Ryanair Corporate Finance Autopilot</strong> · Assiduous Hackathon 2025<br>
  Educational purposes only · Not investment advice · Data: Yahoo Finance (public) · Sources cited in README
</footer>

<script>
let polling = null;
let charts = {};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(148,163,184,0.1)';
Chart.defaults.font.family = 'Inter';
Chart.defaults.font.size = 11;

const COLORS = {
  base:     {border:'#2d7ef7', bg:'rgba(45,126,247,0.18)'},
  upside:   {border:'#10b981', bg:'rgba(16,185,129,0.18)'},
  downside: {border:'#ef4444', bg:'rgba(239,68,68,0.18)'},
};

async function runPipeline(fresh){
  document.getElementById('run-btn').disabled = true;
  setStatus('running','Starting pipeline...');
  try {
    const r = await fetch('/analyze?fresh='+fresh, {method:'POST'});
    if(r.status===409){ alert('Already running!'); document.getElementById('run-btn').disabled=false; return; }
    startPolling();
  } catch(e){ setStatus('error','Failed: '+e.message); document.getElementById('run-btn').disabled=false; }
}

function startPolling(){ if(polling) clearInterval(polling); polling=setInterval(checkStatus,2000); }

async function checkStatus(){
  try {
    const r = await fetch('/status'); const d = await r.json();
    setStatus(d.status, d.current_step||'Idle');
    updateProgress(d.current_step||'');
    if(d.started_at){
      const el = d.completed_at
        ? ((new Date(d.completed_at)-new Date(d.started_at))/1000).toFixed(1)+'s'
        : ((new Date()-new Date(d.started_at))/1000).toFixed(0)+'s elapsed';
      document.getElementById('timing').textContent = el;
    }
    if(d.status==='complete'){ clearInterval(polling); document.getElementById('run-btn').disabled=false; await loadAll(); }
    else if(d.status==='error'){ clearInterval(polling); document.getElementById('run-btn').disabled=false; }
  } catch(e){ console.error(e); }
}

function setStatus(s,t){ document.getElementById('status-dot').className='status-dot '+s; document.getElementById('step-text').textContent=t; }

function updateProgress(step){
  [['ps1','1/5'],['ps2','2/5'],['ps3','3/5'],['ps4','4/5'],['ps5','5/5']].forEach(([id,k],i,arr)=>{
    const active = arr.findIndex(([,k2])=>step.includes(k2));
    const el = document.getElementById(id);
    el.className = i<active?'ps done':i===active?'ps active':'ps';
  });
}

async function loadAll(){ await Promise.all([loadMarket(),loadScenarios(),loadReport()]); document.getElementById('downloads-section').style.display='block'; }

async function loadMarket(){
  try {
    const r = await fetch('/market'); if(!r.ok) return;
    const {market,income,balance,company,ticker} = await r.json();
    const grid = document.getElementById('kpi-grid');
    const kpis = [
      {l:'Current Price', v:market.current_price?market.current_price+'p':'N/A', s:ticker},
      {l:'Market Cap',    v:market.market_cap_eur_bn?'€'+market.market_cap_eur_bn+'bn':'N/A', s:'EUR billions'},
      {l:'Trailing P/E',  v:market.trailing_pe??'N/A', s:'Price / Earnings'},
      {l:'Forward P/E',   v:market.forward_pe??'N/A', s:'Fwd estimate'},
      {l:'52W High',      v:market.fifty_two_week_high??'N/A', s:'Pence'},
      {l:'52W Low',       v:market.fifty_two_week_low??'N/A', s:'Pence'},
      {l:'Op. Margin',    v:income.operating_margin_pct?income.operating_margin_pct+'%':'N/A', s:'Operating', c:income.operating_margin_pct>0?'kpi-up':'kpi-down'},
      {l:'Net Margin',    v:income.net_margin_pct?income.net_margin_pct+'%':'N/A', s:'Net profit', c:income.net_margin_pct>0?'kpi-up':'kpi-down'},
      {l:'Rev Growth',    v:income.revenue_growth_pct?income.revenue_growth_pct+'%':'N/A', s:'YoY', c:income.revenue_growth_pct>0?'kpi-up':'kpi-down'},
      {l:'Net Debt',      v:balance.net_debt?'€'+(balance.net_debt/1e9).toFixed(1)+'bn':'N/A', s:'Debt minus cash'},
      {l:'Analyst Target',v:market.analyst_target_price?market.analyst_target_price+'p':'N/A', s:'Mean target'},
      {l:'Price/Book',    v:market.price_to_book??'N/A', s:'P/B ratio'},
    ];
    grid.innerHTML = kpis.map(k=>`<div class="kpi"><div class="kpi-label">${k.l}</div><div class="kpi-value ${k.c||''}">${k.v}</div><div class="kpi-sub">${k.s}</div></div>`).join('');
    document.getElementById('kpi-section').style.display='block';
  } catch(e){ console.error(e); }
}

async function loadScenarios(){
  try {
    const r = await fetch('/scenarios'); if(!r.ok) return;
    const data = await r.json();
    buildCharts(data);
    buildScenarioCards(data);
    document.getElementById('charts-section').style.display='block';
    document.getElementById('scenarios-section').style.display='block';
  } catch(e){ console.error(e); }
}

function buildCharts(data){
  const keys=['base','upside','downside'];
  const labels = data.base?.projections?.map(p=>String(p.year))||[];

  makeChart('revenueChart','bar',{
    labels,
    datasets: keys.map(k=>({label:data[k]?.label||k, data:data[k]?.projections?.map(p=>+(p.total_revenue_eur_bn||0).toFixed(3))||[], backgroundColor:COLORS[k].bg, borderColor:COLORS[k].border, borderWidth:2, borderRadius:4}))
  }, chartOpts('€bn'));

  makeChart('marginChart','line',{
    labels,
    datasets: keys.map(k=>({label:data[k]?.label||k, data:data[k]?.projections?.map(p=>+(p.ebit_margin_pct||0).toFixed(1))||[], borderColor:COLORS[k].border, backgroundColor:COLORS[k].bg, borderWidth:2.5, pointRadius:5, pointBackgroundColor:COLORS[k].border, fill:true, tension:0.35}))
  }, chartOpts('%'));

  makeChart('paxChart','line',{
    labels,
    datasets: keys.map(k=>({label:data[k]?.label||k, data:data[k]?.projections?.map(p=>+(p.passengers_m||0).toFixed(1))||[], borderColor:COLORS[k].border, backgroundColor:'transparent', borderWidth:2.5, pointRadius:4, pointBackgroundColor:COLORS[k].border, borderDash:k==='downside'?[5,3]:[], tension:0.3}))
  }, chartOpts('m'));

  const b1 = data.base?.projections?.[0];
  if(b1){
    makeChart('costChart','doughnut',{
      labels:['Fuel Cost','Other OpEx','EBIT'],
      datasets:[{data:[+(b1.fuel_cost_eur_bn||0).toFixed(3), +(b1.other_opex_eur_bn||0).toFixed(3), Math.max(0,+(b1.ebit_eur_bn||0).toFixed(3))], backgroundColor:['rgba(245,158,11,0.75)','rgba(148,163,184,0.4)','rgba(16,185,129,0.65)'], borderColor:['#f59e0b','#4b5563','#10b981'], borderWidth:2}]
    },{responsive:true,maintainAspectRatio:false,cutout:'60%',plugins:{legend:{position:'bottom',labels:{color:'#94a3b8',padding:14,boxWidth:10}},tooltip:{callbacks:{label:c=>`€${c.parsed.toFixed(3)}bn`}}}});
  }
}

function makeChart(id, type, data, options){
  if(charts[id]) charts[id].destroy();
  const el = document.getElementById(id);
  if(!el) return;
  charts[id] = new Chart(el, {type, data, options});
}

function chartOpts(unit){
  return {
    responsive:true, maintainAspectRatio:false,
    interaction:{mode:'index',intersect:false},
    plugins:{
      legend:{position:'top',labels:{color:'#94a3b8',padding:10,boxWidth:8,usePointStyle:true}},
      tooltip:{backgroundColor:'rgba(8,17,31,0.95)',borderColor:'rgba(148,163,184,0.2)',borderWidth:1,padding:10,callbacks:{label:c=>`${c.dataset.label}: ${typeof c.parsed.y==='number'?c.parsed.y.toFixed(2):c.parsed.y} ${unit}`}}
    },
    scales:{
      x:{grid:{color:'rgba(148,163,184,0.05)'},ticks:{color:'#64748b'}},
      y:{grid:{color:'rgba(148,163,184,0.05)'},ticks:{color:'#64748b',callback:v=>`${v} ${unit}`}}
    }
  };
}

function buildScenarioCards(data){
  const desc={base:'Stable growth, steady fuel, modest yield gains.',upside:'Strong demand, lower fuel, premium ancillary revenue.',downside:'Weak demand, fuel spike, geopolitical disruption.'};
  document.getElementById('scenario-grid').innerHTML=['base','upside','downside'].map(k=>{
    const s=data[k]; if(!s) return '';
    const a=s.assumptions||{};
    return `<div class="sc-card ${k}">
      <div class="sc-label">${s.label||k}</div>
      <div class="sc-rev">€${s.total_revenue_3y_eur_bn}bn</div>
      <div class="sc-sub">${desc[k]}</div>
      <div style="margin-bottom:10px">
        <span class="assumption-tag">Pax ${a.passenger_growth_pct>=0?'+':''}${a.passenger_growth_pct}%</span>
        <span class="assumption-tag">Fuel ${a.fuel_cost_delta_pct>=0?'+':''}${a.fuel_cost_delta_pct}%</span>
        <span class="assumption-tag">Yield ${a.yield_change_pct>=0?'+':''}${a.yield_change_pct}%</span>
      </div>
      <div class="sc-row"><span>3Y Revenue</span><span>€${s.total_revenue_3y_eur_bn}bn</span></div>
      <div class="sc-row"><span>Avg EBIT Margin</span><span>${s.avg_ebit_margin_pct}%</span></div>
      <div class="sc-row"><span>Final Year Rev</span><span>€${s.final_year_revenue_eur_bn}bn</span></div>
    </div>`;
  }).join('');
}

async function loadReport(){
  try {
    const r = await fetch('/report'); if(!r.ok) return;
    const {sections,trace} = await r.json();
    const titles={executive_summary:'Executive Summary',business_overview:'Business Overview',financial_analysis:'Financial Analysis',risk_factors:'Risk Factors',investment_thesis:'Investment Thesis',strategic_options:'Strategic Options'};
    document.getElementById('report-grid').innerHTML = Object.entries(sections).map(([k,v])=>`<div class="report-section"><h4>${titles[k]||k}</h4><p>${v.replace(/\n/g,'<br>')}</p></div>`).join('');
    document.getElementById('report-section').style.display='block';

    let html='';
    for(const step of trace){
      html+=`<div class="t-step"><span class="t-time">[${(step.timestamp||'').slice(11,19)}]</span> ▶ Step ${step.step} — ${step.stop_reason}</div>`;
      for(const a of step.actions||[]){
        if(a.type==='tool_call') html+=`<span class="t-tool">  ⚙ ${a.tool}(${JSON.stringify(a.input).slice(0,70)})</span>\n`;
        else if(a.type==='tool_result') html+=`<span class="t-result">  ✓ ${(a.result_preview||'').slice(0,100)}</span>\n`;
      }
    }
    document.getElementById('trace-log').innerHTML = html||'<span style="color:#475569">No trace yet.</span>';
    document.getElementById('trace-section').style.display='block';
  } catch(e){ console.error(e); }
}

// Init
checkStatus();
(async()=>{ const r=await fetch('/status'); const d=await r.json(); if(d.status==='complete') await loadAll(); })();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

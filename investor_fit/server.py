"""Investor-Fit Agent: an MCP server people connect to their own Claude.

Claude handles the conversation and the writing. This server supplies the
verified funder data and the deterministic matching, so every funder Claude
mentions comes from the database with a source link.
"""

from __future__ import annotations

import os
from typing import Any, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import data
from .matching import evaluate, match
from .models import CompanyProfile, FoundFunder
from .vocab import FUNDER_TYPES, INSTRUMENTS, SECTORS, STAGE_HELP

INSTRUCTIONS = """\
Investor-Fit Agent matches companies to funders worldwide. It holds a curated, source-linked funder database, scores the fit, lists
readiness gaps, and can score any other funder from criteria read on its website.

How to work:
1. Gather the company profile from the user in plain conversation. You need at least country and
   sector. Also ask, briefly and in one message, for anything important that is missing: stage,
   amount sought (USD), type of money wanted, annual revenue, years operating, years of audited
   accounts, export history/orders, impact story, women-led. Never invent values; leave unknowns null.
2. Call match_company. Use check_readiness or get_funder for detail on a specific funder.
3. Present results as an investor-targeting memo (call memo_template for the format).

Financial models:
- No model yet: call financial_model_guide, collect assumptions (use uploaded accounts for opening
  balances and history), then project_financials. If the Investor-Fit skill is installed, also build
  the Excel model with its build_model.py script.
- Has a model: read it, pass its yearly figures to review_projections, and (with the skill) run
  review_model.py on the file for mechanical checks. Report findings by severity, with fixes.
- Uploaded documents: extract facts with their source (document and page) before filling the profile.

Rules:
- The database is a verified core, not every funder in the world. After match_company, if the user
  wants wider coverage (or names a funder that is not in the database), use web search to find
  funders that fit, read each one's official criteria page, and score it with score_found_funder.
  Label those results "found online, not verified" and never mix them up with database results.
- Never state a funder's criteria from memory. Facts come from the database or a page you just read.
- The fit score is computed by the server. Explain it; never recalculate or change it.
- Always show each funder's source link and last_checked date, and flag rows whose data_confidence
  is not "high" or whose verification_status is "needs_human_review".
- For funders with an access_route, explain the company must go through partner banks or funds.
- End every memo with the disclaimer returned by match_company. This is not financial advice.
"""

mcp = MCPServer(
    name="investor-fit-agent",
    title="Investor-Fit Agent",
    description="Match companies to funders worldwide, check readiness, and build or review financial models.",
    instructions=INSTRUCTIONS,
    website_url="https://github.com/EMMANUEL-LAMPTEY-96/investor-fit",
    version="0.4.0",
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False, idempotentHint=True)

SectorT = Literal[tuple(SECTORS)]  # type: ignore[valid-type]
InstrumentT = Literal[tuple(INSTRUMENTS)]  # type: ignore[valid-type]
FunderTypeT = Literal[tuple(FUNDER_TYPES)]  # type: ignore[valid-type]


@mcp.tool(annotations=READ_ONLY)
def match_company(company: CompanyProfile, top_n: int = 10) -> dict[str, Any]:
    """Rank the funders in the database for one company.

    Applies hard filters (geography, instrument, sector, stage, ticket size), then a 0-100 fit
    score (sector 30, stage 20, ticket 20, impact 15, geography 15). For each match it returns
    the score breakdown, readiness ("ready", "check_first" or "not_yet"), each gap with what
    would unlock it, how to apply, and source links. Also lists excluded funders and why, and
    which profile fields are missing (ask the user for those to sharpen the result).
    """
    top_n = max(1, min(int(top_n), 25))
    return match(company, data.load_funders(), top_n=top_n)


@mcp.tool(annotations=READ_ONLY)
def check_readiness(company: CompanyProfile, funder_id: str) -> dict[str, Any]:
    """Detailed fit and readiness check of one company against one funder.

    Use when the user asks about a specific funder ("could we get money from X?"). Returns either
    the reason the funder is ruled out, or the score breakdown and each requirement with status
    met / missing / unknown and what would unlock it.
    """
    f = data.get_funder(funder_id)
    if f is None:
        return {"error": f"No funder with id '{funder_id}'. Use search_funders to find the right id."}
    result = evaluate(company, f)
    if result["excluded"]:
        return {
            "funder_id": f["id"], "name": f["name"], "eligible": False,
            "ruled_out_by": result["reason"], "detail": result["detail"],
            "sources": f.get("source_urls"), "last_checked": f.get("last_checked"),
        }
    return {"eligible": True, **result}


@mcp.tool(annotations=READ_ONLY)
def score_found_funder(company: CompanyProfile, funder: FoundFunder) -> dict[str, Any]:
    """Score a funder that is NOT in the database, using criteria you read on its own website.

    Use this for any funder worldwide that match_company does not return: search the web, open the
    funder's official criteria page, fill in only what the page states (null otherwise), and pass
    the page URL in source_urls. The result is labelled unverified. Tell the user so, and suggest
    they propose the funder for the database on GitHub.
    """
    import datetime
    import re

    record = funder.model_dump()
    record["id"] = "found-" + re.sub(r"[^a-z0-9]+", "-", funder.name.lower()).strip("-")
    record["confidence"] = "unverified"
    record["verification_status"] = "found_online_not_in_database"
    record["last_checked"] = datetime.date.today().isoformat()
    record["notes"] = "Criteria read from the funder's website during this conversation; not yet reviewed."
    result = evaluate(company, record)
    if result["excluded"]:
        return {"name": funder.name, "eligible": False, "ruled_out_by": result["reason"],
                "detail": result["detail"], "sources": funder.source_urls, "data_status": "unverified"}
    return {"eligible": True, **result, "data_status": "unverified"}


@mcp.tool(annotations=READ_ONLY)
def financial_model_guide() -> dict[str, Any]:
    """How to collect assumptions for a financial model, with a complete worked example.

    Call this before project_financials when the company has no financial model. Ask the user for
    the assumptions in plain language (a few at a time), and fill opening balances and history from
    any accounts they upload. Rates are fractions (0.25 = 25%).
    """
    from .finmodel.assumptions import EXAMPLE

    return {
        "questions_to_ask": [
            "What do you sell? For each product: units sold last year (or expected in year 1), price per unit, expected growth in volume and price.",
            "Direct costs as a share of revenue (raw materials, direct labour), or the cost per unit.",
            "Other costs that rise with sales (commissions, transport), as a share of revenue.",
            "Fixed costs per year: salaries, rent, utilities, admin; and how fast each grows.",
            "Planned investment (equipment, buildings) by year, and how long the assets last.",
            "How many days customers take to pay, how many days of stock you hold, how many days you take to pay suppliers.",
            "Tax rate.",
            "Opening balance sheet: cash, receivables, inventory, net fixed assets, payables (from the latest accounts).",
            "Existing loans: balance, interest rate, years left.",
            "The funding sought: loan amount, rate, tenor, grace period, year drawn; or equity amount and year.",
            "Use of funds: what the money pays for, item by item.",
        ],
        "example_assumptions": EXAMPLE,
        "notes": "Per-year values can be one number or a list with one value per year. Unknown values: ask; "
                 "do not invent. Say clearly which numbers came from the user, which from documents, and "
                 "which are your suggested placeholders.",
    }


@mcp.tool(annotations=READ_ONLY)
def project_financials(assumptions: dict[str, Any]) -> dict[str, Any]:
    """Run a 3-statement projection (income statement, balance sheet, cash flow, debt schedule) from
    assumptions, then check whether the funding ask fits.

    Returns yearly figures, the funding analysis (how much the business really needs vs what it plans
    to raise, lowest cash, lowest debt service cover) and a funder-style review with findings.
    To give the user an editable Excel model, use the Investor-Fit skill's build_model.py script with
    the same assumptions; it writes formulas that produce these exact numbers.
    """
    from .finmodel.assumptions import AssumptionError
    from .finmodel.engine import funding_analysis, run
    from .finmodel.review import assess_projections, from_engine

    try:
        result = run(assumptions)
    except AssumptionError as e:
        return {"error": f"Assumptions need fixing: {e}"}
    r = lambda xs: [round(x, 2) if isinstance(x, (int, float)) else x for x in xs]  # noqa: E731
    is_, bs, cf = result["income_statement"], result["balance_sheet"], result["cash_flow"]
    return {
        "years": result["years"],
        "currency": result["assumptions"]["currency"],
        "income_statement": {k: r(is_[k]) for k in ("revenue", "gross_profit", "ebitda", "depreciation",
                                                       "interest", "tax", "net_income")},
        "balance_sheet": {k: r(bs[k]) for k in ("cash", "receivables", "inventory", "ppe_net", "total_assets",
                                                  "payables", "debt", "equity")},
        "cash_flow": {k: r(cf[k]) for k in ("operating", "investing", "financing")},
        "ratios": {k: r(v) for k, v in result["ratios"].items()},
        "funding_analysis": funding_analysis(assumptions),
        "review": assess_projections(from_engine(result)),
        "disclaimer": "Projections built from the company's own assumptions. Not audited; not financial advice.",
    }


@mcp.tool(annotations=READ_ONLY)
def review_projections(projections: dict[str, Any]) -> dict[str, Any]:
    """Funder-style review of the numbers in a company's OWN financial model.

    Read the user's model (or business plan) and pass the yearly series you find:
    {"currency", "years": [...], "revenue": [...], "ebitda": [...], "net_income": [...],
     "closing_cash": [...], "total_debt": [...], "debt_service": [... optional],
     "history": {"revenue": [...], "ebitda": [...]} (optional, actual past years),
     "ask": {"amount", "instrument": "debt" | "equity", "tenor_years", "interest_rate", "grace_years",
             "use_of_funds_total"},
     "min_dscr": 1.25}
    Use the exact figures from the file; leave out what is not there. Returns a verdict and findings
    (growth realism, margins, cash shortfalls, debt service cover, size of the ask, use of funds).
    For mechanical checks of the spreadsheet itself (errors, hardcoded numbers, broken formulas),
    run the Investor-Fit skill's review_model.py on the file.
    """
    from .finmodel.review import assess_projections

    try:
        return assess_projections(projections)
    except Exception as e:  # malformed input from the caller
        return {"error": f"Could not read the projections: {e}. Check that each series is a list of numbers."}


@mcp.tool(annotations=READ_ONLY)
def search_funders(
    country: Optional[str] = None,
    sector: Optional[SectorT] = None,
    instrument: Optional[InstrumentT] = None,
    funder_type: Optional[FunderTypeT] = None,
    text: Optional[str] = None,
) -> dict[str, Any]:
    """Browse the funder database without a company profile.

    All filters are optional. country is an ISO alpha-2 code (GH, NG, CI...). text searches funder
    names and notes. Returns short cards; call get_funder for the full record.
    """
    hits = data.search(country, sector, instrument, funder_type, text)
    return {"count": len(hits), "funders": [data.brief(f) for f in hits]}


@mcp.tool(annotations=READ_ONLY)
def get_funder(funder_id: str) -> dict[str, Any]:
    """Full record for one funder: criteria, requirements, how to apply, sources, confidence."""
    f = data.get_funder(funder_id)
    if f is None:
        return {"error": f"No funder with id '{funder_id}'. Use search_funders to find the right id."}
    return f


@mcp.tool(annotations=READ_ONLY)
def list_options() -> dict[str, Any]:
    """The allowed values for sector, stage and instruments, and database coverage.

    Call this if unsure how to map what the user said onto the profile fields.
    """
    funders = data.load_funders()
    return {
        "sectors": SECTORS,
        "stages": STAGE_HELP,
        "instruments_wanted": ["equity", "quasi_equity", "debt", "working_capital", "trade_finance", "guarantee", "grant"],
        "funder_types": FUNDER_TYPES,
        "database": {
            "funders": len(funders),
            "focus": "Verified core strongest for African SMEs and agribusiness; any other funder worldwide can be scored with score_found_funder",
            "last_checked": max(f.get("last_checked") or "" for f in funders),
        },
    }


MEMO_TEMPLATE = """\
# Investor-targeting memo: {company name}

**Company snapshot.** One or two lines: country, sector, stage, amount sought, instrument.

## Top matches
A table: Rank | Funder | Fit score | Readiness | Ticket range | Why it fits (one line)

## Funder notes
For each of the top 3-5 funders:
- Why it fits (use the score_breakdown reasons)
- Gaps and what would unlock them (from gaps[].unlock)
- How to apply / access route
- Source and last checked date; flag low-confidence data

## Readiness plan
The gaps that block the most funders, in the order to fix them, and which funders each fix unlocks.

## Ruled out
One line per exclusion reason with a count (from excluded_summary), so the user knows what was considered.

## Next steps
Three concrete actions for the next 30 days.

---
*{disclaimer from match_company}*
"""


@mcp.tool(annotations=READ_ONLY)
def memo_template() -> dict[str, str]:
    """The format for the final investor-targeting memo, with writing rules."""
    return {
        "template": MEMO_TEMPLATE,
        "rules": "Plain language for a founder, not jargon. Only funders from match_company. Keep fit "
                 "scores exactly as returned. Every funder named needs its source link.",
    }


@mcp.custom_route("/", methods=["GET"])
async def home(request):
    from starlette.responses import JSONResponse

    return JSONResponse({
        "name": "Investor-Fit Agent",
        "connect": "Add this server's /mcp URL as a custom connector in Claude (Customize > Connectors).",
        "funders": len(data.load_funders()),
        "source": "https://github.com/EMMANUEL-LAMPTEY-96/investor-fit",
    })


def http_app():
    """ASGI app for hosting (Vercel, Render, Hugging Face, a VPS...).

    Stateless, so any instance can answer any request. Some serverless hosts never send
    the ASGI startup event, so the session manager is also started on the first request.
    """
    import contextlib

    import anyio

    inner = mcp.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")
    stack = contextlib.AsyncExitStack()
    lock = anyio.Lock()
    started = False

    async def app(scope, receive, send):
        nonlocal started
        if scope["type"] == "lifespan":
            return await inner(scope, receive, send)
        if not started:
            async with lock:
                if not started and not mcp.session_manager._has_started:
                    await stack.enter_async_context(mcp.session_manager.run())
                started = True
        await inner(scope, receive, send)

    return app


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        import uvicorn

        uvicorn.run(http_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()

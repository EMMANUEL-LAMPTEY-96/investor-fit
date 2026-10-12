"""Call every tool over HTTP, the same way Claude does once the connector is added.

Usage: python scripts/smoke_test.py http://localhost:8000/mcp
"""

import asyncio
import json
import sys

from mcp.client import Client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"

COMPANY = {
    "name": "Sample cashew processor",
    "country": "GH",
    "sector": "agri_processing",
    "stage": "growth",
    "amount_usd": 500000,
    "instruments_wanted": ["working_capital"],
    "annual_revenue_usd": 1200000,
    "years_operating": 4,
    "audited_years": 1,
    "has_export_history": False,
    "has_export_order": True,
    "impact_focus": True,
}


def payload(result):
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


async def main() -> None:
    async with Client(URL) as client:
        tools = await client.list_tools()
        print("Tools:", ", ".join(t.name for t in tools.tools))

        r = payload(await client.call_tool("match_company", {"company": COMPANY, "top_n": 5}))
        print(f"\nmatch_company: {r['matches_found']} matches of {r['funders_screened']}; excluded {r['excluded_summary']}")
        for m in r["matches"]:
            print(f"  {m['rank']}. {m['fit_score']:>3}  {m['readiness']:<11} {m['name']}")

        r = payload(await client.call_tool("check_readiness", {"company": COMPANY, "funder_id": "shared-interest"}))
        print("\ncheck_readiness(shared-interest):", r["readiness"])
        for g in r["gaps"]:
            print(f"  - {g['requirement']}: {g['status']}" + (f" -> {g['unlock']}" if g["unlock"] else ""))

        r = payload(await client.call_tool("search_funders", {"country": "NG", "instrument": "equity"}))
        print("\nsearch_funders(NG, equity):", r["count"], "funders")

        r = payload(await client.call_tool("get_funder", {"funder_id": "root-capital"}))
        print("get_funder(root-capital):", r["name"], r["source_urls"][0])

        r = payload(await client.call_tool("list_options", {}))
        print("list_options:", r["database"])

        r = payload(await client.call_tool("memo_template", {}))
        print("memo_template:", r["template"].splitlines()[0])

        found = {"name": "Example Global Impact Lender", "type": "impact_lender", "geographies": ["emerging_markets"],
                 "sectors": ["agribusiness"], "instruments": ["working_capital"], "ticket_min_usd": 100000,
                 "ticket_max_usd": 2000000, "source_urls": ["https://example.org/criteria"]}
        r = payload(await client.call_tool("score_found_funder", {"company": COMPANY, "funder": found}))
        print("\nscore_found_funder:", r.get("fit_score"), r.get("readiness"), r.get("data_status"))

        guide = payload(await client.call_tool("financial_model_guide", {}))
        r = payload(await client.call_tool("project_financials", {"assumptions": guide["example_assumptions"]}))
        fa = r["funding_analysis"]
        print("project_financials: revenue", [round(x) for x in r["income_statement"]["revenue"]])
        print(f"  raising {fa['funding_raised']:,.0f}, need {fa['funding_need']:,.0f}, min DSCR {fa['min_dscr']:.2f}")
        print("  review:", r["review"]["verdict"])

        r = payload(await client.call_tool("review_projections", {"projections": {
            "years": [2027, 2028, 2029], "revenue": [100, 300, 900], "ebitda": [5, 40, 200],
            "net_income": [-5, 10, 120], "closing_cash": [-10, 20, 150], "total_debt": [50, 40, 30],
            "ask": {"amount": 50, "instrument": "debt", "use_of_funds_total": 30}}}))
        print("review_projections:", r["verdict"], r["counts"])


if __name__ == "__main__":
    asyncio.run(main())

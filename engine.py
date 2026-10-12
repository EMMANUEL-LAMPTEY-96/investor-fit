"""Three-statement projection engine.

Computes exactly what the Excel formulas compute, so the engine is both the source for the
agent's checks and the test that the spreadsheet formulas are right.

Conventions (also written on the workbook's Notes sheet):
- Annual periods. New debt is drawn at the start of its drawdown year; repayments at year end.
- Interest is charged on the balance outstanding during the year (opening balance plus any
  drawdown), which avoids circular references.
- Depreciation is straight line, a full year in the year of purchase.
- Tax is charged on positive profit only; losses are not carried forward (conservative).
- No dividends.
"""

from __future__ import annotations

from typing import Any

from .assumptions import normalize


def _debt_schedule(n, amount, rate, tenor, grace, draw_year):
    opening, draw, interest, repay, closing = [], [], [], [], []
    bal = 0.0
    repay_years = tenor - grace
    for t in range(1, n + 1):
        d = amount if t == draw_year else 0.0
        due = amount / repay_years if (draw_year + grace <= t <= draw_year + tenor - 1) and repay_years > 0 else 0.0
        r = min(bal + d, due)
        i = rate * (bal + d)
        opening.append(bal)
        draw.append(d)
        interest.append(i)
        repay.append(r)
        bal = bal + d - r
        closing.append(bal)
    return {"opening": opening, "drawdown": draw, "interest": interest, "repayment": repay, "closing": closing}


def _existing_schedule(n, balance, rate, remaining):
    opening, interest, repay, closing = [], [], [], []
    bal = balance
    for t in range(1, n + 1):
        due = balance / remaining if t <= remaining else 0.0
        r = min(bal, due)
        opening.append(bal)
        interest.append(rate * bal)
        repay.append(r)
        bal -= r
        closing.append(bal)
    return {"opening": opening, "interest": interest, "repayment": repay, "closing": closing}


def run(raw: dict[str, Any], *, include_new_funding: bool = True) -> dict[str, Any]:
    a = normalize(raw)
    n = a["years"]
    yrs = list(range(1, n + 1))

    # Revenue
    streams = []
    for s in a["revenue_streams"]:
        vol, price = [], []
        for t in yrs:
            if t == 1:
                vol.append(s["volume"])
                price.append(s["price"])
            else:
                vol.append(vol[-1] * (1 + s["volume_growth"][t - 1]))
                price.append(price[-1] * (1 + s["price_growth"][t - 1]))
        streams.append({"name": s["name"], "volume": vol, "price": price,
                        "revenue": [v * p for v, p in zip(vol, price)]})
    revenue = [sum(s["revenue"][i] for s in streams) for i in range(n)]

    cogs = [revenue[i] * a["cogs_pct_revenue"][i] for i in range(n)]
    gross = [revenue[i] - cogs[i] for i in range(n)]
    var_opex = [revenue[i] * a["variable_opex_pct_revenue"][i] for i in range(n)]
    fixed = []
    for f in a["fixed_costs"]:
        vals = []
        for t in yrs:
            vals.append(f["amount"] if t == 1 else vals[-1] * (1 + f["growth"][t - 1]))
        fixed.append({"name": f["name"], "amounts": vals})
    fixed_total = [sum(f["amounts"][i] for f in fixed) for i in range(n)]
    ebitda = [gross[i] - var_opex[i] - fixed_total[i] for i in range(n)]

    # Capex and depreciation
    capex_total = [sum(c["amounts"][i] for c in a["capex"]) for i in range(n)]
    L = a["depreciation_years"]
    ob = a["opening_balance"]
    dep_existing = [ob["ppe_net"] / a["existing_ppe_remaining_years"] if t <= a["existing_ppe_remaining_years"] else 0.0
                    for t in yrs]
    dep_new = [sum(capex_total[k - 1] for k in yrs if k <= t and t - k < L) / L for t in yrs]
    dep = [dep_existing[i] + dep_new[i] for i in range(n)]
    ebit = [ebitda[i] - dep[i] for i in range(n)]

    # Debt
    ed = a["existing_debt"]
    ex = _existing_schedule(n, ed["balance"], ed["interest_rate"], ed["remaining_years"])
    nd = a["new_debt"]
    amt = nd["amount"] if include_new_funding else 0.0
    new = _debt_schedule(n, amt, nd["interest_rate"], nd["tenor_years"], nd["grace_years"], nd["drawdown_year"])
    interest = [ex["interest"][i] + new["interest"][i] for i in range(n)]

    ebt = [ebit[i] - interest[i] for i in range(n)]
    tax = [max(0.0, ebt[i]) * a["tax_rate"] for i in range(n)]
    net_income = [ebt[i] - tax[i] for i in range(n)]

    # Working capital
    ar = [revenue[i] * a["receivable_days"] / 365 for i in range(n)]
    inv = [cogs[i] * a["inventory_days"] / 365 for i in range(n)]
    ap = [cogs[i] * a["payable_days"] / 365 for i in range(n)]

    ne = a["new_equity"]
    equity_in = [(ne["amount"] if (include_new_funding and t == ne["year"]) else 0.0) for t in yrs]

    # Cash flow and balance sheet
    open_equity = ob["cash"] + ob["receivables"] + ob["inventory"] + ob["ppe_net"] - ob["payables"] - ed["balance"]
    cash, ppe, equity = [], [], []
    cfo, cfi, cff, d_ar, d_inv, d_ap = [], [], [], [], [], []
    prev_cash, prev_ar, prev_inv, prev_ap, prev_ppe, prev_eq = (
        ob["cash"], ob["receivables"], ob["inventory"], ob["payables"], ob["ppe_net"], open_equity)
    for i in range(n):
        d_ar.append(ar[i] - prev_ar)
        d_inv.append(inv[i] - prev_inv)
        d_ap.append(ap[i] - prev_ap)
        cfo.append(net_income[i] + dep[i] - d_ar[i] - d_inv[i] + d_ap[i])
        cfi.append(-capex_total[i])
        cff.append(new["drawdown"][i] - new["repayment"][i] - ex["repayment"][i] + equity_in[i])
        c = prev_cash + cfo[i] + cfi[i] + cff[i]
        p = prev_ppe + capex_total[i] - dep[i]
        e = prev_eq + equity_in[i] + net_income[i]
        cash.append(c); ppe.append(p); equity.append(e)
        prev_cash, prev_ar, prev_inv, prev_ap, prev_ppe, prev_eq = c, ar[i], inv[i], ap[i], p, e

    debt = [ex["closing"][i] + new["closing"][i] for i in range(n)]
    total_assets = [cash[i] + ar[i] + inv[i] + ppe[i] for i in range(n)]
    total_le = [ap[i] + debt[i] + equity[i] for i in range(n)]
    balance_check = [round(total_assets[i] - total_le[i], 6) for i in range(n)]

    debt_service = [interest[i] + new["repayment"][i] + ex["repayment"][i] for i in range(n)]
    dscr = [((ebitda[i] - tax[i]) / debt_service[i]) if debt_service[i] > 0 else None for i in range(n)]

    def pct(a_, b_):
        return [(x / y) if y else None for x, y in zip(a_, b_)]

    return {
        "assumptions": a,
        "years": [a["first_year"] + i for i in range(n)],
        "income_statement": {
            "revenue_by_stream": {s["name"]: s["revenue"] for s in streams},
            "revenue": revenue, "cogs": cogs, "gross_profit": gross, "variable_opex": var_opex,
            "fixed_costs": {f["name"]: f["amounts"] for f in fixed}, "fixed_costs_total": fixed_total,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit, "interest": interest, "ebt": ebt,
            "tax": tax, "net_income": net_income,
        },
        "balance_sheet": {
            "cash": cash, "receivables": ar, "inventory": inv, "ppe_net": ppe, "total_assets": total_assets,
            "payables": ap, "debt": debt, "equity": equity, "total_liabilities_equity": total_le,
            "balance_check": balance_check, "opening_equity": open_equity,
        },
        "cash_flow": {
            "operating": cfo, "investing": cfi, "financing": cff, "change_receivables": d_ar,
            "change_inventory": d_inv, "change_payables": d_ap, "capex": capex_total,
            "new_debt_drawdown": new["drawdown"], "new_debt_repayment": new["repayment"],
            "existing_debt_repayment": ex["repayment"], "equity_injection": equity_in, "closing_cash": cash,
        },
        "debt": {"new": new, "existing": ex},
        "ratios": {
            "revenue_growth": [None] + [(revenue[i] / revenue[i - 1] - 1) if revenue[i - 1] else None for i in range(1, n)],
            "gross_margin": pct(gross, revenue), "ebitda_margin": pct(ebitda, revenue),
            "net_margin": pct(net_income, revenue), "dscr": dscr,
            "net_debt_to_ebitda": [((debt[i] - cash[i]) / ebitda[i]) if ebitda[i] > 0 else None for i in range(n)],
        },
    }


def funding_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    """How much money the business actually needs, compared with what it plans to raise."""
    base = run(raw)
    a = base["assumptions"]
    without = run(raw, include_new_funding=False)
    min_cash_without = min(without["balance_sheet"]["cash"])
    worst_year = base["years"][without["balance_sheet"]["cash"].index(min_cash_without)]
    need = max(0.0, a["minimum_cash"] - min_cash_without)
    raised = a["new_debt"]["amount"] + a["new_equity"]["amount"]
    uof = sum(u["amount"] for u in a["use_of_funds"])
    dscr = [d for d in base["ratios"]["dscr"] if d is not None]
    min_cash_with = min(base["balance_sheet"]["cash"])
    return {
        "funding_raised": raised,
        "funding_need": need,
        "funding_need_year": worst_year if need > 0 else None,
        "lowest_cash_without_new_funding": min_cash_without,
        "lowest_cash_with_new_funding": min_cash_with,
        "use_of_funds_total": uof,
        "use_of_funds_gap": raised - uof,
        "min_dscr": min(dscr) if dscr else None,
        "min_dscr_year": base["years"][base["ratios"]["dscr"].index(min(dscr))] if dscr else None,
        "dscr_threshold": a["minimum_dscr"],
        "balance_sheet_balances": all(abs(x) < 0.01 for x in base["balance_sheet"]["balance_check"]),
    }

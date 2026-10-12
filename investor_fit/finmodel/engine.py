"""Three-statement projection engine.

Computes exactly what the Excel formulas compute, so the engine is both the source for the
agent's checks and the test that the spreadsheet formulas are right.

Conventions (also written on the workbook's Cover sheet):
- Annual periods. New debt is drawn at the start of its drawdown year; repayments at year end.
- Interest is charged on the balance outstanding during the year (opening balance plus any
  drawdown), which avoids circular references.
- Depreciation is straight line, a full year in the year of purchase.
- Tax is charged on positive profit only; losses are not carried forward (conservative).
- No dividends.
- Foreign currency: the rate starts at fx.rate, falls by any scenario devaluation in year 1, then
  by fx.depreciation each year. Sales, interest and repayments use each year's rate; a loan drawn
  at the start of a year converts at the opening rate. The balance outstanding is revalued each
  year; the change is an exchange loss (or gain) in the income statement, which is not cash and is
  added back in the cash flow.
"""

from __future__ import annotations

from typing import Any

from .assumptions import SHOCK_KEYS, normalize


def _schedule(n, amount, rate, tenor, grace, draw_year):
    """New loan, in its own currency."""
    opening, draw, interest, repay, closing = [], [], [], [], []
    bal = 0.0
    repay_years = tenor - grace
    for t in range(1, n + 1):
        d = amount if t == draw_year else 0.0
        due = amount / repay_years if (draw_year + grace <= t <= draw_year + tenor - 1) and repay_years > 0 else 0.0
        r = min(bal + d, due)
        opening.append(bal)
        draw.append(d)
        interest.append(rate * (bal + d))
        repay.append(r)
        bal = bal + d - r
        closing.append(bal)
    return {"opening": opening, "drawdown": draw, "interest": interest, "repayment": repay, "closing": closing}


def _existing(n, balance, rate, remaining):
    """Existing debt, in its own currency."""
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
    return {"opening": opening, "drawdown": [0.0] * n, "interest": interest, "repayment": repay, "closing": closing}


def _to_local(sched, f, f0):
    """Convert a loan schedule to local currency.

    Drawdowns happen at the start of the year, so they convert at the opening rate. Interest and
    repayments are paid during the year at that year's rate. The balance outstanding during the
    year is revalued from the opening to the closing rate; the difference is the FX loss.
    """
    n = len(sched["opening"])
    prev = [f0] + f[:-1]
    out = {k: [sched[k][i] * f[i] for i in range(n)] for k in ("interest", "repayment", "closing")}
    out["drawdown"] = [sched["drawdown"][i] * prev[i] for i in range(n)]
    out["fx_loss"] = [(sched["opening"][i] + sched["drawdown"][i]) * (f[i] - prev[i]) for i in range(n)]
    out["opening_local"] = sched["opening"][0] * f0
    return out


def resolve_shocks(a: dict, scenario: str = "base", shocks: dict | None = None) -> dict[str, float]:
    if shocks is not None:
        return {k: float(shocks.get(k, 0) or 0) for k in SHOCK_KEYS}
    if scenario not in a["scenarios"]:
        raise ValueError(f"unknown scenario '{scenario}'; available: {', '.join(a['scenarios'])}")
    return dict(a["scenarios"][scenario])


def run(raw: dict[str, Any], *, include_new_funding: bool = True, scenario: str = "base",
        shocks: dict | None = None) -> dict[str, Any]:
    a = normalize(raw)
    sh = resolve_shocks(a, scenario, shocks)
    n = a["years"]
    yrs = list(range(1, n + 1))
    home = a["currency"]

    # Exchange rate: local units per 1 foreign unit
    spot = a["fx"]["rate"]
    fx_rate = []
    for t in yrs:
        prev = spot if t == 1 else fx_rate[-1]
        fx_rate.append(prev * (1 + (sh["fx_devaluation"] if t == 1 else 0)) * (1 + a["fx"]["depreciation"][t - 1]))

    def factor(ccy):
        return [1.0] * n if ccy == home else fx_rate

    def factor0(ccy):
        return 1.0 if ccy == home else spot

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
        f = factor(s["currency"])
        rev = [vol[i] * (1 + sh["volume"]) * price[i] * (1 + sh["price"]) * f[i] for i in range(n)]
        streams.append({"name": s["name"], "currency": s["currency"], "volume": vol, "price": price, "revenue": rev})
    revenue = [sum(s["revenue"][i] for s in streams) for i in range(n)]

    cogs = [revenue[i] * (a["cogs_pct_revenue"][i] + sh["cogs_pts"]) for i in range(n)]
    gross = [revenue[i] - cogs[i] for i in range(n)]
    var_opex = [revenue[i] * a["variable_opex_pct_revenue"][i] for i in range(n)]
    fixed = []
    for fc in a["fixed_costs"]:
        vals = []
        for t in yrs:
            vals.append(fc["amount"] if t == 1 else vals[-1] * (1 + fc["growth"][t - 1]))
        fixed.append({"name": fc["name"], "amounts": [v * (1 + sh["fixed_costs"]) for v in vals]})
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

    # Debt (schedules in loan currency, then converted)
    ed, nd = a["existing_debt"], a["new_debt"]
    ex_fc = _existing(n, ed["balance"], max(0.0, ed["interest_rate"] + sh["interest_pts"]), ed["remaining_years"])
    amt = nd["amount"] if include_new_funding else 0.0
    new_fc = _schedule(n, amt, max(0.0, nd["interest_rate"] + sh["interest_pts"]), nd["tenor_years"],
                       nd["grace_years"], nd["drawdown_year"])
    ex = _to_local(ex_fc, factor(ed["currency"]), factor0(ed["currency"]))
    new = _to_local(new_fc, factor(nd["currency"]), factor0(nd["currency"]))
    interest = [ex["interest"][i] + new["interest"][i] for i in range(n)]
    fx_loss = [ex["fx_loss"][i] + new["fx_loss"][i] for i in range(n)]

    ebt = [ebit[i] - interest[i] - fx_loss[i] for i in range(n)]
    tax = [max(0.0, ebt[i]) * a["tax_rate"] for i in range(n)]
    net_income = [ebt[i] - tax[i] for i in range(n)]

    # Working capital
    ar = [revenue[i] * (a["receivable_days"] + sh["receivable_days"]) / 365 for i in range(n)]
    inv = [cogs[i] * a["inventory_days"] / 365 for i in range(n)]
    ap = [cogs[i] * a["payable_days"] / 365 for i in range(n)]

    ne = a["new_equity"]
    equity_in = [(ne["amount"] if (include_new_funding and t == ne["year"]) else 0.0) for t in yrs]

    # Cash flow and balance sheet
    open_debt = ex["opening_local"]
    open_equity = ob["cash"] + ob["receivables"] + ob["inventory"] + ob["ppe_net"] - ob["payables"] - open_debt
    cash, ppe, equity = [], [], []
    cfo, cfi, cff, d_ar, d_inv, d_ap = [], [], [], [], [], []
    prev_cash, prev_ar, prev_inv, prev_ap, prev_ppe, prev_eq = (
        ob["cash"], ob["receivables"], ob["inventory"], ob["payables"], ob["ppe_net"], open_equity)
    for i in range(n):
        d_ar.append(ar[i] - prev_ar)
        d_inv.append(inv[i] - prev_inv)
        d_ap.append(ap[i] - prev_ap)
        cfo.append(net_income[i] + dep[i] + fx_loss[i] - d_ar[i] - d_inv[i] + d_ap[i])
        cfi.append(-capex_total[i])
        cff.append(new["drawdown"][i] - new["repayment"][i] - ex["repayment"][i] + equity_in[i])
        c = prev_cash + cfo[i] + cfi[i] + cff[i]
        p = prev_ppe + capex_total[i] - dep[i]
        e = prev_eq + equity_in[i] + net_income[i]
        cash.append(c)
        ppe.append(p)
        equity.append(e)
        prev_cash, prev_ar, prev_inv, prev_ap, prev_ppe, prev_eq = c, ar[i], inv[i], ap[i], p, e

    debt = [ex["closing"][i] + new["closing"][i] for i in range(n)]
    total_assets = [cash[i] + ar[i] + inv[i] + ppe[i] for i in range(n)]
    total_le = [ap[i] + debt[i] + equity[i] for i in range(n)]
    balance_check = [round(total_assets[i] - total_le[i], 6) for i in range(n)]

    principal = [new["repayment"][i] + ex["repayment"][i] for i in range(n)]
    debt_service = [interest[i] + principal[i] for i in range(n)]
    dscr = [((ebitda[i] - tax[i]) / debt_service[i]) if debt_service[i] > 0 else None for i in range(n)]

    def pct(a_, b_):
        return [(x / y) if y else None for x, y in zip(a_, b_)]

    return {
        "assumptions": a,
        "scenario": scenario if shocks is None else "custom",
        "shocks": sh,
        "years": [a["first_year"] + i for i in range(n)],
        "currency": home,
        "fx_rate": fx_rate if a["foreign_currency"] else None,
        "income_statement": {
            "revenue_by_stream": {s["name"]: s["revenue"] for s in streams},
            "revenue": revenue, "cogs": cogs, "gross_profit": gross, "variable_opex": var_opex,
            "fixed_costs": {f["name"]: f["amounts"] for f in fixed}, "fixed_costs_total": fixed_total,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit, "interest": interest, "fx_loss": fx_loss,
            "ebt": ebt, "tax": tax, "net_income": net_income,
        },
        "balance_sheet": {
            "cash": cash, "receivables": ar, "inventory": inv, "ppe_net": ppe, "total_assets": total_assets,
            "payables": ap, "debt": debt, "equity": equity, "total_liabilities_equity": total_le,
            "balance_check": balance_check, "opening_equity": open_equity, "opening_debt": open_debt,
        },
        "cash_flow": {
            "operating": cfo, "investing": cfi, "financing": cff, "change_receivables": d_ar,
            "change_inventory": d_inv, "change_payables": d_ap, "capex": capex_total,
            "new_debt_drawdown": new["drawdown"], "new_debt_repayment": new["repayment"],
            "existing_debt_repayment": ex["repayment"], "equity_injection": equity_in, "closing_cash": cash,
        },
        "debt": {"new": new, "existing": ex, "new_in_loan_currency": new_fc, "existing_in_loan_currency": ex_fc,
                 "interest": interest, "principal": principal, "debt_service": debt_service},
        "ratios": {
            "revenue_growth": [None] + [(revenue[i] / revenue[i - 1] - 1) if revenue[i - 1] else None for i in range(1, n)],
            "gross_margin": pct(gross, revenue), "ebitda_margin": pct(ebitda, revenue),
            "net_margin": pct(net_income, revenue), "dscr": dscr,
            "net_debt_to_ebitda": [((debt[i] - cash[i]) / ebitda[i]) if ebitda[i] > 0 else None for i in range(n)],
        },
    }


def key_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """The few numbers lenders look at first, for one run."""
    a = result["assumptions"]
    dscr = [d for d in result["ratios"]["dscr"] if d is not None]
    cash = result["balance_sheet"]["cash"]
    years = result["years"]
    low_years = [years[i] for i, d in enumerate(result["ratios"]["dscr"]) if d is not None and d < a["minimum_dscr"]]
    return {
        "min_dscr": min(dscr) if dscr else None,
        "min_dscr_year": years[result["ratios"]["dscr"].index(min(dscr))] if dscr else None,
        "years_below_dscr_minimum": low_years,
        "lowest_cash": min(cash),
        "lowest_cash_year": years[cash.index(min(cash))],
        "cash_below_minimum": min(cash) < a["minimum_cash"],
        "final_year_net_income": result["income_statement"]["net_income"][-1],
        "total_fx_loss": sum(result["income_statement"]["fx_loss"]),
        "final_year_revenue": result["income_statement"]["revenue"][-1],
    }


def funding_analysis(raw: dict[str, Any], scenario: str = "base") -> dict[str, Any]:
    """How much money the business actually needs, compared with what it plans to raise."""
    base = run(raw, scenario=scenario)
    a = base["assumptions"]
    without = run(raw, include_new_funding=False, scenario=scenario)
    min_cash_without = min(without["balance_sheet"]["cash"])
    worst_year = base["years"][without["balance_sheet"]["cash"].index(min_cash_without)]
    need = max(0.0, a["minimum_cash"] - min_cash_without)
    nd = a["new_debt"]
    loan_local_at_start = nd["amount"] * (a["fx"]["rate"] if nd["currency"] != a["currency"] else 1.0)
    raised = loan_local_at_start + a["new_equity"]["amount"]
    uof = sum(u["amount"] for u in a["use_of_funds"])
    m = key_metrics(base)
    return {
        "currency": a["currency"],
        "funding_raised": raised,
        "funding_raised_note": (f"loan of {nd['amount']:,.0f} {nd['currency']} converted at {a['fx']['rate']:g}"
                                if nd["currency"] != a["currency"] else None),
        "funding_need": need,
        "funding_need_year": worst_year if need > 0 else None,
        "lowest_cash_without_new_funding": min_cash_without,
        "lowest_cash_with_new_funding": m["lowest_cash"],
        "use_of_funds_total": uof,
        "use_of_funds_gap": raised - uof,
        "min_dscr": m["min_dscr"],
        "min_dscr_year": m["min_dscr_year"],
        "dscr_threshold": a["minimum_dscr"],
        "balance_sheet_balances": all(abs(x) < 0.01 for x in base["balance_sheet"]["balance_check"]),
    }

"""Turn the evidence from a company's documents into model assumptions.

Every assumption gets an entry in a register saying where it came from:
  document      read directly from a document (file and page)
  derived       calculated from document figures (the method is stated)
  user          given by the user (answers)
  suggested     a reasonable default the agent proposes; the user should confirm it
  placeholder   unknown; used only when the user has agreed to build with placeholders

Anything the documents cannot answer becomes a question. Unless placeholders are allowed, the
model is not built until the questions are answered, so the agent first works through them with
the user.
"""

from __future__ import annotations

import copy
from typing import Any

from ..evidence import Evidence


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def derive(evidence: dict[str, Any], answers: dict[str, Any] | None = None,
           allow_placeholders: bool = False, years: int = 5) -> dict[str, Any]:
    ev = Evidence(evidence)
    answers = answers or {}
    hist = ev.periods()
    register: list[dict] = []
    questions: list[dict] = []
    a: dict[str, Any] = {}

    def reg(field, label, value, origin, source=None, method=None):
        register.append({"field": field, "label": label, "value": value, "origin": origin,
                         "source": source, "method": method,
                         "confirm": origin in ("suggested", "placeholder", "derived")})

    def ask(field, question, why, placeholder):
        questions.append({"field": field, "question": question, "why": why, "placeholder": placeholder})

    ccy = ev.currency or "USD"
    a["company_name"] = evidence.get("company") or "Company"
    a["currency"] = ccy
    a["years"] = years
    if not hist:
        return {"status": "needs_documents", "assumptions": None, "register": [], "history": {},
                "questions": [{"field": "history", "question": "Please share the last 2–3 years of financial statements.",
                               "why": "There are no historical figures to build from.", "placeholder": None}]}

    L = hist[-1]
    P = hist[-2] if len(hist) > 1 else None
    g = lambda m, p=L: ev.get(m, p)  # noqa: E731
    src = lambda m, p=L: ev.source(m, p)  # noqa: E731
    a["first_year"] = int(L[:4]) + 1
    reg("first_year", "First projection year", a["first_year"], "derived", src("revenue"), f"year after the latest accounts ({L})")

    # ---------------------------------------------------------------- revenue
    rev = g("revenue")
    revs = [(p, ev.get("revenue", p)) for p in hist if ev.get("revenue", p)]
    growth = None
    if len(revs) >= 2 and revs[0][1] > 0:
        n = len(revs) - 1
        growth = (revs[-1][1] / revs[0][1]) ** (1 / n) - 1
        capped = _clip(growth, -0.10, 0.30)
        method = f"average yearly growth {revs[0][0]}–{revs[-1][0]} ({growth:.1%})" + (
            f", capped at {capped:.0%}" if capped != growth else "")
        growth = capped
        growth_origin = "derived"
    vol, price = g("volume_sold"), g("average_price")
    if vol and price:
        stream = {"name": "Sales", "unit": "units", "volume": vol, "price": price,
                  "volume_growth": growth if growth is not None else 0.0, "price_growth": 0.0}
        reg("revenue_streams[0].volume", "Year-1 volume (last actual)", vol, "document", src("volume_sold"))
        reg("revenue_streams[0].price", "Year-1 price (last actual)", price, "document", src("average_price"))
    elif rev:
        stream = {"name": "Sales (total; no volume data)", "unit": "year", "volume": 1, "volume_growth": 0.0,
                  "price": None, "price_growth": None}
    else:
        stream = None
        ask("revenue_streams", "What were sales in the latest year, and what do you sell?",
            "No revenue figure was found.", None)
    if stream is not None:
        if growth is None:
            ask("growth", f"How fast do you expect sales to grow? There is only one year of history ({L}).",
                "Growth cannot be measured from a single year.", 0.05)
        if stream["price"] is None:  # total-sales stream: year-1 value = last revenue grown once
            gr = growth if growth is not None else None
            if gr is not None:
                stream["price"] = rev * (1 + gr)
                stream["price_growth"] = gr
                reg("revenue_streams[0].price", "Year-1 sales", round(stream["price"]), "derived", src("revenue"),
                    f"{L} revenue {rev:,.0f} grown by {gr:.1%}")
                reg("revenue_streams[0].price_growth", "Sales growth per year", round(gr, 4), growth_origin,
                    src("revenue"), method)
        elif growth is not None:
            reg("revenue_streams[0].volume_growth", "Volume growth per year", round(growth, 4), growth_origin,
                src("revenue"), method)
        a["revenue_streams"] = [stream]

    # ---------------------------------------------------------------- costs
    ratios = []
    for p in hist[-2:]:
        r_, c_, gp_ = ev.get("revenue", p), ev.get("cogs", p), ev.get("gross_profit", p)
        if r_ and c_ is None and gp_ is not None:
            c_ = r_ - gp_
        if r_ and c_ is not None:
            ratios.append(c_ / r_)
    if ratios:
        a["cogs_pct_revenue"] = round(sum(ratios) / len(ratios), 4)
        reg("cogs_pct_revenue", "Direct costs, % of revenue", a["cogs_pct_revenue"], "derived", src("cogs"),
            f"average of {', '.join(f'{x:.1%}' for x in ratios)} ({', '.join(hist[-len(ratios):])})")
    else:
        ask("cogs_pct_revenue", "What share of sales goes on direct costs (raw materials, direct labour)?",
            "No cost of sales found in the documents.", 0.6)

    opex = g("operating_expenses")
    if opex is not None:
        gp = g("gross_profit") if g("gross_profit") is not None else (rev - g("cogs") if rev and g("cogs") is not None else None)
        dep, intr, pbt = g("depreciation") or 0, g("interest") or 0, g("profit_before_tax")
        includes_dep = False
        if g("ebitda") is not None and gp is not None:
            opex_ex = gp - g("ebitda")
            how = "gross profit − EBITDA"
        else:
            if gp is not None and pbt is not None and dep:
                excl = abs(gp - opex - dep - intr - pbt)
                incl = abs(gp - opex - intr - pbt)
                includes_dep = incl < excl
            opex_ex = opex - dep if includes_dep else opex
            how = "operating expenses less depreciation" if includes_dep else "operating expenses (depreciation shown separately)"
        og = None
        if P and ev.get("operating_expenses", P):
            og = _clip(opex / ev.get("operating_expenses", P) - 1, 0.0, 0.25)
        gr_o = og if og is not None else 0.08
        a["fixed_costs"] = [{"name": "Operating costs", "amount": round(opex_ex * (1 + gr_o)), "growth": round(gr_o, 4)}]
        reg("fixed_costs[0].amount", "Year-1 operating costs", a["fixed_costs"][0]["amount"], "derived",
            src("operating_expenses"), f"{L} {how} {opex_ex:,.0f} grown by {gr_o:.1%}")
        reg("fixed_costs[0].growth", "Operating cost growth per year", round(gr_o, 4),
            "derived" if og is not None else "suggested", src("operating_expenses"),
            f"growth {P}–{L}, capped 0–25%" if og is not None else "8% a year; confirm with the company")
    else:
        ask("fixed_costs", "What are the yearly operating costs (salaries, rent, utilities, admin)?",
            "No operating expenses found.", None)
    a["variable_opex_pct_revenue"] = 0.0

    # ---------------------------------------------------------------- assets, depreciation, working capital
    ppe, dep = g("ppe_net"), g("depreciation")
    if ppe and dep:
        life = int(_clip(round(ppe / dep), 1, 30))
        a["existing_ppe_remaining_years"] = life
        reg("existing_ppe_remaining_years", "Remaining life of existing assets", life, "derived", src("ppe_net"),
            f"net fixed assets {ppe:,.0f} ÷ depreciation {dep:,.0f}")
    a["depreciation_years"] = 10
    reg("depreciation_years", "Life of new equipment", 10, "suggested", None, "10 years; adjust to the asset type")
    cogs_L = g("cogs") if g("cogs") is not None else (rev - g("gross_profit") if rev and g("gross_profit") is not None else None)
    for key, m, base, label in (("receivable_days", "receivables", rev, "Customer payment days"),
                                ("inventory_days", "inventory", cogs_L, "Stock days"),
                                ("payable_days", "payables", cogs_L, "Supplier payment days")):
        v = g(m)
        if v is not None and base:
            a[key] = round(v / base * 365)
            reg(key, label, a[key], "derived", src(m), f"{m} {v:,.0f} ÷ {'revenue' if m == 'receivables' else 'direct costs'} {base:,.0f} × 365")
        else:
            ask(key, f"{label}: roughly how many days?", f"No {m} figure found.", 30)

    pbt, tax = g("profit_before_tax"), g("tax")
    if pbt and tax is not None and pbt > 0 and 0 <= tax / pbt < 0.6:
        a["tax_rate"] = round(tax / pbt, 4)
        reg("tax_rate", "Tax rate", a["tax_rate"], "derived", src("tax"), f"tax {tax:,.0f} ÷ profit before tax {pbt:,.0f}")
    else:
        ask("tax_rate", "What corporate tax rate applies to the company?", "The accounts do not give a usable rate.", 0.25)

    # ---------------------------------------------------------------- opening balance sheet and debt
    ob = {}
    for key, m in (("cash", "cash"), ("receivables", "receivables"), ("inventory", "inventory"),
                   ("ppe_net", "ppe_net"), ("payables", "payables")):
        v = g(m)
        if v is not None:
            ob[key] = v
            reg(f"opening_balance.{key}", f"Opening {m.replace('_', ' ')}", v, "document", src(m), f"{L} balance sheet")
        else:
            ob[key] = 0
            ask(f"opening_balance.{key}", f"What was {m.replace('_', ' ')} at the end of {L}?", "Not found in the balance sheet.", 0)
    a["opening_balance"] = ob

    debt = g("total_debt") or 0
    a["existing_debt"] = {"balance": debt, "currency": ccy}
    if debt > 0:
        reg("existing_debt.balance", "Existing debt", debt, "document", src("total_debt"), f"{L} balance sheet")
        intr = g("interest")
        avg = (debt + (ev.get("total_debt", P) or debt)) / 2 if P else debt
        if intr and avg:
            a["existing_debt"]["interest_rate"] = round(intr / avg, 4)
            reg("existing_debt.interest_rate", "Interest rate on existing debt", round(intr / avg, 4), "derived",
                src("interest"), f"interest {intr:,.0f} ÷ average debt {avg:,.0f}; confirm against the loan agreement")
        else:
            ask("existing_debt.interest_rate", "What interest rate do you pay on existing loans?", "Not derivable.", 0.2)
        ask("existing_debt.remaining_years", "How many years are left on the existing loans?",
            "The documents give the balance but not the repayment schedule.", 3)
    else:
        a["existing_debt"].update(interest_rate=0, remaining_years=1)

    # ---------------------------------------------------------------- what the company wants (only the user knows)
    ask("new_debt", "How much are you raising, as a loan or equity, in which currency, and on what terms "
        "(rate, tenor, grace period, year drawn)?", "Funding plans are not in the historical documents.",
        {"amount": 0, "interest_rate": 0, "tenor_years": 5, "grace_years": 0, "drawdown_year": 1})
    ask("use_of_funds", "What will the money pay for, item by item?", "Funders always ask.", [])
    ask("capex", "Do you plan any investment in equipment or buildings in the next five years? When, and how much?",
        "Investment plans change depreciation and cash.", [])

    a["minimum_dscr"] = 1.25
    reg("minimum_dscr", "Lender's minimum debt cover", 1.25, "suggested", None, "common lender test; use the funder's figure if known")
    monthly_costs = ((cogs_L or 0) + (opex or 0)) / 12
    a["minimum_cash"] = round(monthly_costs)
    reg("minimum_cash", "Minimum cash to keep", a["minimum_cash"], "suggested", None, "one month of costs")

    # ---------------------------------------------------------------- apply the user's answers
    flat_answers = _flatten(answers)
    a = _deep_merge(a, answers)
    for k, v in flat_answers.items():
        register[:] = [r for r in register if not (r["field"] == k or r["field"].startswith(k + "."))]
        reg(k, k.replace("_", " ").replace(".", ": "), v, "user", "answer from the user")

    def answered(field):
        top = field.split(".")[0]
        if field in flat_answers or top in answers:
            return True
        if field == "growth":
            return "revenue_streams" in answers
        return False

    open_q = [q for q in questions if not answered(q["field"])]
    if open_q and not allow_placeholders:
        return {"status": "needs_input", "assumptions": None, "register": register, "questions": open_q,
                "history": history_table(ev, hist)}

    for q in open_q:
        if q["placeholder"] is None:
            return {"status": "needs_input", "assumptions": None, "register": register,
                    "questions": [x for x in open_q if x["placeholder"] is None], "history": history_table(ev, hist),
                    "note": "These cannot be filled with a placeholder."}
        f = q["field"]
        if f == "growth":
            st = a["revenue_streams"][0]
            if st["price"] is None:
                st["price"], st["price_growth"] = rev * (1 + q["placeholder"]), q["placeholder"]
            else:
                st["volume_growth"] = q["placeholder"]
        elif "." in f:
            top, sub = f.split(".", 1)
            a.setdefault(top, {})[sub] = q["placeholder"]
        else:
            a[f] = q["placeholder"]
        reg(f, f.replace("_", " ").replace(".", ": "), q["placeholder"], "placeholder", None, q["question"])

    return {"status": "ready", "assumptions": a, "register": register,
            "questions": open_q if allow_placeholders else [], "history": history_table(ev, hist),
            "placeholders_used": [q["field"] for q in open_q]}


HISTORY_ROWS = ["revenue", "cogs", "gross_profit", "operating_expenses", "ebitda", "depreciation", "interest",
                "profit_before_tax", "tax", "net_income", "cash", "receivables", "inventory", "ppe_net",
                "total_assets", "payables", "total_debt", "equity"]


def history_table(ev: Evidence, hist: list[str]) -> dict[str, Any]:
    rows = []
    for m in HISTORY_ROWS:
        vals = [ev.get(m, p) for p in hist]
        if any(v is not None for v in vals):
            rows.append({"metric": m, "values": vals, "sources": [ev.source(m, p) for p in hist]})
    return {"periods": hist, "rows": rows}

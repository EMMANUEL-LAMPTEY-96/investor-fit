"""Scenarios, stress tests, breaking points and loan structuring.

All results come from re-running the engine with different shocks, so they are exact for the
model's own logic (and the Excel model shows the same numbers when its scenario selector is set).
"""

from __future__ import annotations

import copy
from typing import Any

from .engine import key_metrics, run

# One shock at a time. Labels are written for a founder.
STRESS_TESTS: list[tuple[str, dict[str, float]]] = [
    ("Selling prices 10% lower", {"price": -0.10}),
    ("Volumes 20% lower", {"volume": -0.20}),
    ("Direct costs up 5 points of revenue", {"cogs_pts": 0.05}),
    ("Fixed costs 10% higher", {"fixed_costs": 0.10}),
    ("Customers pay 30 days later", {"receivable_days": 30}),
    ("Interest rates up 3 points", {"interest_pts": 0.03}),
    ("Local currency falls 30% in year 1", {"fx_devaluation": 0.30}),
]


def _summary(r: dict[str, Any], threshold: float, min_cash: float) -> dict[str, Any]:
    m = key_metrics(r)
    passes_dscr = m["min_dscr"] is None or m["min_dscr"] >= threshold
    return {
        "min_dscr": None if m["min_dscr"] is None else round(m["min_dscr"], 2),
        "min_dscr_year": m["min_dscr_year"],
        "lowest_cash": round(m["lowest_cash"]),
        "lowest_cash_year": m["lowest_cash_year"],
        "final_year_net_income": round(m["final_year_net_income"]),
        "total_fx_loss": round(m["total_fx_loss"]),
        "passes_lender_test": passes_dscr,
        "cash_stays_above_minimum": m["lowest_cash"] >= min_cash,
    }


def scenarios(raw: dict[str, Any]) -> dict[str, Any]:
    a = run(raw)["assumptions"]
    out = {}
    for name in a["scenarios"]:
        r = run(raw, scenario=name)
        out[name] = {"shocks": {k: v for k, v in r["shocks"].items() if v},
                     **_summary(r, a["minimum_dscr"], a["minimum_cash"])}
    return out


def stress_tests(raw: dict[str, Any]) -> list[dict[str, Any]]:
    base = run(raw)
    a = base["assumptions"]
    rows = [{"test": "Plan as submitted (base case)", **_summary(base, a["minimum_dscr"], a["minimum_cash"])}]
    for label, shock in STRESS_TESTS:
        if "fx_devaluation" in shock and not a["foreign_currencies"]:
            continue  # nothing is in foreign currency, so a devaluation changes nothing
        r = run(raw, shocks=shock)
        rows.append({"test": label, **_summary(r, a["minimum_dscr"], a["minimum_cash"])})
    return rows


def _fails(raw, key, value, threshold, min_cash, what):
    r = run(raw, shocks={key: value})
    m = key_metrics(r)
    if what == "dscr":
        return m["min_dscr"] is not None and m["min_dscr"] < threshold
    return m["lowest_cash"] < min_cash


def _bisect(raw, key, sign, hi, threshold, min_cash, what):
    if _fails(raw, key, 0.0, threshold, min_cash, what):
        return "already fails in the base case", None
    if not _fails(raw, key, sign * hi, threshold, min_cash, what):
        return f"holds even at {hi:.0%}", None
    lo_v, hi_v = 0.0, hi
    for _ in range(30):
        mid = (lo_v + hi_v) / 2
        if _fails(raw, key, sign * mid, threshold, min_cash, what):
            hi_v = mid
        else:
            lo_v = mid
    return f"{hi_v:.0%}", round(hi_v, 4)


def breaking_points(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """The size of each shock at which the plan stops passing: debt cover below the lender's
    minimum, or cash below the minimum balance."""
    a = run(raw)["assumptions"]
    has_debt = any(d is not None for d in run(raw)["ratios"]["dscr"])
    checks = [("price", "fall in selling prices", -1), ("volume", "fall in volumes", -1)]
    if a["foreign_currencies"]:
        checks.append(("fx_devaluation", f"fall of the {a['currency']} against the {' and '.join(a['foreign_currencies'])}", 1))
    tests = []
    if has_debt:
        tests.append(("dscr", a["minimum_dscr"], f"debt cover below the lender minimum of {a['minimum_dscr']:.2f}x"))
        tests.append(("dscr", 1.0, "debt cover below 1.00x (repayments no longer covered by cash flow)"))
    tests.append(("cash", None, "cash below the minimum balance"))
    out = []
    for key, label, sign in checks:
        hi = 0.9 if key != "fx_devaluation" else 3.0
        for what, threshold, text in tests:
            at, value = _bisect(raw, key, sign, hi, threshold or a["minimum_dscr"], a["minimum_cash"], what)
            out.append({"shock": label, "fails": text, "breaks_at": at, **({"value": value} if value else {})})
    return out


DOWNSIDE_DSCR = 1.0


def loan_structures(raw: dict[str, Any], max_options: int = 5) -> dict[str, Any]:
    """Search loan terms that meet the lender's minimum debt cover in the base case and still cover
    repayments (1.00x) in the downside case. Tries longer tenors, grace periods, smaller amounts and, for a foreign-currency loan,
    the same loan in local currency (if `local_currency_rate` is given in new_debt)."""
    base = run(raw)
    a = base["assumptions"]
    nd = a["new_debt"]
    if nd["amount"] <= 0:
        return {"note": "No new loan in the assumptions.", "options": []}

    def test(mod: dict) -> dict | None:
        trial = copy.deepcopy(raw)
        trial["new_debt"] = {**trial.get("new_debt", {}), **mod}
        res = {}
        for sc in ("base", "downside"):
            m = key_metrics(run(trial, scenario=sc))
            res[sc] = m
        b, d = res["base"]["min_dscr"], res["downside"]["min_dscr"]
        ok = (b is None or b >= a["minimum_dscr"]) and (d is None or d >= DOWNSIDE_DSCR)
        return {"terms": mod, "base_min_dscr": round(res["base"]["min_dscr"] or 0, 2),
                "downside_min_dscr": round(res["downside"]["min_dscr"] or 0, 2),
                "downside_lowest_cash": round(res["downside"]["lowest_cash"]), "passes": ok}

    current = test({})
    currencies = [nd["currency"]]
    local_rate = (raw.get("new_debt") or {}).get("local_currency_rate")
    if nd["currency"] != a["currency"] and local_rate:
        currencies.append(a["currency"])
    options = []
    for ccy in currencies:
        for share in (1.0, 0.85, 0.7, 0.55, 0.4):
            for tenor in range(nd["tenor_years"], 11):
                for grace in range(0, min(3, tenor)):
                    mod = {"tenor_years": tenor, "grace_years": grace, "amount": round(nd["amount"] * share, 2)}
                    if ccy != nd["currency"]:
                        mod.update(currency=ccy, amount=round(nd["amount"] * share * a["fx"][nd["currency"]]["rate"], 2),
                                   interest_rate=float(local_rate))
                    if mod["tenor_years"] == nd["tenor_years"] and mod["grace_years"] == nd["grace_years"] \
                            and share == 1.0 and ccy == nd["currency"]:
                        continue
                    r = test(mod)
                    if r["passes"]:
                        # How far from what was asked: smaller loan and currency switch cost most.
                        r["change_score"] = (1 - share) * 10 + (tenor - nd["tenor_years"]) + abs(grace - nd["grace_years"]) \
                            + (3 if ccy != nd["currency"] else 0)
                        r["description"] = _describe(nd, mod, share, a)
                        options.append(r)
    options.sort(key=lambda o: (o["change_score"], -o["downside_min_dscr"]))
    for o in options:
        o.pop("change_score", None)
    return {
        "requested": {"amount": nd["amount"], "currency": nd["currency"], "tenor_years": nd["tenor_years"],
                      "grace_years": nd["grace_years"], "interest_rate": nd["interest_rate"]},
        "requested_result": current,
        "minimum_dscr": a["minimum_dscr"],
        "options": options[:max_options],
        "test": (f"Base case debt cover at least {a['minimum_dscr']:.2f}x and downside at least "
                 f"{DOWNSIDE_DSCR:.2f}x in every year"),
        "note": ("Whether a lender offers these terms is for the lender to decide.") if options else
                ("No combination of tenor (up to 10 years), grace (up to 2 years) and a loan down to 40% of "
                 "the amount passes. The plan needs more equity, lower costs, slower spending or a "
                 "different mix of debt."),
    }


def _describe(nd, mod, share, a):
    parts = []
    if share < 1:
        parts.append(f"borrow {share:.0%} of the amount ({mod['amount']:,.0f} {mod.get('currency', nd['currency'])})")
    if mod["tenor_years"] != nd["tenor_years"]:
        parts.append(f"{mod['tenor_years']}-year tenor instead of {nd['tenor_years']}")
    if mod["grace_years"] != nd["grace_years"]:
        parts.append(f"{mod['grace_years']}-year grace period instead of {nd['grace_years']}")
    if mod.get("currency") and mod["currency"] != nd["currency"]:
        parts.append(f"borrow in {mod['currency']} at {mod['interest_rate']:.1%} instead of {nd['currency']}")
    return "; ".join(parts) or "as requested"


def full_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenarios": scenarios(raw),
        "stress_tests": stress_tests(raw),
        "breaking_points": breaking_points(raw),
        "loan_structures": loan_structures(raw),
    }


# ---------------------------------------------------------------- findings and facts for other tools

def stress_findings(raw: dict[str, Any], analysis: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Funder-style findings from the stress analysis, in the same format as review.py."""
    analysis = analysis or full_analysis(raw)
    a = run(raw)["assumptions"]
    f: list[dict[str, Any]] = []

    def add(sev, area, where, found, why, fix):
        f.append({"severity": sev, "area": area, "where": where, "found": found, "why_it_matters": why, "fix": fix})

    down = analysis["scenarios"].get("downside", {})
    if down.get("min_dscr") is not None and down["min_dscr"] < 1.0:
        add("high", "Stress test", f"Downside case, {down['min_dscr_year']}",
            f"In the downside case debt cover falls to {down['min_dscr']:.2f}x: repayments are not covered by cash flow",
            "Lenders test a bad year as well as the plan; below 1.0x the loan depends on luck or new money.",
            "See the loan options on the Stress tests sheet, or add equity, cut fixed costs or slow investment.")
    if down and not down.get("cash_stays_above_minimum", True):
        add("high", "Stress test", f"Downside case, {down['lowest_cash_year']}",
            f"In the downside case cash falls to {down['lowest_cash']:,} {a['currency']}",
            "Running out of cash in a bad year is how viable businesses fail.",
            "Hold a larger cash buffer, arrange a standby working-capital line, or phase spending.")
    for b in analysis["breaking_points"]:
        v = b.get("value")
        if v is not None and "1.00x" in b["fails"] and v < 0.10:
            add("high", "Thin margin", b["shock"],
                f"A {b['breaks_at']} {b['shock']} is enough to leave repayments uncovered",
                "There is almost no room for error; small, normal swings would put the loan at risk.",
                "Build headroom: lower debt service, higher margins or more equity.")
    if a["foreign_currencies"] and a["new_debt"]["currency"] != a["currency"]:
        fx_test = next((t for t in analysis["stress_tests"] if t["test"].startswith("Local currency falls")), None)
        if fx_test and not fx_test["passes_lender_test"]:
            add("high", "Currency risk", "Local currency falls 30%",
                f"A 30% fall of the {a['currency']} cuts debt cover to {fx_test['min_dscr']:.2f}x "
                f"(exchange losses {fx_test['total_fx_loss']:,} {a['currency']})",
                f"The loan is in {a['new_debt']['currency']} but most costs and part of revenue are in {a['currency']}.",
                "Borrow in local currency, match the loan to export revenue, or ask the lender about currency hedging.")
    ls = analysis["loan_structures"]
    if ls.get("requested_result") and not ls["requested_result"]["passes"] and ls.get("options"):
        add("medium", "Loan structure", "New loan",
            "The loan as requested does not pass, but these terms would: " + "; ".join(
                o["description"] for o in ls["options"][:3]),
            "Asking for terms the cash flow can carry makes approval more likely.",
            "Discuss these terms with the lender, or adjust the plan.")
    return f


def facts_from_model(raw: dict[str, Any]) -> dict[str, Any]:
    """Facts for the pre-mortem (objections.py), taken from the model instead of asking the user."""
    r = run(raw)
    a = r["assumptions"]
    m = key_metrics(r)
    rev = r["income_statement"]["revenue"]
    streams = a["revenue_streams"]
    foreign_rev = sum(r["income_statement"]["revenue_by_stream"][s["name"]][0]
                      for s in streams if s["currency"] != a["currency"])
    ebitda1 = r["income_statement"]["ebitda"][0]
    n = len(rev)
    cagr = (rev[-1] / rev[0]) ** (1 / (n - 1)) - 1 if n > 1 and rev[0] > 0 and rev[-1] > 0 else None
    facts = {
        "dscr_min": None if m["min_dscr"] is None else round(m["min_dscr"], 3),
        "dscr_required": a["minimum_dscr"],
        "debt_to_ebitda": round(r["balance_sheet"]["debt"][0] / ebitda1, 2) if ebitda1 > 0 else None,
        "revenue_cagr": None if cagr is None else round(cagr, 3),
        "use_of_funds_defined": bool(a["use_of_funds"]),
        "revenue_currency": a["currency"],
        "foreign_revenue_share": round(foreign_rev / rev[0], 3) if rev[0] else 0.0,
    }
    if a["new_debt"]["amount"] > 0:
        facts["loan_currency"] = a["new_debt"]["currency"]
        facts["loan_tenor_years"] = a["new_debt"]["tenor_years"]
    return {k: v for k, v in facts.items() if v is not None}

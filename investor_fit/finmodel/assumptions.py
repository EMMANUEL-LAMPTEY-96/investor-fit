"""Model assumptions: what the founder provides, with defaults and validation.

Plain Python (no third-party imports) so the same code runs on the connector server and inside
the user's Claude code-execution sandbox.

The model reports in one currency (`currency`, normally the company's local currency). A loan or a
revenue stream can be in another currency (e.g. a USD loan, or export sales priced in USD); it is
converted with `fx`, per foreign currency: {"USD": {"rate": 12, "depreciation": 0.08}, "EUR": {...}}.
`rate` = local units per 1 foreign unit at the start, `depreciation` = expected yearly fall of the
local currency against it (0.08 = 8% a year). With a single foreign currency the short form
{"rate": 12, "depreciation": 0.08} also works. Rates are fractions: 0.15 means 15%.
A value that varies by year can be a single number (same every year) or a list, one per year.

Scenarios: `scenarios` sets the shocks for "downside" and "upside" (defaults below). Shock keys:
price, volume, fixed_costs (fractions, e.g. -0.10), cogs_pts and interest_pts (added to the
rates, e.g. 0.03), receivable_days (added days), fx_devaluation (one-off fall of the local
currency in year 1, e.g. 0.20).
"""

from __future__ import annotations

import copy
from typing import Any

EXAMPLE: dict[str, Any] = {
    "company_name": "Example Cashew Processing Ltd",
    "currency": "USD",
    # To model in local currency with a foreign-currency loan, see EXAMPLE_FX below.
    "first_year": 2027,
    "years": 5,
    "revenue_streams": [
        {"name": "Cashew kernels (export)", "unit": "tonnes", "volume": 400, "volume_growth": 0.20,
         "price": 3500, "price_growth": 0.03},
        {"name": "Cashew shell oil", "unit": "tonnes", "volume": 120, "volume_growth": 0.15,
         "price": 600, "price_growth": 0.02},
    ],
    "cogs_pct_revenue": 0.62,
    "variable_opex_pct_revenue": 0.05,
    "fixed_costs": [
        {"name": "Salaries", "amount": 180000, "growth": 0.08},
        {"name": "Rent and utilities", "amount": 60000, "growth": 0.05},
        {"name": "Admin and other", "amount": 40000, "growth": 0.05},
    ],
    "capex": [
        {"name": "Processing line upgrade", "amounts": [250000, 0, 0, 100000, 0]},
    ],
    "depreciation_years": 10,
    "existing_ppe_remaining_years": 8,
    "receivable_days": 45,
    "inventory_days": 60,
    "payable_days": 30,
    "tax_rate": 0.25,
    "opening_balance": {"cash": 50000, "receivables": 120000, "inventory": 150000, "ppe_net": 400000,
                        "payables": 80000},
    "existing_debt": {"balance": 100000, "interest_rate": 0.18, "remaining_years": 2},
    "new_debt": {"amount": 500000, "interest_rate": 0.14, "tenor_years": 5, "grace_years": 1,
                 "drawdown_year": 1},
    "new_equity": {"amount": 0, "year": 1},
    "use_of_funds": [
        {"item": "Processing line upgrade", "amount": 250000},
        {"item": "Raw cashew stock (working capital)", "amount": 250000},
    ],
    "minimum_dscr": 1.25,
    "minimum_cash": 25000,
}

# The same business modelled in Ghana cedis, borrowing in US dollars, with kernels exported in USD.
EXAMPLE_FX: dict[str, Any] = {
    **EXAMPLE,
    "currency": "GHS",
    "fx": {"rate": 12.0, "depreciation": 0.08},
    "revenue_streams": [
        {"name": "Cashew kernels (export)", "unit": "tonnes", "volume": 400, "volume_growth": 0.20,
         "price": 3500, "price_growth": 0.03, "currency": "USD"},
        {"name": "Cashew shell oil (local)", "unit": "tonnes", "volume": 120, "volume_growth": 0.15,
         "price": 7200, "price_growth": 0.10},
    ],
    "fixed_costs": [
        {"name": "Salaries", "amount": 2160000, "growth": 0.15},
        {"name": "Rent and utilities", "amount": 720000, "growth": 0.12},
        {"name": "Admin and other", "amount": 480000, "growth": 0.12},
    ],
    "capex": [{"name": "Processing line upgrade", "amounts": [3000000, 0, 0, 1200000, 0]}],
    "opening_balance": {"cash": 600000, "receivables": 1440000, "inventory": 1800000, "ppe_net": 4800000,
                        "payables": 960000},
    "existing_debt": {"balance": 1200000, "interest_rate": 0.28, "remaining_years": 2},
    "new_debt": {"amount": 500000, "interest_rate": 0.11, "tenor_years": 5, "grace_years": 1,
                 "drawdown_year": 1, "currency": "USD"},
    "use_of_funds": [
        {"item": "Processing line upgrade", "amount": 3000000},
        {"item": "Raw cashew stock (working capital)", "amount": 3000000},
    ],
    "minimum_cash": 300000,
}

SHOCK_KEYS = ("price", "volume", "cogs_pts", "fixed_costs", "receivable_days", "interest_pts", "fx_devaluation")

DEFAULT_SCENARIOS: dict[str, dict[str, float]] = {
    "base": {},
    # A realistic bad year; edit to suit the sector. fx_devaluation only bites if something is in foreign currency.
    "downside": {"price": -0.10, "volume": -0.15, "cogs_pts": 0.03, "fixed_costs": 0.05,
                 "receivable_days": 15, "interest_pts": 0.02, "fx_devaluation": 0.20},
    "upside": {"price": 0.05, "volume": 0.10},
}

DEFAULTS: dict[str, Any] = {
    "currency": "USD",
    "years": 5,
    "variable_opex_pct_revenue": 0.0,
    "fixed_costs": [],
    "capex": [],
    "depreciation_years": 10,
    "receivable_days": 30,
    "inventory_days": 30,
    "payable_days": 30,
    "tax_rate": 0.25,
    "opening_balance": {},
    "existing_debt": {"balance": 0, "interest_rate": 0, "remaining_years": 1},
    "new_debt": {"amount": 0, "interest_rate": 0, "tenor_years": 1, "grace_years": 0, "drawdown_year": 1},
    "new_equity": {"amount": 0, "year": 1},
    "use_of_funds": [],
    "minimum_dscr": 1.25,
    "minimum_cash": 0,
    "fx": {},
}

OPENING_KEYS = ("cash", "receivables", "inventory", "ppe_net", "payables")


class AssumptionError(ValueError):
    pass


def series(value: Any, n: int, name: str) -> list[float]:
    """A number or list -> a list of n floats (a short list repeats its last value)."""
    if value is None:
        return [0.0] * n
    if isinstance(value, (int, float)):
        return [float(value)] * n
    if isinstance(value, (list, tuple)):
        if not value:
            return [0.0] * n
        vals = [float(v or 0) for v in value][:n]
        return vals + [vals[-1]] * (n - len(vals))
    raise AssumptionError(f"{name} must be a number or a list of numbers")


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults, expand per-year values, and check that the inputs make sense."""
    a = copy.deepcopy(DEFAULTS)
    for k, v in raw.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            a[k] = {**a[k], **v}
        else:
            a[k] = v

    problems: list[str] = []
    n = int(a.get("years") or 5)
    if not 1 <= n <= 10:
        problems.append("years must be between 1 and 10")
        n = 5
    a["years"] = n
    if not a.get("company_name"):
        problems.append("company_name is required")
    if not a.get("first_year"):
        problems.append("first_year is required (first projection year, e.g. 2027)")
    if not a.get("revenue_streams"):
        problems.append("at least one revenue stream is required (name, volume, price)")
    if "cogs_pct_revenue" not in a:
        problems.append("cogs_pct_revenue is required (direct costs as a share of revenue, e.g. 0.6)")

    streams = []
    for i, s in enumerate(a.get("revenue_streams") or []):
        if s.get("volume") is None or s.get("price") is None:
            problems.append(f"revenue stream {i + 1} needs a year-1 volume and price")
            continue
        streams.append({
            "currency": (s.get("currency") or a.get("currency") or "USD").upper(),
            "name": s.get("name") or f"Revenue stream {i + 1}",
            "unit": s.get("unit") or "units",
            "volume": float(s["volume"]),
            "volume_growth": series(s.get("volume_growth", 0), n, "volume_growth"),
            "price": float(s["price"]),
            "price_growth": series(s.get("price_growth", 0), n, "price_growth"),
        })
    a["revenue_streams"] = streams

    a["cogs_pct_revenue"] = series(a.get("cogs_pct_revenue"), n, "cogs_pct_revenue")
    a["variable_opex_pct_revenue"] = series(a.get("variable_opex_pct_revenue"), n, "variable_opex_pct_revenue")
    for name in ("cogs_pct_revenue", "variable_opex_pct_revenue"):
        if any(not 0 <= x < 1.5 for x in a[name]):
            problems.append(f"{name} should be a fraction such as 0.6 (60%), not a percentage like 60")

    a["fixed_costs"] = [{
        "name": f.get("name") or f"Fixed cost {i + 1}",
        "amount": float(f.get("amount") or 0),
        "growth": series(f.get("growth", 0), n, "growth"),
    } for i, f in enumerate(a.get("fixed_costs") or [])]

    a["capex"] = [{
        "name": c.get("name") or f"Capex {i + 1}",
        "amounts": series(c.get("amounts", 0), n, "capex amounts") if isinstance(c.get("amounts"), list)
        else [float(c.get("amounts") or 0)] + [0.0] * (n - 1),
    } for i, c in enumerate(a.get("capex") or [])]

    ob = {k: float((a.get("opening_balance") or {}).get(k) or 0) for k in OPENING_KEYS}
    a["opening_balance"] = ob
    ed = a["existing_debt"]
    ed["balance"] = float(ed.get("balance") or 0)
    ed["interest_rate"] = float(ed.get("interest_rate") or 0)
    ed["remaining_years"] = max(1, int(ed.get("remaining_years") or 1))
    nd = a["new_debt"]
    nd["amount"] = float(nd.get("amount") or 0)
    nd["interest_rate"] = float(nd.get("interest_rate") or 0)
    nd["tenor_years"] = max(1, int(nd.get("tenor_years") or 1))
    nd["grace_years"] = max(0, int(nd.get("grace_years") or 0))
    nd["drawdown_year"] = max(1, int(nd.get("drawdown_year") or 1))
    if nd["grace_years"] >= nd["tenor_years"]:
        problems.append("new_debt grace_years must be shorter than tenor_years")
    ne = a["new_equity"]
    ne["amount"] = float(ne.get("amount") or 0)
    ne["year"] = max(1, int(ne.get("year") or 1))

    a["depreciation_years"] = max(1, int(a.get("depreciation_years") or 10))
    a["existing_ppe_remaining_years"] = max(1, int(a.get("existing_ppe_remaining_years") or a["depreciation_years"]))
    for k in ("receivable_days", "inventory_days", "payable_days", "tax_rate", "minimum_dscr", "minimum_cash"):
        a[k] = float(a.get(k) or 0)
    if a["tax_rate"] > 1:
        problems.append("tax_rate should be a fraction such as 0.25, not 25")
    for r in ("interest_rate",):
        if nd[r] > 1 or ed[r] > 1:
            problems.append("interest rates should be fractions such as 0.14, not 14")

    home = (a.get("currency") or "USD").upper()
    a["currency"] = home
    ed["currency"] = (ed.get("currency") or home).upper()
    nd["currency"] = (nd.get("currency") or home).upper()
    foreign = sorted({c for c in [ed["currency"], nd["currency"]] + [s["currency"] for s in streams] if c != home})
    fx_in = a.get("fx") or {}
    if "rate" in fx_in or "depreciation" in fx_in:  # one-currency form: {"rate": .., "depreciation": ..}
        if len(foreign) > 1:
            problems.append("several foreign currencies are used, so give fx per currency, e.g. "
                            '{"USD": {"rate": 12, "depreciation": 0.08}, "EUR": {"rate": 13, "depreciation": 0.06}}')
        fx_in = {c: fx_in for c in foreign}
    fx_in = {str(k).upper(): v for k, v in fx_in.items()}
    a["fx"] = {}
    for c in foreign:
        spec = fx_in.get(c) or {}
        rate = float(spec.get("rate") or 0)
        if rate <= 0:
            problems.append(f"fx.{c}.rate is required: {home} per 1 {c} at the start of the first year")
        a["fx"][c] = {"rate": rate, "depreciation": series(spec.get("depreciation", 0), n, f"fx {c} depreciation")}
    a["foreign_currencies"] = foreign
    a["foreign_currency"] = foreign[0] if foreign else None  # kept for older callers

    sc = {k: dict(v) for k, v in DEFAULT_SCENARIOS.items()}
    for name, shocks in (a.get("scenarios") or {}).items():
        sc[name] = {**sc.get(name, {}), **(shocks or {})}
    for name, shocks in sc.items():
        bad = [k for k in shocks if k not in SHOCK_KEYS]
        if bad:
            problems.append(f"scenario '{name}' has unknown shocks {bad}; use {', '.join(SHOCK_KEYS)}")
        sc[name] = {k: float(shocks.get(k, 0) or 0) for k in SHOCK_KEYS}
    a["scenarios"] = sc

    a["use_of_funds"] = [{"item": u.get("item") or "Item", "amount": float(u.get("amount") or 0)}
                         for u in a.get("use_of_funds") or []]

    if problems:
        raise AssumptionError("; ".join(problems))
    return a

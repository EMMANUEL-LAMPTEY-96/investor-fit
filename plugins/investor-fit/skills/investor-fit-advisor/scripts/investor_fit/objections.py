"""Pre-mortem: the objections a funder is likely to raise, before the company applies.

Patterns (data/objections.json) come from public sources: development finance institutions,
SME finance research and lender guidance. Each has a list of sources and an evidence_strength.

For one company and one funder, each relevant pattern is either:
  flagged     the company's facts show the risk (e.g. largest customer is 45% of revenue)
  to_prepare  relevant to this funder, but the facts are not known; prepare the evidence
Patterns that do not apply to the funder type or instrument are left out.

Optional company facts used here (beyond the profile; leave out what is unknown):
  top_customer_share, top3_customer_share       fractions of revenue, e.g. 0.45
  collateral_cover                              collateral value / loan amount, e.g. 0.8
  dscr_min                                      lowest debt service cover in the model
  debt_to_ebitda, debt_to_equity                after the new funding
  revenue_currency, loan_currency               e.g. "GHS", "USD"
  foreign_revenue_share                         share of revenue earned in foreign currency, e.g. 0.8
  revenue_cagr                                  projected average growth, e.g. 0.6
  loan_tenor_years
  has_board, founder_dependent, management_team_size, tax_clearance_current, esg_policy,
  excluded_activity, use_of_funds_defined, has_offtake_contract, beneficial_ownership_documented,
  related_party_issues, credit_history_issues, records_inconsistent, exit_plan
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "objections.json"

HARD_CURRENCIES = {"USD", "EUR", "GBP", "CHF", "JPY"}
AGRI = {"agribusiness", "agri_processing", "agri_fintech"}
COMMODITY = AGRI | {"extractives", "trade_export"}
DEBT = {"debt", "working_capital", "trade_finance", "quasi_equity", "on_lending", "guarantee"}
EQUITY = {"equity", "quasi_equity"}

SEVERITY = {  # how damaging the objection is when flagged
    "excluded_activity": "critical", "kyc_aml_documentation_gaps": "critical", "unclear_ownership_kyc": "critical",
    "weak_debt_service_coverage": "high", "insufficient_collateral": "high", "tax_or_regulatory_noncompliance": "high",
    "currency_mismatch": "high", "no_audited_accounts": "high", "informal_or_inconsistent_records": "high",
    "poor_credit_history": "high", "high_leverage": "high", "ticket_too_small": "high", "stage_mismatch": "high",
    "no_offtake_or_export_contract": "high", "esg_standards_gap": "high",
}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2}


@lru_cache(maxsize=2)
def load_patterns(path: str | None = None) -> list[dict[str, Any]]:
    with open(path or DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _f(facts, k):
    v = facts.get(k)
    return None if v in ("", None) else v


def _pct(x):
    return f"{x:.0%}"


# Each rule returns (status, finding) where status is "flagged", "to_prepare" or None (does not apply).
Rule = Callable[[dict, dict, set], tuple[str | None, str | None]]


def _rules() -> dict[str, Rule]:
    def concentration(c, f, ins):
        top, top3 = _f(c, "top_customer_share"), _f(c, "top3_customer_share")
        if top is not None and top > 0.25:
            return "flagged", f"Largest customer is {_pct(top)} of revenue"
        if top3 is not None and top3 > 0.6:
            return "flagged", f"Top three customers are {_pct(top3)} of revenue"
        if top is None and top3 is None:
            return "to_prepare", "Share of revenue from the largest customers is not known"
        return None, None

    def track(c, f, ins):
        yrs = _f(c, "years_operating")
        need = (f.get("requirements") or {}).get("min_years_operating")
        if yrs is None:
            return "to_prepare", "Years trading not known"
        if need and yrs < need:
            return "flagged", f"{yrs:g} years trading; this funder asks for {need:g}"
        if yrs < 2 and ins & DEBT:
            return "flagged", f"Only {yrs:g} years trading; lenders usually want 2–3 years of history"
        return None, None

    def audited(c, f, ins):
        have = _f(c, "audited_years")
        need = (f.get("requirements") or {}).get("audited_years")
        if have is None:
            return "to_prepare", "Number of years of audited accounts not known"
        if need and have < need:
            return "flagged", f"{have} year(s) of audited accounts; this funder asks for {need}"
        if have == 0:
            return "flagged", "No audited accounts"
        return None, None

    def flag_if(field, true_means_risk, finding, unknown=None):
        def rule(c, f, ins):
            v = _f(c, field)
            if v is None:
                return ("to_prepare", unknown) if unknown else (None, None)
            return ("flagged", finding) if bool(v) == true_means_risk else (None, None)
        return rule

    def collateral(c, f, ins):
        if not ins & DEBT:
            return None, None
        cov = _f(c, "collateral_cover")
        if cov is None:
            return "to_prepare", "Collateral available against the loan not known"
        if cov < 1.0:
            return "flagged", f"Collateral covers {cov:.0%} of the loan; secured lenders often want 100–150%"
        return None, None

    def dscr(c, f, ins):
        if not ins & DEBT:
            return None, None
        d = _f(c, "dscr_min")
        floor = float(_f(c, "dscr_required") or 1.25)
        if d is None:
            return "to_prepare", "Debt service cover not yet calculated (build or review the financial model)"
        if d < floor:
            return "flagged", f"Lowest debt service cover is {d:.2f}x, below the usual {floor:.2f}x"
        return None, None

    def leverage(c, f, ins):
        de, dq = _f(c, "debt_to_ebitda"), _f(c, "debt_to_equity")
        if de is not None and de > 4:
            return "flagged", f"Debt is {de:.1f}x EBITDA"
        if dq is not None and dq > 3:
            return "flagged", f"Debt is {dq:.1f}x equity"
        return None, None

    def fx(c, f, ins):
        if not ins & DEBT:
            return None, None
        rc, lc = (_f(c, "revenue_currency") or "").upper(), (_f(c, "loan_currency") or "").upper()
        if not rc or not lc:
            return "to_prepare", "Currency of revenue and of the loan not stated"
        share = _f(c, "foreign_revenue_share")  # share of revenue earned in foreign currency, if known
        if lc in HARD_CURRENCIES and rc != lc:
            if share is not None:
                if share < 0.5:
                    return "flagged", (f"Loan in {lc} but only {share:.0%} of revenue is in foreign currency; "
                                       f"a fall of the {rc} raises the repayments")
                return None, None
            if not c.get("has_export_history"):
                return "flagged", f"Loan in {lc} but revenue in {rc}; a currency fall raises the repayments"
        return None, None

    def ticket(c, f, ins):
        amt, lo = _f(c, "amount_usd"), f.get("ticket_min_usd")
        if amt is not None and lo and amt < lo:
            return "flagged", f"Raising ${amt:,.0f}; this funder's minimum is ${lo:,.0f}"
        return None, None

    def stage(c, f, ins):
        st, stages = _f(c, "stage"), f.get("stages") or []
        if st and stages and st not in stages:
            return "flagged", f"Company is {st} stage; this funder prefers {', '.join(stages)}"
        return None, None

    def management(c, f, ins):
        n = _f(c, "management_team_size")
        if n is None:
            return "to_prepare", "Management team and experience not described"
        if n <= 1:
            return "flagged", "Management rests on one person"
        return None, None

    def tax(c, f, ins):
        v = _f(c, "tax_clearance_current")
        if v is False:
            return "flagged", "Tax clearance is not current"
        if v is None and not any("tax" in d for d in c.get("documents") or []):
            return "to_prepare", "No current tax clearance certificate seen"
        return None, None

    def esg(c, f, ins):
        if (f.get("type") or "") not in ("dfi", "impact_fund", "impact_lender", "export_credit", "pe"):
            return None, None
        v = _f(c, "esg_policy")
        if v is False:
            return "flagged", "No environmental and social policy or system"
        if v is None:
            return "to_prepare", "Environmental and social policy not described"
        return None, None

    def projections(c, f, ins):
        g = _f(c, "revenue_cagr")
        if g is not None and g > 0.5:
            return "flagged", f"Revenue projected to grow {g:.0%} a year"
        return None, None

    def exit_path(c, f, ins):
        if not ins & EQUITY:
            return None, None
        v = _f(c, "exit_plan")
        if v is False:
            return "flagged", "No exit route described for equity investors"
        return ("to_prepare", "Exit route for investors not described") if v is None else (None, None)

    def valuation(c, f, ins):
        return ("to_prepare", "Prepare a valuation basis investors can test") if ins & EQUITY else (None, None)

    def commodity(c, f, ins):
        if _f(c, "sector") in COMMODITY:
            return "flagged", "Commodity business: prices and seasons move cash flow"
        return None, None

    def supply(c, f, ins):
        return ("to_prepare", "Show how raw-material supply is secured") if _f(c, "sector") in AGRI else (None, None)

    def offtake(c, f, ins):
        if not ins & {"trade_finance", "working_capital"}:
            return None, None
        if c.get("has_offtake_contract") or c.get("has_export_order"):
            return None, None
        if c.get("has_offtake_contract") is False or c.get("has_export_order") is False:
            return "flagged", "No firm purchase order or offtake contract"
        return "to_prepare", "Firm orders or offtake contracts not described"

    def country(c, f, ins):
        if (f.get("type") or "") in ("export_credit", "pe", "vc", "dfi"):
            return "to_prepare", "Be ready to address country, currency-transfer and political risk"
        return None, None

    def kyc(c, f, ins):
        v = _f(c, "beneficial_ownership_documented")
        if v is False:
            return "flagged", "Beneficial owners not documented"
        if v is None and not any("registration" in d or "incorporation" in d for d in c.get("documents") or []):
            return "to_prepare", "Registration and ownership documents not yet seen"
        return None, None

    def market(c, f, ins):
        return ("to_prepare", "Size the market the company can reach") if (f.get("type") in ("vc", "pe")) else (None, None)

    def climate(c, f, ins):
        return ("to_prepare", "Show how weather and climate shocks are managed") if _f(c, "sector") in AGRI else (None, None)

    def tenor(c, f, ins):
        t = _f(c, "loan_tenor_years")
        if t is not None and t > 5 and (f.get("type") in ("bank", "impact_lender")):
            return "flagged", f"{t:g}-year tenor requested; SME lenders often cap at 3–5 years"
        return None, None

    return {
        "customer_concentration": concentration,
        "short_track_record": track,
        "no_audited_accounts": audited,
        "informal_or_inconsistent_records": flag_if("records_inconsistent", True, "Figures differ between documents"),
        "insufficient_collateral": collateral,
        "weak_debt_service_coverage": dscr,
        "high_leverage": leverage,
        "currency_mismatch": fx,
        "ticket_too_small": ticket,
        "stage_mismatch": stage,
        "weak_governance": flag_if("has_board", False, "No board or independent oversight"),
        "key_person_dependence": flag_if("founder_dependent", True, "Business depends on the founder"),
        "management_depth": management,
        "tax_or_regulatory_noncompliance": tax,
        "esg_standards_gap": esg,
        "excluded_activity": flag_if("excluded_activity", True, "Activity appears on a funder exclusion list"),
        "unclear_use_of_funds": flag_if("use_of_funds_defined", False, "Use of funds not broken down",
                                        "Use of funds not yet broken down"),
        "unrealistic_projections": projections,
        "no_exit_path": exit_path,
        "valuation_expectations": valuation,
        "commodity_price_and_seasonality": commodity,
        "supply_or_side_selling_risk": supply,
        "no_offtake_or_export_contract": offtake,
        "country_risk": country,
        "unclear_ownership_kyc": kyc,
        "related_party_and_commingling": flag_if("related_party_issues", True, "Related-party dealings or mixed accounts"),
        "small_addressable_market": market,
        "kyc_aml_documentation_gaps": kyc,
        "poor_credit_history": flag_if("credit_history_issues", True, "Past repayment problems on record"),
        "climate_and_weather_risk": climate,
        "long_tenor_request": tenor,
    }


RULES = _rules()


def pre_mortem(company: dict[str, Any], funder: dict[str, Any] | None = None,
               patterns: list[dict] | None = None, instruments: list[str] | None = None) -> dict[str, Any]:
    """Likely objections for one company, optionally for one funder.

    company: profile fields plus any optional facts listed in the module docstring.
    funder: a funder record; without one, every pattern relevant to the instruments sought is used.
    """
    patterns = patterns or load_patterns()
    funder = funder or {}
    ftype = funder.get("type")
    wanted = set(instruments or company.get("instruments_wanted") or [])
    offered = set(funder.get("instruments") or [])
    ins = (wanted & offered) or wanted or offered or {"debt"}
    if "working_capital" in ins or "trade_finance" in ins:
        ins |= {"debt"}

    flagged, prepare = [], []
    for p in patterns:
        if ftype and p.get("funder_types") and ftype not in p["funder_types"]:
            continue
        if p.get("instruments") and not (set(p["instruments"]) & (ins | ({"debt"} if ins & DEBT else set()))):
            continue
        rule = RULES.get(p["id"])
        if not rule:
            continue
        status, finding = rule(company, funder, ins)
        if not status:
            continue
        item = {
            "id": p["id"],
            "objection": p["title"],
            "finding": finding,
            "severity": SEVERITY.get(p["id"], "medium") if status == "flagged" else None,
            "why_funders_care": p.get("why_funders_care"),
            "how_to_answer": p.get("mitigations", [])[:3],
            "evidence_to_prepare": p.get("evidence_to_prepare", [])[:4],
            "evidence_strength": p.get("evidence_strength"),
            "sources": [{"title": s.get("title"), "publisher": s.get("publisher"), "url": s.get("url")}
                        for s in p.get("sources", [])],
        }
        (flagged if status == "flagged" else prepare).append(item)

    flagged.sort(key=lambda x: SEV_ORDER[x["severity"]])
    # The same rule backs both KYC patterns; keep one of each finding.
    seen, unique = set(), []
    for x in flagged:
        if x["finding"] not in seen:
            seen.add(x["finding"])
            unique.append(x)
    prep_seen, prep = set(), []
    for x in prepare:
        if x["finding"] not in prep_seen:
            prep_seen.add(x["finding"])
            prep.append(x)
    return {
        "funder": funder.get("name"),
        "funder_type": ftype,
        "likely_objections": unique,
        "to_prepare": prep,
        "summary": (f"{len(unique)} likely objection(s), {sum(1 for x in unique if x['severity'] in ('critical', 'high'))} serious; "
                    f"{len(prep)} point(s) to prepare evidence for."),
        "note": "Patterns are drawn from public sources (DFIs, SME finance research, lender guidance). "
                "A funder's own policy decides; use this to prepare, not to predict.",
    }

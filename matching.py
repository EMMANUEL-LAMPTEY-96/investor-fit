"""Matching engine: hard filters, a 0-100 fit score, and readiness gaps.

Plain, deterministic Python. No AI is involved, so the same company always gets
the same result, and every number can be explained line by line.
"""

from __future__ import annotations

import math
from typing import Any

from .models import CompanyProfile
from .vocab import INSTRUMENT_FAMILIES, REGION_SPECIFICITY, RELATED_SECTORS, STAGES, region_covers

WEIGHTS = {"sector": 30, "stage": 20, "ticket": 20, "impact": 15, "geography": 15}

# How far outside a funder's ticket range we still show it (as a near miss).
TICKET_TOLERANCE = 2.0


# ---------------------------------------------------------------- helpers

def _usd(x: float | None) -> str:
    if x is None:
        return "not stated"
    if x >= 1_000_000:
        return f"${x / 1_000_000:,.1f}M".replace(".0M", "M")
    if x >= 1_000:
        return f"${x / 1_000:,.0f}K"
    return f"${x:,.0f}"


def _ticket_range(f: dict) -> str:
    lo, hi = f.get("ticket_min_usd"), f.get("ticket_max_usd")
    if lo is None and hi is None:
        return "not stated"
    if lo is None:
        return f"up to {_usd(hi)}"
    if hi is None:
        return f"from {_usd(lo)}"
    return f"{_usd(lo)}–{_usd(hi)}"


# ---------------------------------------------------------------- filters

def _geo(c: CompanyProfile, f: dict) -> tuple[bool, int, str]:
    geos = f.get("geographies") or []
    if c.country in [g.upper() for g in geos]:
        return True, 15, f"names {c.country} as a target country"
    tokens = {g.lower() for g in geos}
    for token, pts in REGION_SPECIFICITY:
        if token in tokens and region_covers(token, c.country):
            label = "invests globally" if token == "global" else f"covers {token.replace('_', ' ')}"
            return True, pts, label
    return False, 0, "does not cover this country"


def _instrument(c: CompanyProfile, f: dict) -> tuple[bool, str]:
    offered = set(f.get("instruments") or [])
    if not c.instruments_wanted:
        return True, "open to any instrument"
    accepted: set[str] = set()
    for w in c.instruments_wanted:
        accepted |= INSTRUMENT_FAMILIES.get(w, {w})
    hit = sorted(offered & accepted)
    if hit:
        return True, "offers " + ", ".join(hit)
    return False, "offers " + (", ".join(sorted(offered)) or "nothing stated") + ", not what the company wants"


def _sector(c: CompanyProfile, f: dict) -> tuple[bool, int, str]:
    secs = set(f.get("sectors") or [])
    if c.sector in secs:
        return True, 30, f"targets {c.sector}"
    if RELATED_SECTORS.get(c.sector, set()) & secs:
        rel = ", ".join(sorted(RELATED_SECTORS[c.sector] & secs))
        return True, 18, f"targets related sector ({rel})"
    if "any" in secs:
        return True, 15, "sector-agnostic"
    return False, 0, "sector not covered"


def _stage(c: CompanyProfile, f: dict) -> tuple[bool, int, str]:
    stages = f.get("stages") or []
    if c.stage is None:
        return True, 10, "company stage not given"
    if not stages:
        return True, 10, "funder's preferred stage not stated"
    if c.stage in stages:
        return True, 20, f"invests at {c.stage} stage"
    ci = STAGES.index(c.stage)
    dist = min(abs(ci - STAGES.index(s)) for s in stages)
    if dist == 1:
        return True, 8, f"prefers {', '.join(stages)} (one step from {c.stage})"
    return False, 0, f"prefers {', '.join(stages)}"


def _ticket(c: CompanyProfile, f: dict) -> tuple[bool, int, str, bool]:
    """Returns (keep, points, reason, outside_range)."""
    lo, hi, amt = f.get("ticket_min_usd"), f.get("ticket_max_usd"), c.amount_usd
    if amt is None:
        return True, 10, "amount sought not given", False
    if lo is None and hi is None:
        return True, 10, "ticket size not published", False
    if lo is not None and amt < lo:
        ratio = lo / amt
        return ratio <= TICKET_TOLERANCE, 4, f"{_usd(amt)} is below their minimum of {_usd(lo)}", True
    if hi is not None and amt > hi:
        ratio = amt / hi
        return ratio <= TICKET_TOLERANCE, 4, f"{_usd(amt)} is above their maximum of {_usd(hi)}", True
    if lo is not None and hi is not None and hi > lo:
        # Closer to the middle of their range (on a log scale) scores higher.
        p = math.log(amt / lo) / math.log(hi / lo)
        pts = round(20 - 8 * abs(p - 0.5) * 2)
        return True, pts, f"{_usd(amt)} sits inside their {_ticket_range(f)} range", False
    return True, 16, f"{_usd(amt)} fits their range ({_ticket_range(f)})", False


def _impact(c: CompanyProfile, f: dict) -> tuple[int, str]:
    req = (f.get("requirements") or {}).get("impact_required")
    if req:
        if c.impact_focus is True:
            return 15, "impact investor, and the company has an impact story"
        if c.impact_focus is False:
            return 0, "impact investor, but the company reports no impact focus"
        return 8, "impact investor; company impact not yet described"
    return 10, "no specific impact mandate"


# ---------------------------------------------------------------- gaps

def readiness_gaps(c: CompanyProfile, f: dict) -> dict[str, Any]:
    """Compare the company with each stated requirement and say what would unlock it."""
    r = f.get("requirements") or {}
    gaps: list[dict[str, Any]] = []

    def add(req, needed, have, status, unlock):
        gaps.append({"requirement": req, "funder_needs": needed, "company_has": have, "status": status, "unlock": unlock})

    if r.get("min_revenue_usd") is not None:
        need = r["min_revenue_usd"]
        have = c.annual_revenue_usd
        if have is None:
            add("Minimum revenue", _usd(need), "not given", "unknown", "Confirm last year's revenue.")
        elif have >= need:
            add("Minimum revenue", _usd(need), _usd(have), "met", None)
        else:
            add("Minimum revenue", _usd(need), _usd(have), "missing", f"Grow annual revenue to at least {_usd(need)}.")

    if r.get("min_years_operating") is not None:
        need = r["min_years_operating"]
        have = c.years_operating
        if have is None:
            add("Years in business", f"{need:g}+", "not given", "unknown", "Confirm how long the company has traded.")
        elif have >= need:
            add("Years in business", f"{need:g}+", f"{have:g}", "met", None)
        else:
            add("Years in business", f"{need:g}+", f"{have:g}", "missing",
                f"Eligible after {need:g} years of trading (about {need - have:g} more).")

    if r.get("audited_years") is not None:
        need = r["audited_years"]
        have = c.audited_years
        if have is None:
            add("Audited accounts", f"{need} years", "not given", "unknown", "Confirm how many years of audited accounts exist.")
        elif have >= need:
            add("Audited accounts", f"{need} years", f"{have} years", "met", None)
        else:
            add("Audited accounts", f"{need} years", f"{have} years", "missing",
                f"Build {need - have} more year(s) of audited accounts; start the audit now.")

    if r.get("export_history_required"):
        if c.has_export_history is True:
            add("Export history", "previous exports", "yes", "met", None)
        elif c.has_export_history is False:
            unlock = "Complete a first export; its bills of lading and invoices become the evidence."
            if c.has_export_order:
                unlock += " You hold an export order, so ask whether they accept first-time exporters with a confirmed order."
            else:
                unlock += " A signed purchase contract or letter of credit from a buyer is the usual first step."
            add("Export history", "previous exports", "none", "missing", unlock)
        else:
            add("Export history", "previous exports", "not given", "unknown", "Confirm whether the company has exported before.")

    if r.get("impact_required"):
        if c.impact_focus is True:
            add("Impact", "measurable social or environmental impact", "yes", "met", None)
        elif c.impact_focus is False:
            add("Impact", "measurable social or environmental impact", "none stated", "missing",
                "Document impact: farmers sourced from, jobs created, women employed, climate benefits.")
        else:
            add("Impact", "measurable social or environmental impact", "not given", "unknown",
                "Describe who benefits from the business beyond its owners.")

    other = [o for o in (r.get("other") or []) if o]
    # A requirement line that starts with "Women-led" means the programme is only for women-led firms.
    if any(o.lower().strip().startswith("women-led") for o in other):
        if c.women_led is True:
            add("Women-led", "women-owned or women-led", "yes", "met", None)
        elif c.women_led is False:
            add("Women-led", "women-owned or women-led", "no", "missing", "Only open to women-led businesses.")
        else:
            add("Women-led", "women-owned or women-led", "not given", "unknown", "Confirm whether the company is women-led.")

    missing = [g for g in gaps if g["status"] == "missing"]
    unknown = [g for g in gaps if g["status"] == "unknown"]
    if missing:
        readiness = "not_yet"
    elif unknown:
        readiness = "check_first"
    else:
        readiness = "ready"

    route = None
    if f.get("direct_application") is False:
        route = "Does not take direct applications. Money reaches companies through partner banks or funds; approach those instead."

    return {
        "readiness": readiness,
        "gaps": gaps,
        "access_route": route,
        "other_requirements_to_confirm": other,
    }


# ---------------------------------------------------------------- main entry

def evaluate(c: CompanyProfile, f: dict) -> dict[str, Any]:
    """Score one funder for one company. Returns excluded=True with a reason if a hard filter fails."""
    ok_geo, geo_pts, geo_why = _geo(c, f)
    if not ok_geo:
        return {"excluded": True, "reason": "geography", "detail": geo_why}
    ok_ins, ins_why = _instrument(c, f)
    if not ok_ins:
        return {"excluded": True, "reason": "instrument", "detail": ins_why}
    ok_sec, sec_pts, sec_why = _sector(c, f)
    if not ok_sec:
        return {"excluded": True, "reason": "sector", "detail": sec_why}
    ok_stg, stg_pts, stg_why = _stage(c, f)
    if not ok_stg:
        return {"excluded": True, "reason": "stage", "detail": stg_why}
    ok_tkt, tkt_pts, tkt_why, outside = _ticket(c, f)
    if not ok_tkt:
        return {"excluded": True, "reason": "ticket_size", "detail": tkt_why}
    imp_pts, imp_why = _impact(c, f)

    breakdown = {
        "sector": {"points": sec_pts, "max": 30, "why": sec_why},
        "stage": {"points": stg_pts, "max": 20, "why": stg_why},
        "ticket": {"points": tkt_pts, "max": 20, "why": tkt_why},
        "impact": {"points": imp_pts, "max": 15, "why": imp_why},
        "geography": {"points": geo_pts, "max": 15, "why": geo_why},
    }
    score = sum(b["points"] for b in breakdown.values())
    ready = readiness_gaps(c, f)
    if outside:
        ready["gaps"].insert(0, {
            "requirement": "Ticket size", "funder_needs": _ticket_range(f), "company_has": _usd(c.amount_usd),
            "status": "missing", "unlock": "Resize the raise to fit their range, or co-finance with another funder.",
        })
        ready["readiness"] = "not_yet"

    return {
        "excluded": False,
        "funder_id": f["id"],
        "name": f["name"],
        "type": f["type"],
        "fit_score": score,
        "score_breakdown": breakdown,
        "ticket_range": _ticket_range(f),
        "instruments": f.get("instruments", []),
        **ready,
        "how_to_apply": f.get("how_to_apply"),
        "apply_url": f.get("apply_url"),
        "sources": f.get("source_urls", []),
        "data_confidence": f.get("confidence"),
        "last_checked": f.get("last_checked"),
        "verification_status": f.get("verification_status"),
        "notes": f.get("notes"),
    }


READINESS_ORDER = {"ready": 0, "check_first": 1, "not_yet": 2}


def match(c: CompanyProfile, funders: list[dict], top_n: int = 10) -> dict[str, Any]:
    results, excluded = [], {}
    for f in funders:
        r = evaluate(c, f)
        if r["excluded"]:
            excluded.setdefault(r["reason"], []).append({"funder": f["name"], "detail": r["detail"]})
        else:
            results.append(r)
    results.sort(key=lambda r: (-r["fit_score"], READINESS_ORDER[r["readiness"]], r["name"]))
    for i, r in enumerate(results, 1):
        r["rank"] = i

    missing_fields = [k for k in (
        "stage", "amount_usd", "annual_revenue_usd", "years_operating", "audited_years", "impact_focus",
    ) if getattr(c, k) is None]

    return {
        "company": c.model_dump(exclude_none=True),
        "funders_screened": len(funders),
        "matches_found": len(results),
        "matches": results[:top_n],
        "excluded_summary": {k: len(v) for k, v in excluded.items()},
        "excluded_detail": excluded,
        "profile_fields_missing": missing_fields,
        "method": "Hard filters (geography, instrument, sector, stage, ticket size) then a 0-100 score: "
                  "sector 30, stage 20, ticket 20, impact 15, geography 15. Readiness compares the company "
                  "with each funder's stated requirements.",
        "disclaimer": "Funder data is compiled from public sources and may be out of date. Confirm directly "
                      "with each funder. This is not financial or investment advice.",
    }

"""Matching engine: hard filters, a 0-100 fit score, and readiness gaps.

Plain, deterministic Python. No AI is involved, so the same company always gets
the same result, and every number can be explained line by line.
"""

from __future__ import annotations

import math
from typing import Any

from .profile import Profile, make_profile
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

def _geo(c: Profile, f: dict) -> tuple[bool, int, str]:
    geos = f.get("geographies") or []
    if c.country in [g.upper() for g in geos]:
        return True, 15, f"names {c.country} as a target country"
    tokens = {g.lower() for g in geos}
    for token, pts in REGION_SPECIFICITY:
        if token in tokens and region_covers(token, c.country):
            label = "invests globally" if token == "global" else f"covers {token.replace('_', ' ')}"
            return True, pts, label
    return False, 0, "does not cover this country"


def _instrument(c: Profile, f: dict) -> tuple[bool, str]:
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


def _sector(c: Profile, f: dict) -> tuple[bool, int, str]:
    secs = set(f.get("sectors") or [])
    if c.sector in secs:
        return True, 30, f"targets {c.sector}"
    if RELATED_SECTORS.get(c.sector, set()) & secs:
        rel = ", ".join(sorted(RELATED_SECTORS[c.sector] & secs))
        return True, 18, f"targets related sector ({rel})"
    if "any" in secs:
        return True, 15, "sector-agnostic"
    return False, 0, "sector not covered"


def _stage(c: Profile, f: dict) -> tuple[bool, int, str]:
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


def _ticket(c: Profile, f: dict) -> tuple[bool, int, str, bool]:
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


def _impact(c: Profile, f: dict) -> tuple[int, str]:
    req = (f.get("requirements") or {}).get("impact_required")
    if req:
        if c.impact_focus is True:
            return 15, "impact investor, and the company has an impact story"
        if c.impact_focus is False:
            return 0, "impact investor, but the company reports no impact focus"
        return 8, "impact investor; company impact not yet described"
    return 10, "no specific impact mandate"


# ---------------------------------------------------------------- gaps

def readiness_gaps(c: Profile, f: dict) -> dict[str, Any]:
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


def _documents(c: Profile, f: dict) -> list[dict[str, str]] | None:
    """The funder's document list, marked against the documents the company says it holds."""
    req = f.get("required_documents") or []
    if not req:
        return None
    held = [d.lower() for d in (getattr(c, "documents", None) or [])]
    out = []
    for doc in req:
        words = [w for w in doc.lower().replace("/", " ").split() if len(w) > 2]
        have = any(doc.lower() == h or (words and all(w in h for w in words)) for h in held)
        out.append({"document": doc, "status": "have" if have else ("missing" if held else "unknown")})
    return out


# ---------------------------------------------------------------- main entry

def evaluate(c: Any, f: dict) -> dict[str, Any]:
    """Score one funder for one company. Returns excluded=True with a reason if a hard filter fails."""
    c = make_profile(c)
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

    docs = _documents(c, f)
    return {
        "excluded": False,
        "source": f.get("source", "built_in"),
        "funder_id": f.get("id") or _slug(f.get("name", "funder")),
        "name": f.get("name", "Unnamed funder"),
        "type": f.get("type"),
        "fit_score": score,
        "score_breakdown": breakdown,
        "ticket_range": _ticket_range(f),
        "instruments": f.get("instruments", []),
        **ready,
        "documents": docs,
        "how_to_apply": f.get("how_to_apply"),
        "apply_url": f.get("apply_url"),
        "sources": f.get("source_urls", []),
        "data_confidence": f.get("confidence"),
        "last_checked": f.get("last_checked"),
        "verification_status": f.get("verification_status"),
        "notes": f.get("notes"),
    }


READINESS_ORDER = {"ready": 0, "check_first": 1, "not_yet": 2}


SOURCE_LABEL = {
    "user_provided": "provided by the user (treated as authoritative for this case)",
    "built_in": "built-in checked list",
    "found_online": "found online during this conversation (not verified)",
}


def combine_sources(built_in: list[dict], user: list[dict] | None = None,
                    found: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Merge funder lists. The same institution from several sources keeps the most trusted
    version (user > built-in > found online); differing facts are reported as conflicts."""
    order = [("user_provided", user or []), ("built_in", built_in or []), ("found_online", found or [])]
    chosen: dict[str, dict] = {}
    conflicts: list[dict] = []
    keys = ("ticket_min_usd", "ticket_max_usd", "geographies", "sectors", "stages", "instruments")
    rkeys = ("min_revenue_usd", "min_years_operating", "audited_years", "export_history_required", "impact_required")
    for source, items in order:
        for raw in items:
            f = {**raw, "source": source}
            f.setdefault("requirements", {})
            f.setdefault("id", _slug(f.get("name", "funder")))
            key = _slug(f.get("name") or f["id"])
            if key not in chosen:
                chosen[key] = f
                continue
            kept = chosen[key]
            diffs = []
            for k in keys:
                if f.get(k) not in (None, []) and kept.get(k) not in (None, []) and f.get(k) != kept.get(k):
                    diffs.append({"field": k, kept["source"]: kept.get(k), source: f.get(k)})
            for k in rkeys:
                a, b = (kept.get("requirements") or {}).get(k), (f.get("requirements") or {}).get(k)
                if a is not None and b is not None and a != b:
                    diffs.append({"field": f"requirements.{k}", kept["source"]: a, source: b})
            if diffs:
                conflicts.append({"funder": kept.get("name"), "used": kept["source"], "differences": diffs})
    return list(chosen.values()), conflicts


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def match(c: Any, funders: list[dict], top_n: int = 10, conflicts: list[dict] | None = None,
          facts: dict | None = None) -> dict[str, Any]:
    """facts: optional extra company facts (see objections.py). When given, each match also lists
    the objections that funder is likely to raise."""
    raw = c.as_dict() if hasattr(c, "as_dict") else (c.model_dump() if hasattr(c, "model_dump") else dict(c))
    c = make_profile(c)
    results, excluded = [], {}
    for f in funders:
        r = evaluate(c, f)
        if r["excluded"]:
            excluded.setdefault(r["reason"], []).append({"funder": f.get("name", "Unnamed funder"), "source": f.get("source", "built_in"), "detail": r["detail"]})
        else:
            results.append(r)
    results.sort(key=lambda r: (-r["fit_score"], READINESS_ORDER[r["readiness"]], r["name"]))
    for i, r in enumerate(results, 1):
        r["rank"] = i
    if facts is not None:
        from .objections import pre_mortem

        by_id = {f.get("id") or _slug(f.get("name", "")): f for f in funders}
        company_facts = {**raw, **facts}
        for r in results[:top_n] + [x for x in results[top_n:] if x.get("source") == "user_provided"]:
            pm = pre_mortem(company_facts, by_id.get(r["funder_id"], {}))
            r["likely_objections"] = [
                {"objection": o["objection"], "finding": o["finding"], "severity": o["severity"]}
                for o in pm["likely_objections"]
            ]

    missing_fields = [k for k in (
        "stage", "amount_usd", "annual_revenue_usd", "years_operating", "audited_years", "impact_focus",
    ) if getattr(c, k) is None]

    return {
        "company": c.model_dump(exclude_none=True),
        "funders_screened": len(funders),
        "matches_found": len(results),
        "matches": results[:top_n],
        # Institutions the user asked about are always reported, wherever they rank or if ruled out.
        "your_institutions": [
            {k: r.get(k) for k in ("rank", "name", "fit_score", "readiness", "gaps", "documents", "access_route",
                                   "likely_objections")}
            for r in results if r.get("source") == "user_provided"
        ] + [
            {"name": x["funder"], "ruled_out_by": reason, "detail": x["detail"]}
            for reason, xs in excluded.items() for x in xs if x.get("source") == "user_provided"
        ],
        "sources_used": {s: sum(1 for f in funders if f.get("source", "built_in") == s) for s in SOURCE_LABEL
                         if any(f.get("source", "built_in") == s for f in funders)},
        "source_labels": SOURCE_LABEL,
        "conflicts": conflicts or [],
        "excluded_summary": {k: len(v) for k, v in excluded.items()},
        "excluded_detail": excluded,
        "profile_fields_missing": missing_fields,
        "method": "Hard filters (geography, instrument, sector, stage, ticket size) then a 0-100 score: "
                  "sector 30, stage 20, ticket 20, impact 15, geography 15. Readiness compares the company "
                  "with each funder's stated requirements.",
        "disclaimer": "Funder data is compiled from public sources and may be out of date. Confirm directly "
                      "with each funder. This is not financial or investment advice.",
    }

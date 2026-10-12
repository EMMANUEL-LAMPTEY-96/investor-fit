"""Check a company against any checklist the user provides.

A checklist can come from anywhere: a bank's term sheet, a grant's eligibility rules, an
investor's document list, the user's own credit policy. Claude turns it into items; this module
checks each item against the company's facts and documents, deterministically.

Item types
  min / max      numeric threshold on a fact          {"field": "audited_years", "value": 3}
  equals         fact must equal a value              {"field": "country", "value": "GH"}
  one_of         fact must be one of several values   {"field": "sector", "value": ["agribusiness", "agri_processing"]}
  yes            fact must be true                    {"field": "women_led"}
  document       company must hold a document         {"document": "tax clearance certificate"}
  judgement      needs a reasoned assessment          Claude fills "assessment": "met" | "missing" | "unclear"
                                                       and "reason"; the checker records it as such.

Facts are a flat dict of values (the company profile plus anything else the checklist needs,
e.g. "collateral_cover": 1.4, "dscr_min": 1.2). Each fact can have evidence: where it came from.
"""

from __future__ import annotations

from typing import Any

STATUS_ORDER = {"missing": 0, "unknown": 1, "needs_review": 2, "met": 3}


def _norm(x: Any) -> Any:
    return x.strip().lower() if isinstance(x, str) else x


def _doc_held(doc: str, held: list[str]) -> str | None:
    want = _norm(doc)
    words = [w for w in want.replace("/", " ").replace("(", " ").replace(")", " ").split() if len(w) > 2]
    for h in held:
        hn = _norm(h)
        if want == hn or want in hn or (words and all(w in hn for w in words)):
            return h
    return None


def check(checklist: dict[str, Any], facts: dict[str, Any], documents: list[Any] | None = None,
          evidence: dict[str, str] | None = None) -> dict[str, Any]:
    """checklist: {"name", "source", "items": [...]}; facts: flat dict; documents: list of names or
    {"name", "type", "file"}; evidence: {fact_name: "where it came from"}."""
    evidence = evidence or {}
    held: list[str] = []
    doc_files: dict[str, str] = {}
    for d in documents or []:
        if isinstance(d, dict):
            label = " ".join(str(d.get(k, "")) for k in ("type", "name")).strip()
            held.append(label)
            doc_files[label] = d.get("file") or d.get("name") or label
        else:
            held.append(str(d))
            doc_files[str(d)] = str(d)

    results = []
    for i, item in enumerate(checklist.get("items") or [], 1):
        kind = (item.get("type") or "judgement").lower()
        req = item.get("requirement") or item.get("document") or item.get("field") or f"Item {i}"
        field = item.get("field")
        target = item.get("value")
        have = facts.get(field) if field else None
        status, detail = "unknown", None

        if kind in ("min", "max"):
            if have is None:
                detail = f"{field} not known"
            else:
                try:
                    ok = float(have) >= float(target) if kind == "min" else float(have) <= float(target)
                    status = "met" if ok else "missing"
                    detail = f"has {have}, needs {'at least' if kind == 'min' else 'at most'} {target}"
                except (TypeError, ValueError):
                    status, detail = "needs_review", f"could not compare {have!r} with {target!r}"
        elif kind == "equals":
            if have is None:
                detail = f"{field} not known"
            else:
                status = "met" if _norm(have) == _norm(target) else "missing"
                detail = f"has {have}, needs {target}"
        elif kind == "one_of":
            if have is None:
                detail = f"{field} not known"
            else:
                options = [_norm(t) for t in (target or [])]
                status = "met" if _norm(have) in options else "missing"
                detail = f"has {have}, needs one of {', '.join(map(str, target or []))}"
        elif kind == "yes":
            if have is None:
                detail = f"{field} not known"
            else:
                status = "met" if have is True or _norm(have) in ("yes", "true") else "missing"
                detail = f"{field}: {have}"
        elif kind == "document":
            doc = item.get("document") or req
            found = _doc_held(doc, held)
            if found:
                status, detail = "met", f"provided: {doc_files.get(found, found)}"
            else:
                status = "missing" if held else "unknown"
                detail = "not among the documents provided" if held else "no documents provided yet"
        else:  # judgement
            a = _norm(item.get("assessment"))
            status = {"met": "met", "missing": "missing", "not met": "missing"}.get(a, "needs_review")
            detail = item.get("reason") or "needs a reasoned assessment"

        results.append({
            "item": i,
            "requirement": req,
            "type": kind,
            "status": status,
            "detail": detail,
            "evidence": evidence.get(field) if field else None,
            "fix": item.get("fix") if status != "met" else None,
        })

    results.sort(key=lambda r: (STATUS_ORDER[r["status"]], r["item"]))
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("met", "missing", "unknown", "needs_review")}
    total = len(results)
    verdict = ("Meets every item on this checklist." if total and counts["met"] == total
               else f"{counts['missing']} item(s) not met." if counts["missing"]
               else "No items failed, but some could not be confirmed." if total
               else "The checklist has no items.")
    return {
        "checklist": checklist.get("name") or "Checklist",
        "source": checklist.get("source") or "provided by the user",
        "verdict": verdict,
        "counts": counts,
        "score": f"{counts['met']} of {total} met",
        "items": results,
    }

"""Read lists and checklists the user provides, as JSON or CSV (export from Excel or Google Sheets).

Lists inside a CSV cell are separated by semicolons: "GH; NG; west_africa".
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

FUNDER_CSV_COLUMNS = [
    "name", "type", "countries_or_regions", "sectors", "stages", "instruments",
    "ticket_min_usd", "ticket_max_usd", "min_revenue_usd", "min_years_operating", "audited_years",
    "export_history_required", "impact_required", "required_documents", "other_requirements",
    "direct_application", "how_to_apply", "apply_url", "source",
]
CHECKLIST_CSV_COLUMNS = ["requirement", "type", "field", "value", "document", "fix"]


def _list(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def _num(v: str | None) -> float | None:
    v = (v or "").replace(",", "").replace("$", "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _bool(v: str | None) -> bool | None:
    v = (v or "").strip().lower()
    if v in ("yes", "y", "true", "1"):
        return True
    if v in ("no", "n", "false", "0"):
        return False
    return None


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def load_funders(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("funders", [])
    out = []
    for r in _rows(p):
        if not r.get("name"):
            continue
        out.append({
            "name": r["name"],
            "type": r.get("type") or None,
            "geographies": _list(r.get("countries_or_regions")) or ["global"],
            "sectors": _list(r.get("sectors")) or ["any"],
            "stages": _list(r.get("stages")),
            "instruments": _list(r.get("instruments")),
            "ticket_min_usd": _num(r.get("ticket_min_usd")),
            "ticket_max_usd": _num(r.get("ticket_max_usd")),
            "requirements": {
                "min_revenue_usd": _num(r.get("min_revenue_usd")),
                "min_years_operating": _num(r.get("min_years_operating")),
                "audited_years": int(_num(r.get("audited_years"))) if _num(r.get("audited_years")) is not None else None,
                "export_history_required": _bool(r.get("export_history_required")),
                "impact_required": _bool(r.get("impact_required")),
                "other": _list(r.get("other_requirements")),
            },
            "required_documents": _list(r.get("required_documents")),
            "direct_application": _bool(r.get("direct_application")),
            "how_to_apply": r.get("how_to_apply") or None,
            "apply_url": r.get("apply_url") or None,
            "source_urls": _list(r.get("source")) or ["provided by the user"],
        })
    return out


def load_checklist(path: str) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    items = []
    for r in _rows(p):
        if not (r.get("requirement") or r.get("document")):
            continue
        value: Any = r.get("value") or None
        if r.get("type") == "one_of":
            value = _list(value)
        elif value is not None and _num(value) is not None and r.get("type") in ("min", "max"):
            value = _num(value)
        items.append({k: v for k, v in {
            "requirement": r.get("requirement") or None, "type": r.get("type") or "judgement",
            "field": r.get("field") or None, "value": value, "document": r.get("document") or None,
            "fix": r.get("fix") or None,
        }.items() if v is not None})
    return {"name": p.stem.replace("_", " "), "source": "provided by the user", "items": items}

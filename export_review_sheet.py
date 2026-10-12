"""Export the funder database to a CSV you can open in Excel to verify each row.

Usage: python scripts/export_review_sheet.py  ->  data/funders_review.csv
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
funders = json.loads((ROOT / "data" / "funders.json").read_text(encoding="utf-8"))

cols = [
    "id", "name", "type", "geographies", "sectors", "stages", "instruments",
    "ticket_min_usd", "ticket_max_usd", "min_revenue_usd", "min_years_operating", "audited_years",
    "export_history_required", "impact_required", "other_requirements", "direct_application",
    "how_to_apply", "apply_url", "source_urls", "notes", "confidence", "last_checked",
    "verification_status", "reviewer_comment",
]

out = ROOT / "data" / "funders_review.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for f in funders:
        r = f.get("requirements") or {}
        w.writerow({
            **{k: f.get(k) for k in cols if k in f},
            "geographies": ", ".join(f.get("geographies") or []),
            "sectors": ", ".join(f.get("sectors") or []),
            "stages": ", ".join(f.get("stages") or []),
            "instruments": ", ".join(f.get("instruments") or []),
            "min_revenue_usd": r.get("min_revenue_usd"),
            "min_years_operating": r.get("min_years_operating"),
            "audited_years": r.get("audited_years"),
            "export_history_required": r.get("export_history_required"),
            "impact_required": r.get("impact_required"),
            "other_requirements": " | ".join(r.get("other") or []),
            "source_urls": " ".join(f.get("source_urls") or []),
            "reviewer_comment": "",
        })
print(f"Wrote {len(funders)} rows to {out}")

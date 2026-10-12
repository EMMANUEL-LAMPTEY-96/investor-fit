"""Build a financial model from the evidence in a company's documents.

Usage:
    python build_from_documents.py evidence.json --out "<Company> financial model.xlsx"
                                   [--answers answers.json] [--allow-placeholders]

Steps:
1. Checks the evidence (same as check_documents.py).
2. Works out assumptions from the documents, recording the source of each.
3. If something only the user can answer is missing, stops and prints the questions (status
   "needs_input"). Answer them in answers.json (same layout as the assumptions, e.g.
   {"new_debt": {"amount": 500000, "currency": "USD", ...}, "existing_debt": {"remaining_years": 3}})
   and run again. Use --allow-placeholders only after working through the questions with the user.
4. Builds the Excel model with scenarios, stress tests, a Data quality sheet and a Sources sheet,
   and writes <out>_assumptions.json (to edit and rebuild with build_model.py) and <out>_facts.json.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.evidence import check  # noqa: E402
from investor_fit.finmodel.assumptions import AssumptionError  # noqa: E402
from investor_fit.finmodel.engine import funding_analysis, run  # noqa: E402
from investor_fit.finmodel.excel import build_workbook  # noqa: E402
from investor_fit.finmodel.from_evidence import derive  # noqa: E402
from investor_fit.finmodel.review import assess_projections, from_engine  # noqa: E402
from investor_fit.finmodel.stress import facts_from_model, full_analysis, stress_findings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence")
    ap.add_argument("--out", required=True)
    ap.add_argument("--answers")
    ap.add_argument("--allow-placeholders", action="store_true")
    a = ap.parse_args()

    evidence = json.loads(Path(a.evidence).read_text(encoding="utf-8"))
    answers = json.loads(Path(a.answers).read_text(encoding="utf-8")) if a.answers else {}
    quality = check(evidence)
    d = derive(evidence, answers, allow_placeholders=a.allow_placeholders)
    if d["status"] != "ready":
        print(json.dumps({"status": d["status"], "data_quality": quality, "questions": d["questions"],
                          "assumptions_so_far": d["register"], "note": d.get("note")}, indent=2, ensure_ascii=False))
        return 0
    assumptions = d["assumptions"]
    try:
        result = run(assumptions)
    except AssumptionError as e:
        print(json.dumps({"status": "needs_input", "error": f"Assumptions need fixing: {e}",
                          "data_quality": quality}, indent=2))
        return 1
    analysis = full_analysis(assumptions)
    build_workbook(assumptions, a.out, analysis=analysis,
                   sources={"register": d["register"], "history": d["history"]}, quality=quality)
    stem = str(Path(a.out).with_suffix(""))
    Path(stem + "_assumptions.json").write_text(json.dumps(assumptions, indent=2, default=str))
    Path(stem + "_facts.json").write_text(json.dumps({"facts": facts_from_model(assumptions)}, indent=2))
    review = assess_projections(from_engine(result))
    review["findings"] += stress_findings(assumptions, analysis)
    rnd = lambda xs: [round(x) for x in xs]  # noqa: E731
    print(json.dumps({
        "status": "built",
        "file": a.out,
        "assumptions_file": stem + "_assumptions.json",
        "facts_file": stem + "_facts.json",
        "placeholders_used": d.get("placeholders_used", []),
        "to_confirm": [r for r in d["register"] if r["origin"] in ("suggested", "placeholder")],
        "data_quality": {k: quality[k] for k in ("verdict", "counts_by_severity", "questions")},
        "years": result["years"], "currency": result["currency"],
        "revenue": rnd(result["income_statement"]["revenue"]),
        "net_income": rnd(result["income_statement"]["net_income"]),
        "closing_cash": rnd(result["balance_sheet"]["cash"]),
        "funding_analysis": funding_analysis(assumptions),
        "scenarios": analysis["scenarios"],
        "breaking_points": analysis["breaking_points"],
        "loan_structures": analysis["loan_structures"],
        "review": review,
    }, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build an editable Excel financial model from an assumptions JSON file, with scenarios,
stress tests, breaking points and loan options.

Usage:
    python build_model.py assumptions.json output.xlsx
    python build_model.py --example example.json      # filled-in example in one currency
    python build_model.py --example-fx example.json   # local currency with a USD loan and USD exports

Prints a JSON summary: headline figures, the funding analysis, scenarios, stress tests, breaking
points, loan options and a funder-style review. Also writes <output>_facts.json, the facts the
pre-mortem needs (debt cover, currencies, growth), for pre_mortem.py and match_funders.py --facts.
The Excel numbers come from live formulas; the summary comes from the same calculations in Python.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.finmodel.assumptions import EXAMPLE, EXAMPLE_FX, AssumptionError  # noqa: E402
from investor_fit.finmodel.engine import funding_analysis, run  # noqa: E402
from investor_fit.finmodel.excel import build_workbook  # noqa: E402
from investor_fit.finmodel.review import assess_projections, from_engine  # noqa: E402
from investor_fit.finmodel.stress import facts_from_model, full_analysis, stress_findings  # noqa: E402


def main(argv):
    if len(argv) == 3 and argv[1] in ("--example", "--example-fx"):
        Path(argv[2]).write_text(json.dumps(EXAMPLE if argv[1] == "--example" else EXAMPLE_FX, indent=2))
        print(f"Example assumptions written to {argv[2]}")
        return 0
    if len(argv) != 3:
        print(__doc__)
        return 2
    assumptions = json.loads(Path(argv[1]).read_text())
    try:
        result = run(assumptions)
    except AssumptionError as e:
        print(json.dumps({"error": f"Assumptions need fixing: {e}"}))
        return 1
    analysis = full_analysis(assumptions)
    build_workbook(assumptions, argv[2], analysis=analysis)
    facts = facts_from_model(assumptions)
    facts_path = str(Path(argv[2]).with_suffix("")) + "_facts.json"
    Path(facts_path).write_text(json.dumps({"facts": facts}, indent=2))
    review = assess_projections(from_engine(result))
    extra = stress_findings(assumptions, analysis)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    review["findings"] = sorted(review["findings"] + extra, key=lambda f: order[f["severity"]])
    for f in extra:
        review["counts"][f["severity"]] = review["counts"].get(f["severity"], 0) + 1
    if review["counts"].get("critical"):
        review["verdict"] = "Not ready to send: fix the critical issues first."
    elif review["counts"].get("high"):
        review["verdict"] = "Needs work before sending to funders."
    is_, bs = result["income_statement"], result["balance_sheet"]
    rnd = lambda xs: [None if x is None else round(x) for x in xs]  # noqa: E731
    print(json.dumps({
        "file": argv[2],
        "facts_file": facts_path,
        "years": result["years"],
        "currency": result["assumptions"]["currency"],
        "revenue": rnd(is_["revenue"]), "ebitda": rnd(is_["ebitda"]), "net_income": rnd(is_["net_income"]),
        "closing_cash": rnd(bs["cash"]), "total_debt": rnd(bs["debt"]),
        "dscr": [None if x is None else round(x, 2) for x in result["ratios"]["dscr"]],
        "fx_rate": None if result["fx_rate"] is None else [round(x, 4) for x in result["fx_rate"]],
        "funding_analysis": funding_analysis(assumptions),
        "scenarios": analysis["scenarios"],
        "stress_tests": analysis["stress_tests"],
        "breaking_points": analysis["breaking_points"],
        "loan_structures": analysis["loan_structures"],
        "review": review,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

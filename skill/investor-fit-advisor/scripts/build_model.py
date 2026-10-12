"""Build an editable Excel financial model from an assumptions JSON file.

Usage:
    python build_model.py assumptions.json output.xlsx
    python build_model.py --example example_assumptions.json   # write a filled-in example to start from

Prints a JSON summary: headline figures, the funding analysis and a funder-style review.
The Excel numbers come from live formulas; the summary comes from the same calculations in Python.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.finmodel.assumptions import EXAMPLE, AssumptionError  # noqa: E402
from investor_fit.finmodel.engine import funding_analysis, run  # noqa: E402
from investor_fit.finmodel.excel import build_workbook  # noqa: E402
from investor_fit.finmodel.review import assess_projections, from_engine  # noqa: E402


def main(argv):
    if len(argv) == 3 and argv[1] == "--example":
        Path(argv[2]).write_text(json.dumps(EXAMPLE, indent=2))
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
    build_workbook(assumptions, argv[2])
    is_, bs = result["income_statement"], result["balance_sheet"]
    rnd = lambda xs: [None if x is None else round(x) for x in xs]  # noqa: E731
    print(json.dumps({
        "file": argv[2],
        "years": result["years"],
        "currency": result["assumptions"]["currency"],
        "revenue": rnd(is_["revenue"]), "ebitda": rnd(is_["ebitda"]), "net_income": rnd(is_["net_income"]),
        "closing_cash": rnd(bs["cash"]), "total_debt": rnd(bs["debt"]),
        "dscr": [None if x is None else round(x, 2) for x in result["ratios"]["dscr"]],
        "funding_analysis": funding_analysis(assumptions),
        "review": assess_projections(from_engine(result)),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

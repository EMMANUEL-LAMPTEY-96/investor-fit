"""Review a financial model.

Usage:
    python review_model.py model.xlsx                      # mechanical checks on the spreadsheet
    python review_model.py --projections projections.json  # judgement checks on the numbers

projections.json holds the yearly figures read from the model:
    {"currency": "USD", "years": [2027, ...], "revenue": [...], "ebitda": [...], "net_income": [...],
     "closing_cash": [...], "total_debt": [...], "debt_service": [...optional],
     "history": {"revenue": [...], "ebitda": [...]},
     "ask": {"amount": 500000, "instrument": "debt", "tenor_years": 5, "interest_rate": 0.14,
             "grace_years": 1, "use_of_funds_total": 500000},
     "min_dscr": 1.25}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.finmodel.review import assess_projections, scan_workbook  # noqa: E402


def main(argv):
    if len(argv) == 3 and argv[1] == "--projections":
        print(json.dumps(assess_projections(json.loads(Path(argv[2]).read_text())), indent=2, default=str))
        return 0
    if len(argv) == 2:
        print(json.dumps(scan_workbook(argv[1]), indent=2, default=str))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

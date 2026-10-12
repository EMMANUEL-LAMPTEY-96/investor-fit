"""Check a company against any checklist: a bank's term sheet, a grant's eligibility rules, an
investor's document list, the user's own policy.

Usage:
    python check_checklist.py checklist.(json|csv) facts.json

facts.json:
    {"facts": {"country": "GH", "audited_years": 1, "collateral_cover": 1.4, ...},
     "documents": [{"type": "tax clearance certificate", "file": "GRA_TCC_2026.pdf"}, ...],
     "evidence": {"audited_years": "Audited accounts 2025, p.1", ...}}

Prints JSON: verdict, counts, and each item as met / missing / unknown / needs_review with detail,
evidence and fix.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.checklist import check  # noqa: E402
from investor_fit.userdata import load_checklist  # noqa: E402


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    checklist = load_checklist(argv[1])
    f = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    print(json.dumps(check(checklist, f.get("facts", {}), f.get("documents"), f.get("evidence")), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

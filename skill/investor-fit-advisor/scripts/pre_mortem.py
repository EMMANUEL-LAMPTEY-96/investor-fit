"""Pre-mortem: the objections funders are likely to raise, and how to answer them.

Usage:
    python pre_mortem.py company.json [--facts facts.json] [--funder FUNDER_ID_OR_NAME]
                         [--funders FILE] [--type dfi|bank|impact_lender|impact_fund|vc|pe|export_credit]

Without --funder or --type, checks every pattern relevant to the money being sought.
--funders  a user or found-online funder list to look the funder up in (JSON or CSV)
facts.json holds optional facts such as top_customer_share, collateral_cover, dscr_min,
revenue_currency, loan_currency, has_board, tax_clearance_current, esg_policy (see SKILL.md).

Prints JSON: likely objections (with the finding, severity, why funders care, how to answer, evidence
to prepare and public sources) and points to prepare evidence for.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit import userdata  # noqa: E402
from investor_fit.data import load_funders  # noqa: E402
from investor_fit.matching import _slug  # noqa: E402
from investor_fit.objections import pre_mortem  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("company")
    ap.add_argument("--facts")
    ap.add_argument("--funder")
    ap.add_argument("--funders")
    ap.add_argument("--type")
    a = ap.parse_args()

    company = json.loads(Path(a.company).read_text(encoding="utf-8"))
    if a.facts:
        f = json.loads(Path(a.facts).read_text(encoding="utf-8"))
        company = {**company, **(f.get("facts", f) if isinstance(f, dict) else {})}

    funder = {}
    if a.funder:
        pool = (userdata.load_funders(a.funders) if a.funders else []) + load_funders()
        key = _slug(a.funder)
        funder = next((x for x in pool if x.get("id") == a.funder or _slug(x.get("name", "")) == key
                       or key in _slug(x.get("name", ""))), None)
        if funder is None:
            print(json.dumps({"error": f"Funder '{a.funder}' not found. Pass --funders with its record, or use --type."}))
            return 1
    elif a.type:
        funder = {"type": a.type, "name": f"Typical {a.type.replace('_', ' ')}"}

    print(json.dumps(pre_mortem(company, funder), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

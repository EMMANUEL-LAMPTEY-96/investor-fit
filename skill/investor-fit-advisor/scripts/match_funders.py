"""Rank funders for a company, from three sources: the user's own list, the built-in checked
list, and funders found online during the conversation.

Usage:
    python match_funders.py company.json [--user-funders FILE] [--found FILE] [--top 10] [--no-built-in]

company.json     the company profile (see SKILL.md)
--user-funders   institutions the user provided (JSON, or CSV in templates/funder_list_template.csv format)
--found          institutions Claude found online, in the same format, each with source_urls
--no-built-in    use only the user's list (and anything found online)

Prints JSON: ranked matches with score breakdown, readiness gaps, document status and source of
each funder; every user-provided institution under "your_institutions"; conflicts between sources.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.data import load_funders  # noqa: E402
from investor_fit.matching import combine_sources, match  # noqa: E402
from investor_fit.profile import ProfileError  # noqa: E402
from investor_fit import userdata  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("company")
    ap.add_argument("--user-funders")
    ap.add_argument("--found")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--no-built-in", action="store_true")
    a = ap.parse_args()

    company = json.loads(Path(a.company).read_text(encoding="utf-8"))
    built_in = [] if a.no_built_in else load_funders()
    user = userdata.load_funders(a.user_funders) if a.user_funders else []
    found = userdata.load_funders(a.found) if a.found else []
    funders, conflicts = combine_sources(built_in, user, found)
    try:
        result = match(company, funders, top_n=a.top, conflicts=conflicts)
    except ProfileError as e:
        print(json.dumps({"error": f"Company profile needs fixing: {e}"}))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

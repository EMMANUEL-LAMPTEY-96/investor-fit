"""Check the evidence read from a company's documents: what is missing, inconsistent or implausible.

Usage:
    python check_documents.py evidence.json

evidence.json is written by Claude after reading the documents (format: see SKILL.md and
examples/evidence_example.json). Prints JSON: a verdict, counts, every issue with where it is and a
question for the user, and a list of the high-priority questions to work through first.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investor_fit.evidence import check  # noqa: E402


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    print(json.dumps(check(json.loads(Path(argv[1]).read_text(encoding="utf-8"))), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

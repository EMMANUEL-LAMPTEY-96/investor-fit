"""Package the Claude skill as one zip, ready to upload in Claude (Customize > Skills).

The zip contains everything the agent needs, so no server or hosting is required:
the instructions, the built-in checked list of institutions, and the matching, checklist and
financial-model code (copied from the investor_fit package so both use the same code).

Usage: python scripts/package_skill.py  ->  dist/investor-fit-advisor.zip
"""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "investor-fit-advisor"
SCRIPTS = SKILL / "scripts"
DIST = ROOT / "dist"
SERVER_ONLY = ("server.py", "models.py", "__pycache__", "*.pyc")


def main():
    for old in ("investor_fit", "data", "finmodel"):
        if (SCRIPTS / old).exists():
            shutil.rmtree(SCRIPTS / old)
    shutil.copytree(ROOT / "investor_fit", SCRIPTS / "investor_fit", ignore=shutil.ignore_patterns(*SERVER_ONLY))
    (SCRIPTS / "data").mkdir()
    for f in ("funders.json", "LICENSE.md"):
        shutil.copy(ROOT / "data" / f, SCRIPTS / "data" / f)

    DIST.mkdir(exist_ok=True)
    out = DIST / "investor-fit-advisor.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(SKILL.parent))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

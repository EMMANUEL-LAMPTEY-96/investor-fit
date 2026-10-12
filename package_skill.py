"""Package the Claude skill as a zip ready to upload in Claude (Customize > Skills).

Copies the shared finmodel package into the skill so both use the same code.
Usage: python scripts/package_skill.py  ->  dist/investor-fit-advisor.zip
"""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "investor-fit-advisor"
DIST = ROOT / "dist"


def main():
    target = SKILL / "scripts" / "finmodel"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ROOT / "investor_fit" / "finmodel", target, ignore=shutil.ignore_patterns("__pycache__"))
    DIST.mkdir(exist_ok=True)
    out = DIST / "investor-fit-advisor.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(SKILL.parent))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

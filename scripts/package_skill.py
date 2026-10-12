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


def write_objections_reference():
    """A readable list of every objection pattern and its public sources."""
    import json

    pats = json.loads((ROOT / "data" / "objections.json").read_text(encoding="utf-8"))
    lines = [
        "# Why funders say no: objection patterns",
        "",
        "Used by `scripts/pre_mortem.py`. Every pattern is drawn from public sources: development finance",
        "institutions, SME finance research and lender guidance. `Evidence: limited` means the sources",
        "support the point only generally or come from a single publisher; treat those as practitioner",
        "guidance rather than established findings. A funder's own policy always decides.",
        "",
    ]
    for p in pats:
        lines += [f"## {p['title']}", "",
                  f"`{p['id']}` · applies to: {', '.join(p.get('funder_types', []))} · evidence: {p.get('evidence_strength', 'good')}",
                  "", p.get("why_funders_care", ""), ""]
        if p.get("warning_signs"):
            lines += ["**Warning signs:** " + "; ".join(p["warning_signs"]), ""]
        if p.get("mitigations"):
            lines += ["**How to answer it:** " + "; ".join(p["mitigations"]), ""]
        if p.get("evidence_to_prepare"):
            lines += ["**Evidence to prepare:** " + "; ".join(p["evidence_to_prepare"]), ""]
        if p.get("sources"):
            lines += ["**Sources:**", ""]
            lines += [f"- [{s.get('title')}]({s.get('url')}), {s.get('publisher')}, {s.get('year')}: {s.get('supports')}"
                      for s in p["sources"]]
            lines.append("")
    (SKILL / "references" / "objections.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    for old in ("investor_fit", "data", "finmodel"):
        if (SCRIPTS / old).exists():
            shutil.rmtree(SCRIPTS / old)
    shutil.copytree(ROOT / "investor_fit", SCRIPTS / "investor_fit", ignore=shutil.ignore_patterns(*SERVER_ONLY))
    (SCRIPTS / "data").mkdir()
    for f in ("funders.json", "objections.json", "LICENSE.md"):
        shutil.copy(ROOT / "data" / f, SCRIPTS / "data" / f)
    write_objections_reference()

    DIST.mkdir(exist_ok=True)
    out = DIST / "investor-fit-advisor.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(SKILL.parent))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

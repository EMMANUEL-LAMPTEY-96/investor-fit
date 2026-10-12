"""Build the two ways people install the agent, from the one source in skill/investor-fit-advisor:

1. dist/investor-fit-advisor.zip  - upload in Claude (Customize > Skills)
2. plugins/investor-fit/          - Claude Code plugin, listed in .claude-plugin/marketplace.json

Both contain everything the agent needs (instructions, the built-in checked list, objection
patterns, and the matching, checklist and financial-model code), so no server is required.
Run after any change, and commit the results: python scripts/package_skill.py
"""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "investor-fit-advisor"
SCRIPTS = SKILL / "scripts"
DIST = ROOT / "dist"
SERVER_ONLY = ("server.py", "models.py", "__pycache__", "*.pyc")
PLUGIN = ROOT / "plugins" / "investor-fit"
REPO = "EMMANUEL-LAMPTEY-96/investor-fit"
VERSION = next(line.split('"')[1] for line in (ROOT / "pyproject.toml").read_text().splitlines()
               if line.startswith("version"))
DESCRIPTION = ("Capital-raising advisor: finds funders worldwide, checks readiness against funder criteria "
               "and any checklist, flags likely objections, and builds or reviews financial models.")


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
    build_plugin()


def build_plugin():
    """Claude Code plugin: a copy of the finished skill, with script paths using ${CLAUDE_SKILL_DIR}."""
    import json

    if PLUGIN.exists():
        shutil.rmtree(PLUGIN)
    target = PLUGIN / "skills" / "investor-fit-advisor"
    shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    md = (target / "SKILL.md").read_text(encoding="utf-8")
    md = md.replace("`SKILL_DIR` below means the folder that contains this SKILL.md. ", "")
    md = md.replace("SKILL_DIR", "${CLAUDE_SKILL_DIR}")
    head, body = md.split("---\n", 2)[1], md.split("---\n", 2)[2]
    head += "allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)\n"
    (target / "SKILL.md").write_text(f"---\n{head}---\n{body}", encoding="utf-8")
    (PLUGIN / ".claude-plugin").mkdir(parents=True)
    (PLUGIN / ".claude-plugin" / "plugin.json").write_text(json.dumps({
        "name": "investor-fit",
        "version": VERSION,
        "description": DESCRIPTION,
        "author": {"name": "Emmanuel Nii Lante Lamptey"},
        "homepage": f"https://github.com/{REPO}",
        "repository": f"https://github.com/{REPO}",
        "license": "MIT",
        "keywords": ["finance", "fundraising", "investors", "financial-model", "sme", "development-finance"],
    }, indent=2) + "\n", encoding="utf-8")
    (PLUGIN / "README.md").write_text(
        "# investor-fit (Claude Code plugin)\n\nInstall in Claude Code:\n\n"
        f"    /plugin install investor-fit --marketplace {REPO}\n\n"
        "or, on older versions:\n\n"
        f"    /plugin marketplace add {REPO}\n"
        "    /plugin install investor-fit@investor-fit-marketplace\n\n"
        "Generated by `scripts/package_skill.py` from `skill/investor-fit-advisor`. Do not edit here; "
        "edit the skill and run the script.\n", encoding="utf-8")
    (ROOT / ".claude-plugin").mkdir(exist_ok=True)
    (ROOT / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "investor-fit-marketplace",
        "owner": {"name": "Emmanuel Nii Lante Lamptey"},
        "metadata": {"description": "Investor-Fit Agent: a capital-raising advisor for Claude Code."},
        "plugins": [{"name": "investor-fit", "source": "./plugins/investor-fit", "description": DESCRIPTION}],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {PLUGIN.relative_to(ROOT)} and .claude-plugin/marketplace.json")


if __name__ == "__main__":
    main()

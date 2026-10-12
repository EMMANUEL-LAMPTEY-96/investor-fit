import json
import subprocess
import sys
import zipfile
from pathlib import Path

from investor_fit.data import get_funder, load_funders
from investor_fit.matching import match
from investor_fit.objections import RULES, load_patterns, pre_mortem

ROOT = Path(__file__).resolve().parent.parent
BASE = {"country": "GH", "sector": "agri_processing", "stage": "growth", "amount_usd": 500000,
        "instruments_wanted": ["working_capital"], "years_operating": 4, "audited_years": 1}


def ids(result, key="likely_objections"):
    return {o["id"] for o in result[key]}


def test_every_pattern_is_sourced_and_has_a_rule():
    pats = load_patterns()
    assert len(pats) >= 28
    for p in pats:
        assert p["sources"], p["id"]
        assert all(s.get("url", "").startswith("http") for s in p["sources"]), p["id"]
        assert p["evidence_strength"] in ("good", "limited")
        # outside_funder_mandate is handled by the matching filters instead of a rule
        assert p["id"] in RULES or p["id"] == "outside_funder_mandate"


def test_risky_facts_are_flagged_for_a_lender():
    c = {**BASE, "top_customer_share": 0.45, "collateral_cover": 0.8, "dscr_min": 1.04,
         "revenue_currency": "GHS", "loan_currency": "USD"}
    r = pre_mortem(c, get_funder("root-capital"))
    assert {"customer_concentration", "insufficient_collateral", "weak_debt_service_coverage",
            "currency_mismatch"} <= ids(r)
    assert r["likely_objections"][0]["severity"] in ("critical", "high")


def test_healthy_facts_are_not_flagged():
    c = {**BASE, "sector": "manufacturing", "top_customer_share": 0.1, "collateral_cover": 1.5, "dscr_min": 2.0,
         "revenue_currency": "USD", "loan_currency": "USD", "has_board": True, "management_team_size": 4,
         "tax_clearance_current": True, "esg_policy": True, "use_of_funds_defined": True,
         "has_offtake_contract": True, "beneficial_ownership_documented": True}
    r = pre_mortem(c, get_funder("root-capital"))
    assert r["likely_objections"] == []


def test_unknown_facts_become_points_to_prepare():
    r = pre_mortem(BASE, {"type": "bank", "instruments": ["working_capital"]})
    assert {"customer_concentration", "insufficient_collateral", "weak_debt_service_coverage"} <= ids(r, "to_prepare")


def test_objections_depend_on_funder_type():
    c = {**BASE, "instruments_wanted": ["equity"], "exit_plan": False}
    vc = pre_mortem(c, {"type": "vc", "instruments": ["equity"]})
    bank = pre_mortem(c, {"type": "bank", "instruments": ["debt"]})
    assert "no_exit_path" in ids(vc)
    assert "no_exit_path" not in ids(bank)


def test_match_attaches_objections_when_facts_given():
    r = match(BASE, load_funders(), top_n=5, facts={"dscr_min": 1.0})
    assert all("likely_objections" in m for m in r["matches"])
    assert any(o["objection"].startswith("Cash flow too thin") for m in r["matches"] for o in m["likely_objections"])
    assert "likely_objections" not in match(BASE, load_funders(), top_n=5)["matches"][0]


def test_pre_mortem_script_runs_from_packaged_skill(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "package_skill.py")], check=True, capture_output=True)
    with zipfile.ZipFile(ROOT / "dist" / "investor-fit-advisor.zip") as z:
        z.extractall(tmp_path)
    skill = tmp_path / "investor-fit-advisor"
    assert (skill / "references" / "objections.md").exists()
    (tmp_path / "company.json").write_text(json.dumps(BASE))
    (tmp_path / "facts.json").write_text(json.dumps({"facts": {"collateral_cover": 0.5}}))
    out = subprocess.run([sys.executable, "-I", str(skill / "scripts" / "pre_mortem.py"), str(tmp_path / "company.json"),
                          "--facts", str(tmp_path / "facts.json"), "--funder", "Root Capital"],
                         check=True, capture_output=True, text=True)
    r = json.loads(out.stdout)
    assert r["funder"] == "Root Capital" and "insufficient_collateral" in ids(r)

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from investor_fit.checklist import check
from investor_fit.data import load_funders
from investor_fit.matching import combine_sources, match
from investor_fit.profile import ProfileError, make_profile
from investor_fit.userdata import load_checklist
from investor_fit.userdata import load_funders as load_user_funders

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "skill" / "investor-fit-advisor" / "templates"

COMPANY = {"country": "GH", "sector": "agri_processing", "stage": "growth", "amount_usd": 500000,
           "instruments_wanted": ["working_capital"], "annual_revenue_usd": 1200000, "years_operating": 4,
           "audited_years": 1, "documents": ["tax clearance certificate"]}


def test_profile_validation_explains_problems():
    with pytest.raises(ProfileError, match="country"):
        make_profile({"country": "Ghana", "sector": "agri_processing"})
    with pytest.raises(ProfileError, match="sector"):
        make_profile({"country": "GH", "sector": "farming"})


def test_user_list_wins_conflicts_and_is_always_reported():
    user = [{"name": "Root Capital", "geographies": ["GH"], "sectors": ["agribusiness"],
             "instruments": ["working_capital"], "ticket_min_usd": 100000, "ticket_max_usd": 2000000},
            {"name": "Tiny Local Lender", "geographies": ["GH"], "sectors": ["any"], "instruments": ["debt"],
             "ticket_max_usd": 50000}]
    funders, conflicts = combine_sources(load_funders(), user)
    root = [f for f in funders if f["name"] == "Root Capital"]
    assert len(root) == 1 and root[0]["source"] == "user_provided"
    assert conflicts and conflicts[0]["funder"] == "Root Capital"
    r = match(COMPANY, funders, top_n=3, conflicts=conflicts)
    names = {x["name"] for x in r["your_institutions"]}
    assert names == {"Root Capital", "Tiny Local Lender"}  # the ruled-out one is still reported
    ruled_out = next(x for x in r["your_institutions"] if x["name"] == "Tiny Local Lender")
    assert ruled_out["ruled_out_by"] == "ticket_size"


def test_found_online_funders_are_labelled():
    found = [{"name": "Some Online Fund", "geographies": ["africa"], "sectors": ["agri_processing"],
              "instruments": ["working_capital"], "source_urls": ["https://example.org"]}]
    funders, _ = combine_sources([], None, found)
    r = match(COMPANY, funders)
    assert r["matches"][0]["source"] == "found_online"


def test_required_documents_are_checked():
    user = [{"name": "Bank", "geographies": ["GH"], "sectors": ["any"], "instruments": ["working_capital"],
             "required_documents": ["Tax clearance certificate", "Board resolution"]}]
    funders, _ = combine_sources([], user)
    docs = {d["document"]: d["status"] for d in match(COMPANY, funders)["matches"][0]["documents"]}
    assert docs == {"Tax clearance certificate": "have", "Board resolution": "missing"}


def test_templates_load():
    funders = load_user_funders(str(TEMPLATES / "funder_list_template.csv"))
    assert funders[0]["instruments"] == ["working_capital", "debt"]
    assert funders[0]["requirements"]["audited_years"] == 2
    cl = load_checklist(str(TEMPLATES / "checklist_template.csv"))
    assert {i["type"] for i in cl["items"]} == {"min", "equals", "one_of", "yes", "document", "judgement"}


def test_checklist_statuses():
    cl = {"items": [
        {"requirement": "3 years audited", "type": "min", "field": "audited_years", "value": 3},
        {"requirement": "Ghana", "type": "equals", "field": "country", "value": "gh"},
        {"requirement": "Collateral", "type": "min", "field": "collateral_cover", "value": 1.2},
        {"type": "document", "document": "Tax clearance certificate"},
        {"requirement": "Experience", "type": "judgement", "assessment": "met", "reason": "CV p.2"},
        {"requirement": "Governance", "type": "judgement"},
    ]}
    r = check(cl, {"audited_years": 1, "country": "GH"}, ["Tax clearance certificate 2026"])
    status = {i["requirement"]: i["status"] for i in r["items"]}
    assert status == {"3 years audited": "missing", "Ghana": "met", "Collateral": "unknown",
                      "Tax clearance certificate": "met", "Experience": "met", "Governance": "needs_review"}
    assert r["score"] == "3 of 6 met"


def test_packaged_skill_runs_on_its_own(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "package_skill.py")], check=True, capture_output=True)
    with zipfile.ZipFile(ROOT / "dist" / "investor-fit-advisor.zip") as z:
        z.extractall(tmp_path)
    skill = tmp_path / "investor-fit-advisor"
    assert not (skill / "scripts" / "investor_fit" / "server.py").exists()
    (tmp_path / "company.json").write_text(json.dumps(COMPANY))
    out = subprocess.run([sys.executable, "-I", str(skill / "scripts" / "match_funders.py"), str(tmp_path / "company.json"),
                          "--user-funders", str(skill / "templates" / "funder_list_template.csv")],
                         check=True, capture_output=True, text=True, cwd=tmp_path)
    r = json.loads(out.stdout)
    assert r["matches"] and r["your_institutions"]

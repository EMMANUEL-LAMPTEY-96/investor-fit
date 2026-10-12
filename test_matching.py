import json
from pathlib import Path

import pytest

from investor_fit.data import load_funders
from investor_fit.matching import evaluate, match
from investor_fit.models import CompanyProfile
from investor_fit.vocab import FUNDER_TYPES, INSTRUMENTS, SECTORS, STAGES

FUNDERS = load_funders()


def company(**kw):
    base = dict(country="GH", sector="agri_processing", stage="growth", amount_usd=500_000,
                instruments_wanted=["working_capital"], annual_revenue_usd=1_200_000,
                years_operating=4, audited_years=1, has_export_history=False,
                has_export_order=True, impact_focus=True)
    base.update(kw)
    return CompanyProfile(**base)


def funder(**kw):
    base = {"id": "test", "name": "Test Fund", "type": "impact_fund", "geographies": ["west_africa"],
            "sectors": ["agribusiness"], "stages": ["growth"], "instruments": ["debt"],
            "ticket_min_usd": 100_000, "ticket_max_usd": 2_000_000,
            "requirements": {"min_revenue_usd": None, "min_years_operating": None, "audited_years": None,
                             "export_history_required": None, "impact_required": None, "other": []},
            "direct_application": True, "source_urls": ["https://example.org"], "confidence": "high",
            "last_checked": "2026-10-12", "verification_status": "needs_human_review"}
    base.update(kw)
    return base


# ---------- data quality

def test_every_funder_uses_the_vocabulary():
    ids = set()
    for f in FUNDERS:
        assert f["id"] not in ids, f"duplicate id {f['id']}"
        ids.add(f["id"])
        assert f["type"] in FUNDER_TYPES
        assert set(f["sectors"]) <= set(SECTORS) | {"any"}, f["id"]
        assert set(f["stages"]) <= set(STAGES), f["id"]
        assert set(f["instruments"]) <= set(INSTRUMENTS), f["id"]
        assert f["source_urls"], f"{f['id']} has no source"
        if f["ticket_min_usd"] and f["ticket_max_usd"]:
            assert f["ticket_min_usd"] <= f["ticket_max_usd"], f["id"]


# ---------- hard filters

def test_wrong_country_is_excluded():
    r = evaluate(company(country="KE"), funder(geographies=["west_africa"]))
    assert r["excluded"] and r["reason"] == "geography"


def test_equity_funder_excluded_for_debt_request():
    r = evaluate(company(instruments_wanted=["debt"]), funder(instruments=["equity"]))
    assert r["excluded"] and r["reason"] == "instrument"


def test_ticket_far_too_small_is_excluded_but_near_miss_is_kept():
    far = evaluate(company(amount_usd=10_000), funder(ticket_min_usd=100_000))
    near = evaluate(company(amount_usd=80_000), funder(ticket_min_usd=100_000))
    assert far["excluded"] and far["reason"] == "ticket_size"
    assert not near["excluded"] and near["readiness"] == "not_yet"


def test_two_stages_away_is_excluded():
    r = evaluate(company(stage="startup"), funder(stages=["growth", "mature"]))
    assert r["excluded"] and r["reason"] == "stage"


# ---------- scoring

def test_perfect_fit_scores_100():
    r = evaluate(company(sector="agribusiness", amount_usd=447_214),  # log-midpoint of 100K-2M
                 funder(geographies=["GH"], requirements={**funder()["requirements"], "impact_required": True}))
    assert r["fit_score"] == 100


def test_score_is_deterministic():
    c = company()
    assert match(c, FUNDERS) == match(c, FUNDERS)


# ---------- readiness gaps

def test_audited_accounts_gap_says_how_many_more_years():
    r = evaluate(company(audited_years=1),
                 funder(requirements={**funder()["requirements"], "audited_years": 3}))
    gap = next(g for g in r["gaps"] if g["requirement"] == "Audited accounts")
    assert gap["status"] == "missing" and "2 more" in gap["unlock"]


def test_export_gap_mentions_export_order_when_company_has_one():
    r = evaluate(company(has_export_history=False, has_export_order=True),
                 funder(requirements={**funder()["requirements"], "export_history_required": True}))
    gap = next(g for g in r["gaps"] if g["requirement"] == "Export history")
    assert gap["status"] == "missing" and "first-time exporters" in gap["unlock"]


def test_unknown_values_mean_check_first_not_rejection():
    r = evaluate(company(annual_revenue_usd=None),
                 funder(requirements={**funder()["requirements"], "min_revenue_usd": 100_000}))
    assert r["readiness"] == "check_first"


def test_on_lending_funder_gets_access_route():
    r = evaluate(company(), funder(instruments=["on_lending"], direct_application=False))
    assert r["access_route"] and "partner banks" in r["access_route"]


# ---------- benchmark companies (expected matches set by the analyst)

BENCH = json.loads((Path(__file__).parent / "benchmark.json").read_text())


@pytest.mark.parametrize("case", BENCH, ids=[c["label"] for c in BENCH])
def test_benchmark(case):
    r = match(CompanyProfile(**case["company"]), FUNDERS, top_n=10)
    top = [m["funder_id"] for m in r["matches"]]
    for fid in case["expect_in_top_10"]:
        assert fid in top, f"{fid} missing from top 10: {top}"
    for fid in case.get("expect_excluded", []):
        assert fid not in [m["funder_id"] for m in match(CompanyProfile(**case["company"]), FUNDERS, top_n=99)["matches"]]

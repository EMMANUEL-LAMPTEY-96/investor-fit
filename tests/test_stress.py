import copy

import pytest

from investor_fit.finmodel.assumptions import EXAMPLE, EXAMPLE_FX, AssumptionError, normalize
from investor_fit.finmodel.engine import key_metrics, run
from investor_fit.finmodel.stress import (breaking_points, facts_from_model, full_analysis, loan_structures,
                                          stress_findings, stress_tests)
from investor_fit.objections import pre_mortem


@pytest.mark.parametrize("example", [EXAMPLE, EXAMPLE_FX])
@pytest.mark.parametrize("scenario", ["base", "downside", "upside"])
def test_balance_sheet_balances_in_every_scenario(example, scenario):
    r = run(example, scenario=scenario)
    assert all(abs(x) < 0.01 for x in r["balance_sheet"]["balance_check"])


def test_downside_is_worse_than_base_is_worse_than_upside():
    m = {s: key_metrics(run(EXAMPLE, scenario=s)) for s in ("downside", "base", "upside")}
    assert m["downside"]["min_dscr"] < m["base"]["min_dscr"] < m["upside"]["min_dscr"]


def test_fx_loan_creates_exchange_loss_and_drawdown_at_opening_rate():
    r = run(EXAMPLE_FX)
    assert r["debt"]["new"]["drawdown"][0] == pytest.approx(500000 * 12.0)
    assert sum(r["income_statement"]["fx_loss"]) > 0
    # revaluation: closing debt in cedis = USD balance x closing rate
    usd_close = r["debt"]["new_in_loan_currency"]["closing"][2]
    assert r["debt"]["new"]["closing"][2] == pytest.approx(usd_close * r["fx_rate"][2])


def test_devaluation_hurts_a_local_earner_with_a_dollar_loan_but_helps_an_exporter():
    local = copy.deepcopy(EXAMPLE_FX)
    for s in local["revenue_streams"]:
        s.pop("currency", None)
        s["price"] = s["price"] * 12 if s["price"] < 5000 else s["price"]
    hurt = key_metrics(run(local, shocks={"fx_devaluation": 0.3}))["min_dscr"] < key_metrics(run(local))["min_dscr"]
    helped = key_metrics(run(EXAMPLE_FX, shocks={"fx_devaluation": 0.3}))["min_dscr"] > key_metrics(run(EXAMPLE_FX))["min_dscr"]
    assert hurt and helped


def test_two_foreign_currencies_are_rejected():
    a = copy.deepcopy(EXAMPLE_FX)
    a["existing_debt"]["currency"] = "EUR"
    with pytest.raises(AssumptionError, match="one foreign currency"):
        normalize(a)


def test_breaking_point_is_where_the_test_actually_fails():
    bps = breaking_points(EXAMPLE)
    bp = next(b for b in bps if b["shock"] == "fall in selling prices" and "1.00x" in b["fails"])
    v = bp["value"]
    assert key_metrics(run(EXAMPLE, shocks={"price": -(v - 0.005)}))["min_dscr"] >= 1.0
    assert key_metrics(run(EXAMPLE, shocks={"price": -(v + 0.005)}))["min_dscr"] < 1.0


def test_loan_options_really_pass():
    ls = loan_structures(EXAMPLE_FX)
    assert ls["options"]
    for o in ls["options"]:
        trial = copy.deepcopy(EXAMPLE_FX)
        trial["new_debt"].update(o["terms"])
        assert key_metrics(run(trial))["min_dscr"] >= 1.25
        assert key_metrics(run(trial, scenario="downside"))["min_dscr"] >= 1.0


def test_stress_table_skips_currency_test_when_everything_is_in_one_currency():
    assert not any("currency" in t["test"] for t in stress_tests(EXAMPLE))
    assert any("currency" in t["test"] for t in stress_tests(EXAMPLE_FX))


def test_stress_findings_and_model_facts_feed_the_pre_mortem():
    areas = {f["area"] for f in stress_findings(EXAMPLE)}
    assert {"Stress test", "Thin margin"} <= areas
    facts = facts_from_model(EXAMPLE_FX)
    assert facts["loan_currency"] == "USD" and facts["foreign_revenue_share"] > 0.9
    c = {"country": "GH", "sector": "agri_processing", "instruments_wanted": ["debt"], **facts}
    ids = {o["id"] for o in pre_mortem(c, {"type": "impact_lender", "instruments": ["debt"]})["likely_objections"]}
    assert "currency_mismatch" not in ids  # exporter earning in USD: natural hedge
    assert "weak_debt_service_coverage" in ids
    local = {**c, "foreign_revenue_share": 0.1}
    ids = {o["id"] for o in pre_mortem(local, {"type": "impact_lender", "instruments": ["debt"]})["likely_objections"]}
    assert "currency_mismatch" in ids


def test_full_analysis_runs_fast():
    import time

    t = time.time()
    full_analysis(EXAMPLE_FX)
    assert time.time() - t < 5

import copy
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from investor_fit.finmodel.assumptions import EXAMPLE, AssumptionError, normalize
from investor_fit.finmodel.engine import funding_analysis, run
from investor_fit.finmodel.review import assess_projections, from_engine, scan_workbook

openpyxl = pytest.importorskip("openpyxl")
from investor_fit.finmodel.excel import build_workbook  # noqa: E402

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")


def random_assumptions(seed):
    rnd = random.Random(seed)
    a = copy.deepcopy(EXAMPLE)
    a["years"] = rnd.randint(3, 7)
    a["revenue_streams"][0]["volume_growth"] = [rnd.uniform(-0.1, 0.4) for _ in range(a["years"])]
    a["cogs_pct_revenue"] = rnd.uniform(0.3, 0.9)
    a["capex"] = [{"name": "Kit", "amounts": [rnd.choice([0, 50000, 200000]) for _ in range(a["years"])]}]
    a["new_debt"].update(amount=rnd.choice([0, 300000, 900000]), tenor_years=rnd.randint(2, 6),
                         grace_years=rnd.randint(0, 1), drawdown_year=rnd.randint(1, 2))
    a["new_equity"] = {"amount": rnd.choice([0, 250000]), "year": rnd.randint(1, 3)}
    a["existing_debt"]["remaining_years"] = rnd.randint(1, 4)
    return a


# ---------- engine

@pytest.mark.parametrize("seed", range(25))
def test_balance_sheet_always_balances(seed):
    r = run(random_assumptions(seed))
    assert all(abs(x) < 0.01 for x in r["balance_sheet"]["balance_check"])


def test_loan_is_fully_repaid_within_tenor():
    a = copy.deepcopy(EXAMPLE)
    a["new_debt"].update(amount=500000, tenor_years=4, grace_years=1, drawdown_year=1)
    r = run(a)
    new = r["debt"]["new"]
    assert new["repayment"][0] == 0  # grace year
    assert abs(sum(new["repayment"]) - 500000) < 0.01
    assert new["closing"][3] == pytest.approx(0, abs=0.01)


def test_funding_need_detects_overraising():
    fa = funding_analysis(EXAMPLE)
    assert fa["funding_need"] < fa["funding_raised"]
    assert fa["balance_sheet_balances"]


def test_bad_assumptions_are_explained():
    a = copy.deepcopy(EXAMPLE)
    a["tax_rate"] = 25  # percent instead of fraction
    with pytest.raises(AssumptionError, match="tax_rate"):
        normalize(a)


# ---------- Excel matches the engine

@pytest.mark.skipif(not SOFFICE, reason="LibreOffice not installed")
@pytest.mark.parametrize("seed", [1, 7, 13])
def test_excel_formulas_match_engine(tmp_path, seed):
    a = random_assumptions(seed)
    src = tmp_path / "model.xlsx"
    build_workbook(a, str(src))
    out = tmp_path / "out"
    subprocess.run([SOFFICE, "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
                    "--outdir", str(out), str(src)], check=True, capture_output=True, timeout=180)
    wb = openpyxl.load_workbook(out / "model.xlsx", data_only=True)
    e = run(a)
    n = e["assumptions"]["years"]

    def row(sheet, label):
        ws = wb[sheet]
        for r in range(1, ws.max_row + 1):
            if ws.cell(r, 1).value == label:
                return [ws.cell(r, 4 + i).value for i in range(n)]
        raise KeyError(label)

    for sheet, label, expected in [
        ("Income", "Total revenue", e["income_statement"]["revenue"]),
        ("Income", "Total depreciation", e["income_statement"]["depreciation"]),
        ("Income", "Interest", e["income_statement"]["interest"]),
        ("Income", "Net profit", e["income_statement"]["net_income"]),
        ("Balance", "Cash", e["balance_sheet"]["cash"]),
        ("Balance", "Debt", e["balance_sheet"]["debt"]),
        ("Balance", "Check (should be zero)", [0] * n),
    ]:
        got = row(sheet, label)
        assert got == pytest.approx(expected, abs=0.01), f"{sheet}/{label}"

    # The reviewer finds nothing wrong with a model we built.
    assert scan_workbook(str(out / "model.xlsx"))["findings"] == []


# ---------- reviewer

def test_reviewer_flags_planted_problems(tmp_path):
    p = tmp_path / "m.xlsx"
    build_workbook(EXAMPLE, str(p))
    wb = openpyxl.load_workbook(p)
    ws = wb["Income"]
    labels = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
    ws.cell(labels["Total revenue"], 6).value = 2_500_000          # typed over a formula
    ws.cell(labels["Gross profit"], 7).value = f"=G{labels['Total revenue']}*0.55"  # hidden assumption
    wb.save(p)
    areas = {f["area"] for f in scan_workbook(str(p))["findings"]}
    assert {"Hardcoded numbers", "Inconsistent formulas", "Numbers inside formulas"} <= areas


def test_reviewer_flags_model_without_formulas(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r, row in enumerate([["Revenue", 100, 200, 400], ["Costs", 50, 90, 150]], 1):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
    p = tmp_path / "flat.xlsx"
    wb.save(p)
    assert scan_workbook(str(p))["findings"][0]["severity"] == "critical"


def test_projection_review_catches_the_classic_problems():
    r = assess_projections({
        "years": [2027, 2028, 2029, 2030], "revenue": [100, 260, 700, 1500],
        "ebitda": [5, 60, 250, 600], "net_income": [-10, 20, 150, 400],
        "closing_cash": [-20, 30, 200, 500], "total_debt": [100, 80, 60, 40],
        "history": {"revenue": [80, 90], "ebitda": [4, 5]},
        "ask": {"amount": 100, "instrument": "debt", "tenor_years": 4, "interest_rate": 0.15,
                "use_of_funds_total": 70},
    })
    areas = {f["area"] for f in r["findings"]}
    assert {"Growth", "Cash", "Use of funds", "Debt capacity"} <= areas
    assert r["verdict"].startswith("Not ready")


def test_built_example_review_flags_low_dscr():
    r = assess_projections(from_engine(run(EXAMPLE)))
    assert any(f["area"] == "Debt capacity" for f in r["findings"])

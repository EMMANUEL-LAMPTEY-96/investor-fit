"""Write a formula-driven Excel model from assumptions.

Every calculated cell is a live Excel formula that points back to the Assumptions sheet, so the
founder can change any blue input and the whole model updates. The engine in engine.py computes
the same numbers and is used to test these formulas.

Requires openpyxl.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .assumptions import SHOCK_KEYS, normalize

FONT = "Arial"
BLUE = Font(name=FONT, size=10, color="0000FF")
BLACK = Font(name=FONT, size=10, color="000000")
GREEN = Font(name=FONT, size=10, color="008000")
BOLD = Font(name=FONT, size=10, bold=True)
GREY = Font(name=FONT, size=9, color="808080", italic=True)
TITLE = Font(name=FONT, size=14, bold=True, color="1F3A5F")
HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
SECTION = Font(name=FONT, size=10, bold=True, color="1F3A5F")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
SECTION_FILL = PatternFill("solid", fgColor="DDE6F0")
TOP = Border(top=Side(style="thin", color="000000"))

NUM = '#,##0;(#,##0);"-"'
NUM2 = '#,##0.00;(#,##0.00);"-"'
PCT = '0.0%;(0.0%);"-"'
MULT = '0.00"x";(0.00"x");"-"'
INT = "0"
TXT = "@"

SC = "Scenarios"
SHOCK_ROW0 = 8  # first shock row on the Scenarios sheet
SHOCK_LABELS = {
    "price": ("Selling prices", "% change", PCT),
    "volume": ("Volumes sold", "% change", PCT),
    "cogs_pts": ("Direct costs, % of revenue", "+ points", PCT),
    "fixed_costs": ("Fixed costs", "% change", PCT),
    "receivable_days": ("Customer payment days", "+ days", INT),
    "interest_pts": ("Interest rates", "+ points", PCT),
    "fx_devaluation": ("Fall of the local currency in year 1", "%", PCT),
}


def SH(key: str) -> str:
    """Absolute address of the shock in use (Scenarios sheet, column F)."""
    return f"{SC}!$F${SHOCK_ROW0 + SHOCK_KEYS.index(key)}"

FIRST_YEAR_COL = 4  # column D = year 1; column C = scalar input or opening balance


def col(t: int) -> str:
    return get_column_letter(FIRST_YEAR_COL + t - 1)


class Layout:
    """Two-pass layout: rows are allocated first, then formulas are written with known addresses."""

    def __init__(self, n: int):
        self.n = n
        self.rows: dict[tuple[str, str], int] = {}
        self.specs: dict[str, list] = {}

    def plan(self, sheet: str, spec: list) -> None:
        self.specs[sheet] = spec
        r = 6
        for item in spec:
            if item[0] == "line":
                self.rows[(sheet, item[1])] = r
            r += 1

    def a(self, sheet: str, key: str, t: int | None = None, here: str | None = None, absolute=False) -> str:
        """Address of a line in year t (None = column C)."""
        row = self.rows[(sheet, key)]
        c = "C" if t is None else col(t)
        addr = f"${c}${row}" if absolute else f"{c}{row}"
        return addr if sheet == here else f"{sheet}!{addr}"

    def rng(self, sheet: str, key: str, here: str | None = None) -> str:
        row = self.rows[(sheet, key)]
        r = f"${col(1)}${row}:${col(self.n)}${row}"
        return r if sheet == here else f"{sheet}!{r}"


def build_workbook(raw: dict[str, Any], path: str, analysis: dict | None = None) -> str:
    """analysis: output of stress.full_analysis(raw); computed here if not given."""
    a = normalize(raw)
    if analysis is None:
        from .stress import full_analysis

        analysis = full_analysis(raw)
    n = a["years"]
    L = Layout(n)
    S = "Assumptions"

    def A(key, t=None, here=None):  # absolute link to an Assumptions scalar, relative for per-year
        return L.a(S, key, t, here, absolute=(t is None))

    idx = lambda t, here: L.a(S, "idx", t, here)  # noqa: E731

    # ------------------------------------------------------------------ Assumptions
    asum: list = [
        ("section", "General"),
        ("line", "first_year", "First projection year", "year", ("C", a["first_year"], INT), None),
        ("line", "idx", "Year number", "#", None, ("const", list(range(1, n + 1)), INT)),
        ("line", "tax_rate", "Corporate tax rate", "%", ("C", a["tax_rate"], PCT), None),
        ("section", "Currency (rows below only matter if a loan or a sale is in a foreign currency)"),
        ("line", "ccy", "Model currency (all figures are in this)", "code", ("C", a["currency"], TXT), None),
        ("line", "fccy", "Foreign currency", "code", ("C", a["foreign_currency"] or a["currency"], TXT), None),
        ("line", "fx_spot", "Exchange rate at start (model currency per 1 foreign)", "rate",
         ("C", a["fx"]["rate"], NUM2), None),
        ("line", "fx_dep", "Expected yearly fall of the model currency", "%", None, ("inputs", a["fx"]["depreciation"], PCT)),
        ("line", "fx", "Exchange rate used (includes the scenario)", "rate", None,
         ("formula", lambda t, r: (f"=$C${L.rows[(S, 'fx_spot')]}*(1+{SH('fx_devaluation')})*(1+{col(1)}{L.rows[(S, 'fx_dep')]})"
                                   if t == 1 else f"={col(t - 1)}{r}*(1+{col(t)}{L.rows[(S, 'fx_dep')]})"), NUM2)),
        ("section", "Revenue"),
    ]
    for i, s in enumerate(a["revenue_streams"], 1):
        asum += [
            ("line", f"s{i}_ccy", f"{s['name']}: currency of the price", "code", ("C", s["currency"], TXT), None),
            ("line", f"s{i}_vol_g", f"{s['name']}: volume growth", "%", None, ("growth", s["volume_growth"], PCT)),
            ("line", f"s{i}_vol", f"{s['name']}: volume", s["unit"], None, ("grow", s["volume"], f"s{i}_vol_g", NUM)),
            ("line", f"s{i}_price_g", f"{s['name']}: price growth", "%", None, ("growth", s["price_growth"], PCT)),
            ("line", f"s{i}_price", f"{s['name']}: price per {s['unit'].rstrip('s')}", a["currency"], None,
             ("grow", s["price"], f"s{i}_price_g", NUM2)),
        ]
    asum += [
        ("section", "Costs"),
        ("line", "cogs_pct", "Direct costs (COGS), % of revenue", "%", None, ("inputs", a["cogs_pct_revenue"], PCT)),
        ("line", "varopex_pct", "Variable operating costs, % of revenue", "%", None,
         ("inputs", a["variable_opex_pct_revenue"], PCT)),
    ]
    for i, f in enumerate(a["fixed_costs"], 1):
        asum += [
            ("line", f"f{i}_g", f"{f['name']}: growth", "%", None, ("growth", f["growth"], PCT)),
            ("line", f"f{i}_amt", f"{f['name']}", a["currency"], None, ("grow", f["amount"], f"f{i}_g", NUM)),
        ]
    asum += [("section", "Investment (capex)")]
    for i, c in enumerate(a["capex"], 1):
        asum += [("line", f"c{i}", c["name"], a["currency"], None, ("inputs", c["amounts"], NUM))]
    asum += [
        ("line", "capex_total", "Total capex", a["currency"], None,
         ("sum", [f"c{i}" for i in range(1, len(a["capex"]) + 1)], NUM)),
        ("line", "dep_years", "Depreciation life of new assets", "years", ("C", a["depreciation_years"], INT), None),
        ("line", "ppe_years", "Remaining life of existing assets", "years", ("C", a["existing_ppe_remaining_years"], INT), None),
        ("section", "Working capital"),
        ("line", "ar_days", "Customer payment days (receivables)", "days", ("C", a["receivable_days"], INT), None),
        ("line", "inv_days", "Stock days (inventory)", "days", ("C", a["inventory_days"], INT), None),
        ("line", "ap_days", "Supplier payment days (payables)", "days", ("C", a["payable_days"], INT), None),
        ("section", "Opening balance sheet (start of first year)"),
        ("line", "ob_cash", "Cash", a["currency"], ("C", a["opening_balance"]["cash"], NUM), None),
        ("line", "ob_ar", "Receivables", a["currency"], ("C", a["opening_balance"]["receivables"], NUM), None),
        ("line", "ob_inv", "Inventory", a["currency"], ("C", a["opening_balance"]["inventory"], NUM), None),
        ("line", "ob_ppe", "Property, plant and equipment (net)", a["currency"], ("C", a["opening_balance"]["ppe_net"], NUM), None),
        ("line", "ob_ap", "Payables", a["currency"], ("C", a["opening_balance"]["payables"], NUM), None),
        ("section", "Existing debt"),
        ("line", "ed_bal", "Outstanding balance (in the loan's currency)", "loan ccy", ("C", a["existing_debt"]["balance"], NUM), None),
        ("line", "ed_ccy", "Currency of the loan", "code", ("C", a["existing_debt"]["currency"], TXT), None),
        ("line", "ed_rate", "Interest rate", "%", ("C", a["existing_debt"]["interest_rate"], PCT), None),
        ("line", "ed_rem", "Years left to repay", "years", ("C", a["existing_debt"]["remaining_years"], INT), None),
        ("section", "New funding sought"),
        ("line", "nd_ccy", "Currency of the new loan", "code", ("C", a["new_debt"]["currency"], TXT), None),
        ("line", "nd_amt", "New loan amount (in the loan's currency)", "loan ccy", ("C", a["new_debt"]["amount"], NUM), None),
        ("line", "nd_rate", "New loan interest rate", "%", ("C", a["new_debt"]["interest_rate"], PCT), None),
        ("line", "nd_tenor", "New loan tenor (incl. grace)", "years", ("C", a["new_debt"]["tenor_years"], INT), None),
        ("line", "nd_grace", "Grace period (interest only)", "years", ("C", a["new_debt"]["grace_years"], INT), None),
        ("line", "nd_year", "Loan drawn in year number", "#", ("C", a["new_debt"]["drawdown_year"], INT), None),
        ("line", "ne_amt", "New equity amount", a["currency"], ("C", a["new_equity"]["amount"], NUM), None),
        ("line", "ne_year", "Equity received in year number", "#", ("C", a["new_equity"]["year"], INT), None),
        ("section", "Use of funds"),
    ]
    for i, u in enumerate(a["use_of_funds"], 1):
        asum += [("line", f"u{i}", u["item"], a["currency"], ("C", u["amount"], NUM), None)]
    asum += [
        ("line", "uof_total", "Total use of funds", a["currency"],
         ("Csum", [f"u{i}" for i in range(1, len(a["use_of_funds"]) + 1)], NUM), None),
        ("section", "Lender tests"),
        ("line", "min_dscr", "Minimum debt service cover (DSCR)", "x", ("C", a["minimum_dscr"], MULT), None),
        ("line", "min_cash", "Minimum cash balance to keep", a["currency"], ("C", a["minimum_cash"], NUM), None),
    ]
    L.plan(S, asum)

    # ------------------------------------------------------------------ Income
    I = "Income"
    inc: list = [("section", "Revenue")]
    for i, s in enumerate(a["revenue_streams"], 1):
        inc.append(("line", f"rev{i}", s["name"], lambda t, i=i: (
            f"={A(f's{i}_vol', t, I)}*(1+{SH('volume')})*{A(f's{i}_price', t, I)}*(1+{SH('price')})"
            f"*IF({A(f's{i}_ccy', None, I)}={A('ccy', None, I)},1,{A('fx', t, I)})"), NUM, None))
    rev_keys = [f"rev{i}" for i in range(1, len(a["revenue_streams"]) + 1)]
    inc += [
        ("line", "revenue", "Total revenue", lambda t: "=" + "+".join(L.a(I, k, t, I) for k in rev_keys), NUM, "total"),
        ("line", "cogs", "Direct costs (COGS)",
         lambda t: f"={L.a(I, 'revenue', t, I)}*({A('cogs_pct', t, I)}+{SH('cogs_pts')})", NUM, None),
        ("line", "gross", "Gross profit", lambda t: f"={L.a(I, 'revenue', t, I)}-{L.a(I, 'cogs', t, I)}", NUM, "total"),
        ("section", "Operating costs"),
        ("line", "varopex", "Variable operating costs", lambda t: f"={L.a(I, 'revenue', t, I)}*{A('varopex_pct', t, I)}", NUM, None),
    ]
    fkeys = []
    for i, f in enumerate(a["fixed_costs"], 1):
        inc.append(("line", f"fix{i}", f["name"], lambda t, i=i: f"={A(f'f{i}_amt', t, I)}*(1+{SH('fixed_costs')})", NUM, "link"))
        fkeys.append(f"fix{i}")
    inc += [
        ("line", "opex", "Total operating costs",
         lambda t: "=" + "+".join([L.a(I, "varopex", t, I)] + [L.a(I, k, t, I) for k in fkeys]), NUM, "total"),
        ("line", "ebitda", "EBITDA", lambda t: f"={L.a(I, 'gross', t, I)}-{L.a(I, 'opex', t, I)}", NUM, "total"),
        ("line", "dep_old", "Depreciation: existing assets",
         lambda t: f"=IF({idx(t, I)}<={A('ppe_years', None, I)},{A('ob_ppe', None, I)}/{A('ppe_years', None, I)},0)", NUM, None),
        ("line", "dep_new", "Depreciation: new capex",
         lambda t: (f"=SUMPRODUCT(({L.rng(S, 'idx', I)}<={idx(t, I)})*(({idx(t, I)}-{L.rng(S, 'idx', I)})<"
                    f"{A('dep_years', None, I)})*{L.rng(S, 'capex_total', I)})/{A('dep_years', None, I)}"), NUM, None),
        ("line", "dep", "Total depreciation", lambda t: f"={L.a(I, 'dep_old', t, I)}+{L.a(I, 'dep_new', t, I)}", NUM, None),
        ("line", "ebit", "Operating profit (EBIT)", lambda t: f"={L.a(I, 'ebitda', t, I)}-{L.a(I, 'dep', t, I)}", NUM, "total"),
        ("line", "interest", "Interest", lambda t: f"={L.a('Debt', 'int_total', t, I)}", NUM, "link"),
        ("line", "fxloss", "Exchange loss on foreign-currency loans", lambda t: f"={L.a('Debt', 'fx_total', t, I)}", NUM, "link"),
        ("line", "ebt", "Profit before tax",
         lambda t: f"={L.a(I, 'ebit', t, I)}-{L.a(I, 'interest', t, I)}-{L.a(I, 'fxloss', t, I)}", NUM, "total"),
        ("line", "tax", "Tax", lambda t: f"=MAX(0,{L.a(I, 'ebt', t, I)})*{A('tax_rate', None, I)}", NUM, None),
        ("line", "ni", "Net profit", lambda t: f"={L.a(I, 'ebt', t, I)}-{L.a(I, 'tax', t, I)}", NUM, "grand"),
    ]
    L.plan(I, inc)

    # ------------------------------------------------------------------ Debt
    D = "Debt"
    prev = lambda key, t: (None if t == 1 else L.a(D, key, t - 1, D))  # noqa: E731
    def rates(prefix):
        """Exchange-rate rows for one loan: start-of-year and during-year rates (1 if same currency)."""
        same = f"{A(prefix + '_ccy', None, D)}={A('ccy', None, D)}"
        return [
            ("line", f"{prefix}_f0", "Exchange rate at start of year",
             lambda t: (f"=IF({same},1,{A('fx_spot', None, D)})" if t == 1
                        else f"=IF({same},1,{A('fx', t - 1, D)})"), NUM2, None),
            ("line", f"{prefix}_f", "Exchange rate during year", lambda t: f"=IF({same},1,{A('fx', t, D)})", NUM2, None),
        ]

    def local(prefix):
        g = lambda k, t: L.a(D, f"{prefix}_{k}", t, D)  # noqa: E731
        return [
            ("line", f"{prefix}_draw_l", "Drawdown", lambda t: f"={g('draw', t)}*{g('f0', t)}", NUM, None),
            ("line", f"{prefix}_int_l", "Interest", lambda t: f"={g('int', t)}*{g('f', t)}", NUM, None),
            ("line", f"{prefix}_rep_l", "Repayment", lambda t: f"={g('rep', t)}*{g('f', t)}", NUM, None),
            ("line", f"{prefix}_close_l", "Closing balance", lambda t: f"={g('close', t)}*{g('f', t)}", NUM, "total"),
            ("line", f"{prefix}_fx", "Exchange loss (revaluation)",
             lambda t: f"=({g('open', t)}+{g('draw', t)})*({g('f', t)}-{g('f0', t)})", NUM, None),
        ]

    debt: list = [
        ("section", "New loan, in the loan's currency"),
        ("line", "nd_open", "Opening balance", lambda t: "=0" if t == 1 else f"={prev('nd_close', t)}", NUM, None),
        ("line", "nd_draw", "Drawdown", lambda t: f"=IF({idx(t, D)}={A('nd_year', None, D)},{A('nd_amt', None, D)},0)", NUM, None),
        ("line", "nd_due", "Scheduled repayment",
         lambda t: (f"=IF(AND({A('nd_tenor', None, D)}>{A('nd_grace', None, D)},{idx(t, D)}>={A('nd_year', None, D)}+{A('nd_grace', None, D)},"
                    f"{idx(t, D)}<={A('nd_year', None, D)}+{A('nd_tenor', None, D)}-1),"
                    f"{A('nd_amt', None, D)}/({A('nd_tenor', None, D)}-{A('nd_grace', None, D)}),0)"), NUM, None),
        ("line", "nd_rep", "Repayment", lambda t: f"=MIN({L.a(D, 'nd_open', t, D)}+{L.a(D, 'nd_draw', t, D)},{L.a(D, 'nd_due', t, D)})", NUM, None),
        ("line", "nd_close", "Closing balance",
         lambda t: f"={L.a(D, 'nd_open', t, D)}+{L.a(D, 'nd_draw', t, D)}-{L.a(D, 'nd_rep', t, D)}", NUM, "total"),
        ("line", "nd_int", "Interest",
         lambda t: f"=({L.a(D, 'nd_open', t, D)}+{L.a(D, 'nd_draw', t, D)})*MAX(0,{A('nd_rate', None, D)}+{SH('interest_pts')})", NUM, None),
        *rates("nd"),
        ("section", "New loan, in the model currency"),
        *local("nd"),
        ("section", "Existing debt, in the loan's currency"),
        ("line", "ed_open", "Opening balance", lambda t: f"={A('ed_bal', None, D)}" if t == 1 else f"={prev('ed_close', t)}", NUM, None),
        ("line", "ed_draw", "Drawdown", lambda t: "=0", NUM, None),
        ("line", "ed_rep", "Repayment",
         lambda t: (f"=MIN({L.a(D, 'ed_open', t, D)},IF(AND({A('ed_rem', None, D)}>0,{idx(t, D)}<={A('ed_rem', None, D)}),"
                    f"{A('ed_bal', None, D)}/{A('ed_rem', None, D)},0))"), NUM, None),
        ("line", "ed_close", "Closing balance", lambda t: f"={L.a(D, 'ed_open', t, D)}-{L.a(D, 'ed_rep', t, D)}", NUM, "total"),
        ("line", "ed_int", "Interest",
         lambda t: f"={L.a(D, 'ed_open', t, D)}*MAX(0,{A('ed_rate', None, D)}+{SH('interest_pts')})", NUM, None),
        *rates("ed"),
        ("section", "Existing debt, in the model currency"),
        *local("ed"),
        ("section", "Totals, in the model currency"),
        ("line", "int_total", "Total interest", lambda t: f"={L.a(D, 'nd_int_l', t, D)}+{L.a(D, 'ed_int_l', t, D)}", NUM, None),
        ("line", "prin_total", "Total principal repaid", lambda t: f"={L.a(D, 'nd_rep_l', t, D)}+{L.a(D, 'ed_rep_l', t, D)}", NUM, None),
        ("line", "ds_total", "Total debt service", lambda t: f"={L.a(D, 'int_total', t, D)}+{L.a(D, 'prin_total', t, D)}", NUM, "total"),
        ("line", "fx_total", "Total exchange loss", lambda t: f"={L.a(D, 'nd_fx', t, D)}+{L.a(D, 'ed_fx', t, D)}", NUM, None),
        ("line", "debt_total", "Total debt outstanding", lambda t: f"={L.a(D, 'nd_close_l', t, D)}+{L.a(D, 'ed_close_l', t, D)}", NUM, "grand"),
    ]
    L.plan(D, debt)

    # ------------------------------------------------------------------ Balance sheet (column C = opening)
    B = "Balance"

    def bprev(key, t):
        return L.a(B, key, None, B) if t == 1 else L.a(B, key, t - 1, B)

    bal: list = [
        ("section", "Assets"),
        ("line", "cash", "Cash", lambda t: f"={L.a('CashFlow', 'close_cash', t, B)}", NUM, "link", lambda: f"={A('ob_cash', None, B)}"),
        ("line", "ar", "Receivables", lambda t: f"={L.a(I, 'revenue', t, B)}*({A('ar_days', None, B)}+{SH('receivable_days')})/365",
         NUM, None, lambda: f"={A('ob_ar', None, B)}"),
        ("line", "inv", "Inventory", lambda t: f"={L.a(I, 'cogs', t, B)}*{A('inv_days', None, B)}/365", NUM, None, lambda: f"={A('ob_inv', None, B)}"),
        ("line", "ppe", "Property, plant and equipment (net)",
         lambda t: f"={bprev('ppe', t)}+{A('capex_total', t, B)}-{L.a(I, 'dep', t, B)}", NUM, None, lambda: f"={A('ob_ppe', None, B)}"),
        ("line", "ta", "Total assets",
         lambda t: f"=SUM({col(t)}{L.rows[(B, 'cash')]}:{col(t)}{L.rows[(B, 'ppe')]})", NUM, "total",
         lambda: f"=SUM(C{L.rows[(B, 'cash')]}:C{L.rows[(B, 'ppe')]})"),
        ("section", "Liabilities and equity"),
        ("line", "ap", "Payables", lambda t: f"={L.a(I, 'cogs', t, B)}*{A('ap_days', None, B)}/365", NUM, None, lambda: f"={A('ob_ap', None, B)}"),
        ("line", "debt", "Debt", lambda t: f"={L.a(D, 'debt_total', t, B)}", NUM, "link", lambda: f"={A('ed_bal', None, B)}*IF({A('ed_ccy', None, B)}={A('ccy', None, B)},1,{A('fx_spot', None, B)})"),
        ("line", "equity", "Equity",
         lambda t: f"={bprev('equity', t)}+{L.a('CashFlow', 'eq_in', t, B)}+{L.a(I, 'ni', t, B)}", NUM, None,
         lambda: f"=C{L.rows[(B, 'ta')]}-C{L.rows[(B, 'ap')]}-C{L.rows[(B, 'debt')]}"),
        ("line", "tle", "Total liabilities and equity",
         lambda t: f"={L.a(B, 'ap', t, B)}+{L.a(B, 'debt', t, B)}+{L.a(B, 'equity', t, B)}", NUM, "total",
         lambda: f"=C{L.rows[(B, 'ap')]}+C{L.rows[(B, 'debt')]}+C{L.rows[(B, 'equity')]}"),
        ("line", "check", "Check (should be zero)", lambda t: f"=ROUND({L.a(B, 'ta', t, B)}-{L.a(B, 'tle', t, B)},2)", NUM, None,
         lambda: f"=ROUND(C{L.rows[(B, 'ta')]}-C{L.rows[(B, 'tle')]},2)"),
    ]
    L.plan(B, bal)

    # ------------------------------------------------------------------ Cash flow
    C = "CashFlow"

    def delta(key, t):
        return f"{L.a(B, key, t, C)}-{L.a(B, key, None, C) if t == 1 else L.a(B, key, t - 1, C)}"

    cf: list = [
        ("section", "Operating activities"),
        ("line", "ni", "Net profit", lambda t: f"={L.a(I, 'ni', t, C)}", NUM, "link"),
        ("line", "dep", "Add back depreciation", lambda t: f"={L.a(I, 'dep', t, C)}", NUM, "link"),
        ("line", "fxadd", "Add back exchange loss (not cash)", lambda t: f"={L.a(I, 'fxloss', t, C)}", NUM, "link"),
        ("line", "d_ar", "(Increase) in receivables", lambda t: f"=-({delta('ar', t)})", NUM, None),
        ("line", "d_inv", "(Increase) in inventory", lambda t: f"=-({delta('inv', t)})", NUM, None),
        ("line", "d_ap", "Increase in payables", lambda t: f"={delta('ap', t)}", NUM, None),
        ("line", "cfo", "Cash from operations",
         lambda t: f"=SUM({col(t)}{L.rows[(C, 'ni')]}:{col(t)}{L.rows[(C, 'd_ap')]})", NUM, "total"),
        ("section", "Investing activities"),
        ("line", "capex", "Capital expenditure", lambda t: f"=-{A('capex_total', t, C)}", NUM, None),
        ("line", "cfi", "Cash from investing", lambda t: f"={L.a(C, 'capex', t, C)}", NUM, "total"),
        ("section", "Financing activities"),
        ("line", "draw", "New loan drawn", lambda t: f"={L.a(D, 'nd_draw_l', t, C)}", NUM, "link"),
        ("line", "nd_rep", "New loan repaid", lambda t: f"=-{L.a(D, 'nd_rep_l', t, C)}", NUM, "link"),
        ("line", "ed_rep", "Existing debt repaid", lambda t: f"=-{L.a(D, 'ed_rep_l', t, C)}", NUM, "link"),
        ("line", "eq_in", "New equity received", lambda t: f"=IF({idx(t, C)}={A('ne_year', None, C)},{A('ne_amt', None, C)},0)", NUM, None),
        ("line", "cff", "Cash from financing",
         lambda t: f"=SUM({col(t)}{L.rows[(C, 'draw')]}:{col(t)}{L.rows[(C, 'eq_in')]})", NUM, "total"),
        ("section", "Cash position"),
        ("line", "net", "Net change in cash",
         lambda t: f"={L.a(C, 'cfo', t, C)}+{L.a(C, 'cfi', t, C)}+{L.a(C, 'cff', t, C)}", NUM, None),
        ("line", "open_cash", "Opening cash",
         lambda t: f"={L.a(B, 'cash', None, C)}" if t == 1 else f"={L.a(C, 'close_cash', t - 1, C)}", NUM, None),
        ("line", "close_cash", "Closing cash", lambda t: f"={L.a(C, 'open_cash', t, C)}+{L.a(C, 'net', t, C)}", NUM, "grand"),
        ("line", "cash_ex", "Cash without the new funding (approx.)",
         lambda t: (f"={L.a(C, 'close_cash', t, C)}-SUM(${col(1)}${L.rows[(C, 'draw')]}:{col(t)}{L.rows[(C, 'draw')]})"
                    f"-SUM(${col(1)}${L.rows[(C, 'nd_rep')]}:{col(t)}{L.rows[(C, 'nd_rep')]})"
                    f"-SUM(${col(1)}${L.rows[(C, 'eq_in')]}:{col(t)}{L.rows[(C, 'eq_in')]})"
                    f"+SUM({D}!${col(1)}${L.rows[(D, 'nd_int_l')]}:{D}!{col(t)}{L.rows[(D, 'nd_int_l')]})"), NUM, None),
    ]
    L.plan(C, cf)

    # ------------------------------------------------------------------ Ratios
    R = "Ratios"

    def safe_div(num, den):
        return f'=IF({den}<>0,{num}/{den},"n/a")'

    rat: list = [
        ("section", "Growth and margins"),
        ("line", "growth", "Revenue growth",
         lambda t: '="n/a"' if t == 1 else
         f'=IF({L.a(I, "revenue", t - 1, R)}<>0,{L.a(I, "revenue", t, R)}/{L.a(I, "revenue", t - 1, R)}-1,"n/a")',
         PCT, None),
        ("line", "gm", "Gross margin", lambda t: safe_div(L.a(I, "gross", t, R), L.a(I, "revenue", t, R)), PCT, None),
        ("line", "em", "EBITDA margin", lambda t: safe_div(L.a(I, "ebitda", t, R), L.a(I, "revenue", t, R)), PCT, None),
        ("line", "nm", "Net margin", lambda t: safe_div(L.a(I, "ni", t, R), L.a(I, "revenue", t, R)), PCT, None),
        ("section", "Lender tests"),
        ("line", "dscr", "Debt service cover (DSCR)",
         lambda t: f'=IF({L.a(D, "ds_total", t, R)}>0,({L.a(I, "ebitda", t, R)}-{L.a(I, "tax", t, R)})/{L.a(D, "ds_total", t, R)},"n/a")',
         MULT, None),
        ("line", "dscr_ok", "DSCR meets minimum?",
         lambda t: f'=IF(ISNUMBER({L.a(R, "dscr", t, R)}),IF({L.a(R, "dscr", t, R)}>={A("min_dscr", None, R)},"OK","BELOW"),"-")',
         None, None),
        ("line", "nd_ebitda", "Net debt / EBITDA",
         lambda t: f'=IF({L.a(I, "ebitda", t, R)}>0,({L.a(B, "debt", t, R)}-{L.a(B, "cash", t, R)})/{L.a(I, "ebitda", t, R)},"n/a")',
         MULT, None),
        ("line", "cash_ok", "Cash above minimum?",
         lambda t: f'=IF({L.a(B, "cash", t, R)}>={A("min_cash", None, R)},"OK","BELOW")', None, None),
    ]
    L.plan(R, rat)

    # ------------------------------------------------------------------ write
    wb = Workbook()
    wb.remove(wb.active)
    cover = wb.create_sheet("Cover")
    sheets = {name: wb.create_sheet(name) for name in (S, I, D, B, C, R)}
    years = [a["first_year"] + i for i in range(n)]

    titles = {S: "Assumptions (blue cells are inputs: change them and the model updates)",
              I: "Income statement", D: "Debt schedule", B: "Balance sheet (end of year)",
              C: "Cash flow statement", R: "Ratios and lender tests"}

    for name, ws in sheets.items():
        ws.sheet_view.showGridLines = False
        ws["A1"] = f"{a['company_name']}"
        ws["A1"].font = TITLE
        ws["A2"] = f"{titles[name]}  ·  {a['currency']}"
        ws["A2"].font = GREY
        ws.column_dimensions["A"].width = 44
        ws.column_dimensions["B"].width = 11
        ws.column_dimensions["C"].width = 14
        for t in range(1, n + 1):
            ws.column_dimensions[col(t)].width = 14
        hdr = 4
        for c in range(1, FIRST_YEAR_COL + n):
            ws.cell(row=hdr, column=c).fill = HEAD_FILL
            ws.cell(row=hdr, column=c).font = HEAD
        ws.cell(row=hdr, column=1, value="")
        ws.cell(row=hdr, column=2, value="Unit")
        ws.cell(row=hdr, column=3, value="Opening" if name == B else ("Input" if name == S else ""))
        for t in range(1, n + 1):
            cell = ws.cell(row=hdr, column=FIRST_YEAR_COL + t - 1)
            cell.value = f"={A('first_year', None, name)}+{t - 1}" if name != S else (f"=$C${L.rows[(S, 'first_year')]}+{t - 1}")
            cell.number_format = INT
            cell.alignment = Alignment(horizontal="right")
        ws.freeze_panes = "D5"

        r = 6
        for item in L.specs[name]:
            if item[0] == "section":
                c0 = ws.cell(row=r, column=1, value=item[1])
                for c in range(1, FIRST_YEAR_COL + n):
                    ws.cell(row=r, column=c).fill = SECTION_FILL
                c0.font = SECTION
                r += 1
                continue
            _, key, label, *rest = item
            ws.cell(row=r, column=1, value=label).font = BLACK
            if name == S:
                unit, scalar, per_year = rest
                ws.cell(row=r, column=2, value=unit).font = GREY
                if scalar:
                    kind, val, fmt = scalar
                    cell = ws.cell(row=r, column=3)
                    if kind == "Csum":
                        cell.value = ("=" + "+".join(f"C{L.rows[(S, k)]}" for k in val)) if val else 0
                        cell.font = BLACK
                    else:
                        cell.value = val
                        cell.font = BLUE
                        cell.fill = INPUT_FILL
                    cell.number_format = fmt
                if per_year:
                    kind = per_year[0]
                    for t in range(1, n + 1):
                        cell = ws.cell(row=r, column=FIRST_YEAR_COL + t - 1)
                        if kind == "const":
                            cell.value, cell.font, fmt = per_year[1][t - 1], GREY, per_year[2]
                        elif kind == "inputs":
                            cell.value, cell.font, fmt = per_year[1][t - 1], BLUE, per_year[2]
                            cell.fill = INPUT_FILL
                        elif kind == "growth":
                            fmt = per_year[2]
                            if t == 1:
                                cell.value, cell.font = "-", GREY
                                cell.alignment = Alignment(horizontal="right")
                            else:
                                cell.value, cell.font = per_year[1][t - 1], BLUE
                                cell.fill = INPUT_FILL
                        elif kind == "grow":
                            _, base, gkey, fmt = per_year
                            if t == 1:
                                cell.value, cell.font = base, BLUE
                                cell.fill = INPUT_FILL
                            else:
                                cell.value = f"={col(t - 1)}{r}*(1+{col(t)}{L.rows[(S, gkey)]})"
                                cell.font = BLACK
                        elif kind == "formula":
                            cell.value, cell.font, fmt = per_year[1](t, r), BLACK, per_year[2]
                        elif kind == "sum":
                            keys, fmt = per_year[1], per_year[2]
                            cell.value = ("=" + "+".join(f"{col(t)}{L.rows[(S, k)]}" for k in keys)) if keys else 0
                            cell.font = BLACK
                        cell.number_format = fmt
            else:
                fn, fmt, style, *opening = rest
                for t in range(1, n + 1):
                    cell = ws.cell(row=r, column=FIRST_YEAR_COL + t - 1, value=fn(t))
                    cell.font = GREEN if style == "link" else (BOLD if style in ("total", "grand") else BLACK)
                    if fmt:
                        cell.number_format = fmt
                    else:
                        cell.alignment = Alignment(horizontal="right")
                    if style in ("total", "grand"):
                        cell.border = TOP
                if opening and opening[0]:
                    cell = ws.cell(row=r, column=3, value=opening[0]())
                    cell.font = GREEN
                    cell.number_format = fmt
                if style in ("total", "grand"):
                    ws.cell(row=r, column=1).font = BOLD
            r += 1

    sheets[C].cell(row=L.rows[(C, "cash_ex")], column=1).comment = Comment(
        "Closing cash minus the new loan and equity and their repayments, plus the new loan's interest. "
        "Ignores the small tax effect of that interest. A negative value means the business cannot fund "
        "itself without new money.", "Investor-Fit Agent")

    # ------------------------------------------------------------------ Summary
    sm = wb.create_sheet("Summary", 1)
    sm.sheet_view.showGridLines = False
    sm.column_dimensions["A"].width = 44
    sm.column_dimensions["B"].width = 11
    sm.column_dimensions["C"].width = 16
    for t in range(1, n + 1):
        sm.column_dimensions[col(t)].width = 14
    sm["A1"] = a["company_name"]
    sm["A1"].font = TITLE
    sm["A2"] = f"Summary  ·  {a['currency']}"
    sm["A2"].font = GREY
    sm["A3"] = f'="Scenario shown: "&{SC}!$D$4&"  (change it on the Scenarios sheet)"'
    sm["A3"].font = BOLD
    for c in range(1, FIRST_YEAR_COL + n):
        sm.cell(row=4, column=c).fill = HEAD_FILL
        sm.cell(row=4, column=c).font = HEAD
    for t in range(1, n + 1):
        cell = sm.cell(row=4, column=FIRST_YEAR_COL + t - 1, value=f"={A('first_year')}+{t - 1}")
        cell.number_format = INT
    rows = [
        ("Revenue", I, "revenue", NUM), ("Gross margin", R, "gm", PCT), ("EBITDA", I, "ebitda", NUM),
        ("EBITDA margin", R, "em", PCT), ("Net profit", I, "ni", NUM), ("Closing cash", B, "cash", NUM),
        ("Total debt", B, "debt", NUM), ("Debt service cover (DSCR)", R, "dscr", MULT),
    ]
    r = 5
    for label, sh, key, fmt in rows:
        sm.cell(row=r, column=1, value=label).font = BLACK
        for t in range(1, n + 1):
            cell = sm.cell(row=r, column=FIRST_YEAR_COL + t - 1, value=f"={L.a(sh, key, t)}")
            cell.font, cell.number_format = GREEN, fmt
        r += 1
    r += 1
    sm.cell(row=r, column=1, value="Funding check").font = SECTION
    for c in range(1, 4):
        sm.cell(row=r, column=c).fill = SECTION_FILL
    r += 1
    checks = [
        ("New money raised (loan + equity, at the starting exchange rate)",
         f"={A('nd_amt')}*IF({A('nd_ccy')}={A('ccy')},1,{A('fx_spot')})+{A('ne_amt')}", NUM),
        ("Total use of funds", f"={A('uof_total')}", NUM),
        ("Raised minus use of funds", f"=C{r}-C{r + 1}", NUM),
        ("Lowest cash without the new funding (approx.)", f"=MIN({L.rng(C, 'cash_ex')})", NUM),
        ("Estimated funding need (approx.)", f"=MAX(0,{A('min_cash')}-C{r + 3})", NUM),
        ("Lowest cash with the new funding", f"=MIN({L.rng(B, 'cash')})", NUM),
        ("Lowest DSCR", f"=IF(COUNT({L.rng(R, 'dscr')})>0,MIN({L.rng(R, 'dscr')}),\"n/a\")", MULT),
        ("Minimum DSCR required", f"={A('min_dscr')}", MULT),
        ("DSCR test", f"=IF(ISNUMBER(C{r + 6}),IF(C{r + 6}>=C{r + 7},\"PASS\",\"FAIL\"),\"n/a\")", None),
        ("Balance sheet balances", f"=IF(SUMPRODUCT(ABS({L.rng(B, 'check')}))<1,\"OK\",\"ERROR\")", None),
    ]
    for label, formula, fmt in checks:
        sm.cell(row=r, column=1, value=label).font = BLACK
        cell = sm.cell(row=r, column=3, value=formula)
        cell.font = BOLD
        if fmt:
            cell.number_format = fmt
        else:
            cell.alignment = Alignment(horizontal="right")
        r += 1

    # ------------------------------------------------------------------ Scenarios (live switch)
    sc = wb.create_sheet(SC, 2)
    sc.sheet_view.showGridLines = False
    for colname, w in zip("ABCDEF", (44, 11, 13, 13, 13, 13)):
        sc.column_dimensions[colname].width = w
    sc["A1"] = a["company_name"]
    sc["A1"].font = TITLE
    sc["A2"] = "Scenarios: switch the whole model between the base plan, a bad year and a good year"
    sc["A2"].font = GREY
    sc["A4"] = "Scenario in use (1 = Base, 2 = Downside, 3 = Upside)"
    sc["A4"].font = BOLD
    sc["C4"] = 1
    sc["C4"].font, sc["C4"].fill = BLUE, INPUT_FILL
    sc["D4"] = '=CHOOSE($C$4,"Base","Downside","Upside")'
    sc["D4"].font = BOLD
    for c, h in enumerate(["Shock", "Unit", "Base", "Downside", "Upside", "In use"], 1):
        cell = sc.cell(row=SHOCK_ROW0 - 1, column=c, value=h)
        cell.fill, cell.font = HEAD_FILL, HEAD
    for i, key in enumerate(SHOCK_KEYS):
        r = SHOCK_ROW0 + i
        label, unit, fmt = SHOCK_LABELS[key]
        sc.cell(row=r, column=1, value=label).font = BLACK
        sc.cell(row=r, column=2, value=unit).font = GREY
        for c, name in ((3, "base"), (4, "downside"), (5, "upside")):
            cell = sc.cell(row=r, column=c, value=a["scenarios"][name][key])
            cell.font, cell.number_format = BLUE, fmt
            if c > 3:
                cell.fill = INPUT_FILL
        cell = sc.cell(row=r, column=6, value=f"=INDEX(C{r}:E{r},1,$C$4)")
        cell.font, cell.number_format = BOLD, fmt
    note_r = SHOCK_ROW0 + len(SHOCK_KEYS) + 1
    for i, text in enumerate([
        "Every sheet uses the 'In use' column. Set C4 to 2 to see the whole model in the downside case.",
        "Edit the downside and upside shocks to suit the business; keep Base at zero.",
        "Price and volume shocks change revenue; direct-cost and interest shocks add percentage points;",
        "the currency shock is a one-off fall in year 1 and only matters for foreign-currency loans or sales.",
    ]):
        sc.cell(row=note_r + i, column=1, value=text).font = GREY

    # ------------------------------------------------------------------ Stress tests (values)
    st = wb.create_sheet("Stress tests")
    st.sheet_view.showGridLines = False
    for colname, w in zip("ABCDEFGH", (64, 14, 10, 16, 10, 16, 14, 14)):
        st.column_dimensions[colname].width = w
    st["A1"] = a["company_name"]
    st["A1"].font = TITLE
    st["A2"] = ("Stress tests, breaking points and loan options. These are values calculated by the agent when the "
                "model was built; they do not update. Use the Scenarios sheet to see any case live.")
    st["A2"].font = GREY
    row = 4

    def header(cols):
        nonlocal row
        for c, h in enumerate(cols, 1):
            cell = st.cell(row=row, column=c, value=h)
            cell.fill, cell.font = HEAD_FILL, HEAD
        row += 1

    def section(title):
        nonlocal row
        st.cell(row=row, column=1, value=title).font = SECTION
        row += 1

    def put(values, fmts):
        nonlocal row
        for c, (v, f) in enumerate(zip(values, fmts), 1):
            if c == 1 and isinstance(v, str) and v:
                v = v[0].upper() + v[1:]
            cell = st.cell(row=row, column=c, value=v)
            cell.font = BLACK
            if c == 1:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            if f:
                cell.number_format = f
            if v in ("PASS", "FAIL"):
                cell.font = Font(name=FONT, size=10, bold=True, color="008000" if v == "PASS" else "C00000")
        row += 1

    ccy = a["currency"]
    section(f"Scenarios (lender minimum DSCR {a['minimum_dscr']:.2f}x)")
    header(["Scenario", "Lowest DSCR", "Year", f"Lowest cash ({ccy})", "Year", f"Final-year profit ({ccy})", "Lender test", "Cash test"])
    for name, v in analysis["scenarios"].items():
        put([name.capitalize(), v["min_dscr"], v["min_dscr_year"], v["lowest_cash"], v["lowest_cash_year"],
             v["final_year_net_income"], "PASS" if v["passes_lender_test"] else "FAIL",
             "PASS" if v["cash_stays_above_minimum"] else "FAIL"], [None, MULT, INT, NUM, INT, NUM, None, None])
    row += 1
    section("Stress tests: one shock at a time")
    header(["Test", "Lowest DSCR", "Year", f"Lowest cash ({ccy})", "Year", f"Final-year profit ({ccy})", "Lender test", "Cash test"])
    for v in analysis["stress_tests"]:
        put([v["test"], v["min_dscr"], v["min_dscr_year"], v["lowest_cash"], v["lowest_cash_year"],
             v["final_year_net_income"], "PASS" if v["passes_lender_test"] else "FAIL",
             "PASS" if v["cash_stays_above_minimum"] else "FAIL"], [None, MULT, INT, NUM, INT, NUM, None, None])
    row += 1
    section("Breaking points: how big a shock the plan can take")
    header(["Shock", "Breaks at", "What fails"])
    for b in analysis["breaking_points"]:
        put([b["shock"].capitalize(), b["breaks_at"], b["fails"]], [None, None, None])
    row += 1
    ls = analysis["loan_structures"]
    section("Loan options that pass" + (f": {ls['test']}" if ls.get("test") else ""))
    if ls.get("requested_result"):
        rr = ls["requested_result"]
        put([f"As requested: base DSCR {rr['base_min_dscr']:.2f}x, downside {rr['downside_min_dscr']:.2f}x",
             "PASS" if rr["passes"] else "FAIL"], [None, None])
    if ls.get("options"):
        header(["Option", "Base DSCR", "Downside DSCR"])
        for o in ls["options"]:
            put([o["description"], o["base_min_dscr"], o["downside_min_dscr"]], [None, MULT, MULT])
    put([ls.get("note", "")], [None])

    # ------------------------------------------------------------------ Cover
    cover.sheet_view.showGridLines = False
    cover.column_dimensions["A"].width = 3
    cover.column_dimensions["B"].width = 100
    lines = [
        (a["company_name"], TITLE),
        (f"{n}-year financial model, {years[0]}–{years[-1]}, in {a['currency']}", BOLD),
        (f"Built by Investor-Fit Agent on {datetime.date.today().isoformat()} from assumptions provided by the company.", GREY),
        ("", None),
        ("How to use", SECTION),
        ("Change the blue cells on the Assumptions sheet. Everything else is a formula and updates automatically.", BLACK),
        ("Colours: blue = input you can change · black = calculation · green = link to another sheet.", BLACK),
        ("Yellow-shaded cells are the key assumptions a funder will question first.", BLACK),
        ("", None),
        ("Sheets", SECTION),
        ("Summary: headline numbers and the funding check (is the amount raised right, can the loan be repaid?)", BLACK),
        ("Scenarios: one switch moves the whole model between the base plan, a downside and an upside case", BLACK),
        ("Assumptions · Income · Debt · Balance · CashFlow · Ratios", BLACK),
        ("Stress tests: what happens under each shock, where the plan breaks, and loan terms that would pass", BLACK),
        ("", None),
        ("Conventions", SECTION),
        ("Annual periods. New loans are drawn at the start of the drawdown year; repayments at year end.", BLACK),
        ("Interest is charged on the balance outstanding during the year (no circular references).", BLACK),
        ("Depreciation is straight line, a full year in the year of purchase.", BLACK),
        ("Tax is charged on positive profit only; losses are not carried forward (a conservative simplification).", BLACK),
        ("No dividends. Working capital is driven by customer, stock and supplier days.", BLACK),
        (f"All figures in {a['currency']}. Loans or sales in another currency use the exchange-rate rows on the "
         "Assumptions sheet; loans are revalued each year and the change is shown as an exchange loss.", BLACK),
        ("", None),
        ("This model is a planning tool built from the company's own assumptions. It is not audited and is not "
         "financial or investment advice. Check every assumption before sharing it with a funder.", GREY),
    ]
    for i, (text, font) in enumerate(lines, 2):
        c = cover.cell(row=i, column=2, value=text)
        if font:
            c.font = font
        c.alignment = Alignment(wrap_text=True, vertical="top")

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.font and cell.font.name != FONT:
                    cell.font = Font(name=FONT, size=cell.font.size or 10, bold=cell.font.bold,
                                     color=cell.font.color, italic=cell.font.italic)
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    # No cached values are written; make Excel calculate everything when the file is opened.
    from openpyxl.workbook.properties import CalcProperties
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(path)
    return path

"""Evidence from a company's documents, and the data-quality checks run on it.

Claude reads the documents and records what they say in an evidence file (format below). This
module checks that evidence the way an analyst would, and returns everything that is missing,
inconsistent or implausible, with a question for the user for each.

Evidence format
---------------
{
  "company": "Example Ltd",
  "currency": "GHS",                       # currency the model will use
  "as_of": "2026-10-13",                   # today, for staleness and expiry checks
  "documents": [
    {"id": "afs2025", "name": "Audited accounts 2025.pdf", "type": "audited_accounts",
     "period_end": "2025-12-31", "currency": "GHS", "unit": 1,
     "audited": true, "signed": true, "audit_opinion": "unqualified", "expiry_date": null}
  ],
  "facts": [
    {"metric": "revenue", "period": "2025", "value": 14200000, "document": "afs2025", "page": 4}
  ],
  "bank": {                                # optional
    "account": "Main operating account", "currency": "GHS",
    "transactions": [{"date": "2025-01-03", "description": "...", "amount": 12000, "balance": 50000}],
    "months": [{"month": "2025-01", "deposits": 900000, "withdrawals": 850000, "closing_balance": 120000}],
    "unusual": [{"date": "...", "description": "...", "amount": ..., "why": "..."}]
  }
}

Document types: audited_accounts, management_accounts, tax_return, business_plan, financial_model,
bank_statement, loan_agreement, tax_clearance, registration, contract, invoice, payroll, other.
`unit` is the multiplier the document uses (1, 1000 for "in thousands", 1000000 for millions);
record values as printed and the checks scale them. For bank statements, record individual
transactions when there are 300 or fewer, otherwise monthly totals plus the unusual items.

Metrics: revenue, cogs, gross_profit, operating_expenses, ebitda, depreciation, ebit, interest,
profit_before_tax, tax, net_income, cash, receivables, inventory, other_current_assets, ppe_net,
other_assets, total_assets, payables, other_current_liabilities, total_debt, other_liabilities,
total_liabilities, equity, cfo, cfi, cff, net_change_in_cash, opening_cash, capex, dividends,
new_equity, employees, volume_sold, average_price, revenue_growth (plans only), gross_margin (plans only).
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from typing import Any

PRIORITY = {"audited_accounts": 0, "tax_return": 1, "management_accounts": 2, "bank_statement": 3,
            "financial_model": 4, "business_plan": 5, "other": 6}
FLOW_METRICS = {"revenue", "cogs", "gross_profit", "operating_expenses", "ebitda", "depreciation", "ebit",
                "interest", "profit_before_tax", "tax", "net_income", "cfo", "cfi", "cff", "net_change_in_cash",
                "capex", "dividends", "new_equity"}
CORE_PL = ["revenue", "cogs", "operating_expenses", "net_income"]
CORE_BS = ["cash", "receivables", "inventory", "ppe_net", "payables", "total_debt", "equity", "total_assets"]
TOLERANCE = 0.02  # 2% difference between documents is treated as a mismatch
SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3}
BOUNCE_WORDS = ("return", "reversal", "reversed", "unpaid", "bounced", "insufficient", "dishonoured", "dishonored")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _date(x):
    try:
        return dt.date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None


class Evidence:
    """Indexes facts by metric and period, scaled to full units, with the best source first."""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.currency = (data.get("currency") or "").upper()
        self.as_of = _date(data.get("as_of")) or dt.date.today()
        self.docs = {d["id"]: d for d in data.get("documents") or []}
        self.by: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for f in data.get("facts") or []:
            v = _num(f.get("value"))
            if v is None or not f.get("metric") or not f.get("period"):
                continue
            doc = self.docs.get(f.get("document"), {})
            unit = _num(doc.get("unit")) or 1.0
            self.by[(f["metric"], str(f["period"]))].append({
                **f, "value": v * unit, "raw": v, "doc_type": doc.get("type", "other"),
                "doc_name": doc.get("name", f.get("document", "?")),
                "currency": (f.get("currency") or doc.get("currency") or self.currency or "").upper(),
            })
        for k in self.by:
            self.by[k].sort(key=lambda x: PRIORITY.get(x["doc_type"], 6))

    def periods(self, kinds=("audited_accounts", "management_accounts", "tax_return")) -> list[str]:
        ps = {p for (m, p), fs in self.by.items() if any(f["doc_type"] in kinds for f in fs)}
        return sorted(ps)

    def get(self, metric: str, period: str) -> float | None:
        fs = self.by.get((metric, period))
        return fs[0]["value"] if fs else None

    def source(self, metric: str, period: str) -> str | None:
        fs = self.by.get((metric, period))
        if not fs:
            return None
        f = fs[0]
        return f"{f['doc_name']}" + (f", p.{f['page']}" if f.get("page") else "")


def _item(sev, category, what, where, detail, ask):
    return {"severity": sev, "category": category, "issue": what, "where": where, "detail": detail,
            "question_for_user": ask}


def check(data: dict[str, Any]) -> dict[str, Any]:
    ev = Evidence(data)
    items: list[dict] = []
    add = lambda *a: items.append(_item(*a))  # noqa: E731
    hist = ev.periods()
    doc_types = {d.get("type") for d in ev.docs.values()}

    # ------------------------------------------------------------ missing
    if not hist:
        add("critical", "missing", "No historical financial statements found", "All documents",
            "There are no figures from audited accounts, management accounts or tax returns.",
            "Can you share the last 2–3 years of financial statements (audited if available)?")
    elif len(hist) < 2:
        add("high", "missing", f"Only one year of history ({hist[0]})", "Financial statements",
            "Growth, margins and payment patterns cannot be judged from a single year.",
            "Do you have the previous year's accounts, even unaudited or management accounts?")
    for p in hist:
        miss_pl = [m for m in CORE_PL if ev.get(m, p) is None and not (m == "cogs" and ev.get("gross_profit", p) is not None)]
        miss_bs = [m for m in CORE_BS if ev.get(m, p) is None]
        if miss_pl:
            add("high" if "revenue" in miss_pl else "medium", "missing", f"Income statement items missing for {p}",
                p, ", ".join(miss_pl).replace("_", " "),
                f"Where can I find {', '.join(miss_pl).replace('_', ' ')} for {p}? A detailed income statement or trial balance would do.")
        if len(miss_bs) == len(CORE_BS):
            add("high", "missing", f"No balance sheet for {p}", p,
                "Opening balances, payment days and debt cannot be set without it.",
                f"Can you share the {p} balance sheet?")
        elif miss_bs:
            add("medium", "missing", f"Balance sheet items missing for {p}", p, ", ".join(miss_bs).replace("_", " "),
                f"Are {', '.join(miss_bs).replace('_', ' ')} for {p} shown anywhere, e.g. in the notes?")
    if hist:
        latest = hist[-1]
        end = _date(f"{latest}-12-31") if len(latest) == 4 else _date(latest)
        if end and (ev.as_of - end).days > 548:
            add("high", "missing", f"Latest figures are old (period {latest})", "Financial statements",
                f"The most recent period ended {end.isoformat()}, more than 18 months ago.",
                "Do you have management accounts for the current or last financial year?")
        last_debt = ev.get("total_debt", latest)
        if last_debt and last_debt > 0 and "loan_agreement" not in doc_types:
            add("medium", "missing", "Loans shown but no loan agreement provided", latest,
                f"Debt of {last_debt:,.0f} {ev.currency} with no agreement to confirm rate, tenor and security.",
                "Can you share the loan agreements, or tell me the rate, remaining term and lender?")
    for t, label in (("bank_statement", "bank statements"), ("tax_clearance", "a tax clearance certificate"),
                     ("registration", "registration documents")):
        if t not in doc_types and not (t == "bank_statement" and data.get("bank")):
            add("low", "missing", f"No {label}", "Documents",
                f"Most funders ask for {label}.", f"Can you share {label}?")

    # ------------------------------------------------------------ arithmetic within the best source
    def close(a, b, tol=TOLERANCE, floor=1.0):
        return abs(a - b) <= max(floor, tol * max(abs(a), abs(b)))

    for p in hist:
        g = lambda m: ev.get(m, p)  # noqa: E731
        rev, cogs, gp = g("revenue"), g("cogs"), g("gross_profit")
        if None not in (rev, cogs, gp) and not close(rev - cogs, gp):
            add("high", "inconsistent", f"Gross profit does not add up in {p}", ev.source("gross_profit", p),
                f"Revenue {rev:,.0f} − direct costs {cogs:,.0f} = {rev - cogs:,.0f}, but gross profit is {gp:,.0f}.",
                "Which figure is right? Are some direct costs shown elsewhere?")
        pbt, tax, ni = g("profit_before_tax"), g("tax"), g("net_income")
        if None not in (pbt, tax, ni) and not close(pbt - tax, ni):
            add("medium", "inconsistent", f"Net profit does not equal profit before tax minus tax in {p}",
                ev.source("net_income", p), f"{pbt:,.0f} − {tax:,.0f} ≠ {ni:,.0f}.",
                "Is there an exceptional item or a typo?")
        ta, tl, eq = g("total_assets"), g("total_liabilities"), g("equity")
        if ta is not None and eq is not None:
            liab = tl if tl is not None else sum(x for x in (g("payables"), g("total_debt"),
                                                               g("other_current_liabilities"), g("other_liabilities")) if x)
            if (tl is not None or liab) and not close(ta, liab + eq):
                add("critical", "inconsistent", f"Balance sheet does not balance in {p}", ev.source("total_assets", p),
                    f"Assets {ta:,.0f} vs liabilities + equity {liab + eq:,.0f} (difference {ta - liab - eq:,.0f}).",
                    "Is a liability or equity line missing from what I read, or is the statement wrong?")
        parts = [g(m) for m in ("cash", "receivables", "inventory", "ppe_net", "other_current_assets", "other_assets")]
        if ta is not None and all(x is not None for x in parts[:4]) and sum(x or 0 for x in parts) > ta * (1 + TOLERANCE):
            add("high", "inconsistent", f"Asset lines add up to more than total assets in {p}", ev.source("total_assets", p),
                f"Lines sum to {sum(x or 0 for x in parts):,.0f}; total assets {ta:,.0f}.",
                "Have I misread a line, or are the accounts wrong?")
        oc, nc, cc = g("opening_cash"), g("net_change_in_cash"), g("cash")
        if None not in (oc, nc, cc) and not close(oc + nc, cc):
            add("high", "inconsistent", f"Cash flow does not reconcile to closing cash in {p}", ev.source("cash", p),
                f"Opening {oc:,.0f} + change {nc:,.0f} = {oc + nc:,.0f}, but closing cash is {cc:,.0f}.",
                "Which figure is right?")

    # ------------------------------------------------------------ roll-forward between years
    for a_, b_ in zip(hist, hist[1:]):
        c_prev, oc = ev.get("cash", a_), ev.get("opening_cash", b_)
        if c_prev is not None and oc is not None and not close(c_prev, oc):
            add("medium", "inconsistent", f"Closing cash {a_} ≠ opening cash {b_}", f"{a_}/{b_}",
                f"{c_prev:,.0f} vs {oc:,.0f}.", "Was there a restatement, or is one figure wrong?")
        e0, e1, ni = ev.get("equity", a_), ev.get("equity", b_), ev.get("net_income", b_)
        if None not in (e0, e1, ni):
            expected = e0 + ni - (ev.get("dividends", b_) or 0) + (ev.get("new_equity", b_) or 0)
            if not close(expected, e1, tol=0.05, floor=max(1.0, 0.01 * abs(e1))):
                add("medium", "inconsistent", f"Equity movement in {b_} is not explained", f"{a_}→{b_}",
                    f"Expected {expected:,.0f} (opening equity + profit − dividends + new shares), found {e1:,.0f}.",
                    "Were there dividends, new shares, revaluations or prior-year adjustments?")

    # ------------------------------------------------------------ the same figure in different documents
    for (metric, period), fs in ev.by.items():
        if len(fs) < 2 or metric in ("revenue_growth", "gross_margin"):
            continue
        best = fs[0]
        for other in fs[1:]:
            if other["currency"] != best["currency"]:
                continue
            if not close(best["value"], other["value"]):
                diff = (other["value"] - best["value"]) / best["value"] if best["value"] else 0
                sev = "high" if metric in ("revenue", "net_income", "total_debt", "cash") or abs(diff) > 0.1 else "medium"
                add(sev, "inconsistent", f"{metric.replace('_', ' ').capitalize()} {period} differs between documents",
                    f"{best['doc_name']} vs {other['doc_name']}",
                    f"{best['value']:,.0f} in {best['doc_name']}, {other['value']:,.0f} in {other['doc_name']} ({diff:+.0%}).",
                    f"Which is right? I will use {best['doc_name']} unless you say otherwise.")

    # ------------------------------------------------------------ units and currency
    for p in hist:
        rev = ev.get("revenue", p)
        for m in ("cogs", "operating_expenses", "receivables", "inventory", "payables"):
            v = ev.get(m, p)
            if rev and v and (v / rev > 50 or v / rev < 0.0005):
                add("high", "implausible", f"{m.replace('_', ' ').capitalize()} {p} looks like a different unit",
                    ev.source(m, p), f"{v:,.0f} against revenue of {rev:,.0f} ({v / rev:.4g}×).",
                    "Is one of these in thousands or millions? Check the unit line at the top of the statement.")
    seen_ccy = {f["currency"] for fs in ev.by.values() for f in fs if f["currency"]}
    if ev.currency and seen_ccy - {ev.currency}:
        add("medium", "inconsistent", "Figures in more than one currency", "Documents",
            f"Found {', '.join(sorted(seen_ccy))}; the model uses {ev.currency}.",
            "Which exchange rate should I use to convert them, and for which dates?")

    # ------------------------------------------------------------ plausibility over time
    for i, p in enumerate(hist):
        g = lambda m, q=p: ev.get(m, q)  # noqa: E731
        rev = g("revenue")
        if not rev:
            continue
        cogs = g("cogs") if g("cogs") is not None else (rev - g("gross_profit") if g("gross_profit") is not None else None)
        if cogs is not None:
            gm = 1 - cogs / rev
            if gm < 0 or gm > 0.9:
                add("medium", "implausible", f"Gross margin of {gm:.0%} in {p}", ev.source("revenue", p),
                    "Unusual for most businesses.", "Is that right? What drives it?")
        if g("net_income") is not None and g("net_income") / rev > 0.4:
            add("medium", "implausible", f"Net margin of {g('net_income') / rev:.0%} in {p}", ev.source("net_income", p),
                "Very high for an SME; funders will question it.", "Are there one-off gains in this year?")
        for m, base, name, lim in (("receivables", rev, "Customers take", 180), ("inventory", cogs, "Stock covers", 365),
                                   ("payables", cogs, "Suppliers are paid after", 365)):
            v = g(m)
            if v is not None and base:
                days = v / base * 365
                if days > lim:
                    add("medium", "implausible", f"{name} {days:.0f} days in {p}", ev.source(m, p),
                        f"{m.capitalize()} {v:,.0f} against {'revenue' if m == 'receivables' else 'direct costs'} {base:,.0f}.",
                        "Are some of these old or doubtful balances? Should any be written off?")
        for m in ("cash", "receivables", "inventory", "ppe_net", "total_assets"):
            v = g(m)
            if v is not None and v < 0:
                add("high", "implausible", f"Negative {m.replace('_', ' ')} in {p}", ev.source(m, p), f"{v:,.0f}.",
                    "Is this an overdraft shown as negative cash, or a reading error?")
        debt, intr = g("total_debt"), g("interest")
        if debt and intr is not None and debt > 0:
            rate = intr / debt
            if rate > 0.6 or (rate < 0.01 and intr > 0):
                add("low", "implausible", f"Implied interest rate of {rate:.0%} in {p}", ev.source("interest", p),
                    f"Interest {intr:,.0f} on debt of {debt:,.0f}.", "What are the actual loan rates?")
        if i > 0:
            prev_rev = ev.get("revenue", hist[i - 1])
            if prev_rev:
                ch = rev / prev_rev - 1
                if ch > 1 or ch < -0.5:
                    add("medium", "implausible", f"Revenue changed {ch:+.0%} from {hist[i - 1]} to {p}", f"{hist[i - 1]}→{p}",
                        f"{prev_rev:,.0f} → {rev:,.0f}.", "What explains such a large change?")
            pc, pr = ev.get("cogs", hist[i - 1]), prev_rev
            if cogs is not None and pc is not None and pr:
                swing = (1 - cogs / rev) - (1 - pc / pr)
                if abs(swing) > 0.15:
                    add("medium", "implausible", f"Gross margin moved {swing * 100:+.0f} points in {p}", f"{hist[i - 1]}→{p}",
                        "A large swing in one year.", "What changed: prices, product mix, or how costs are classified?")

    # ------------------------------------------------------------ plans against history
    rev_hist = [(p, ev.get("revenue", p)) for p in hist if ev.get("revenue", p)]
    if len(rev_hist) >= 2:
        n = len(rev_hist) - 1
        hg = (rev_hist[-1][1] / rev_hist[0][1]) ** (1 / n) - 1 if rev_hist[0][1] > 0 else None
        for (metric, period), fs in ev.by.items():
            if metric != "revenue_growth":
                continue
            for f in fs:
                if hg is not None and f["value"] > max(0.15, 2 * hg):
                    add("high", "implausible", f"Plan assumes {f['value']:.0%} growth; history shows {hg:.0%} a year",
                        f["doc_name"], f"Period {period}.", "What will make growth so much faster than before?")
        plan_rev = [(p, fs) for (m, p), fs in ev.by.items() if m == "revenue" and p > rev_hist[-1][0]
                    and any(f["doc_type"] in ("business_plan", "financial_model") for f in fs)]
        for p, fs in sorted(plan_rev)[:1]:
            years_ahead = int(p[:4]) - int(rev_hist[-1][0][:4]) if p[:4].isdigit() and rev_hist[-1][0][:4].isdigit() else 1
            if years_ahead > 0 and rev_hist[-1][1] > 0:
                pg = (fs[0]["value"] / rev_hist[-1][1]) ** (1 / years_ahead) - 1
                if hg is not None and pg > max(0.15, 2 * hg):
                    add("high", "implausible", f"Plan revenue for {p} implies {pg:.0%} growth a year; history shows {hg:.0%}",
                        fs[0]["doc_name"], f"{rev_hist[-1][1]:,.0f} in {rev_hist[-1][0]} → {fs[0]['value']:,.0f} in {p}.",
                        "What drives this: new capacity, contracts, prices? Should I model a slower base case?")

    # ------------------------------------------------------------ documents themselves
    for d in ev.docs.values():
        name = d.get("name", d["id"])
        exp = _date(d.get("expiry_date"))
        if exp and exp < ev.as_of:
            add("high", "document", f"{name} has expired", name, f"Expired on {exp.isoformat()}.",
                "Can you get a current one? Funders check validity dates.")
        elif exp and (exp - ev.as_of).days < 60:
            add("low", "document", f"{name} expires soon", name, f"Expires on {exp.isoformat()}.",
                "Plan to renew it before applying.")
        if d.get("type") == "audited_accounts":
            op = (d.get("audit_opinion") or "").lower()
            if op and op not in ("unqualified", "clean", "unmodified"):
                add("high", "document", f"Audit opinion is '{op}'", name,
                    "A modified opinion means the auditor could not confirm parts of the accounts.",
                    "What was the auditor's reason, and has it been resolved?")
            if d.get("audited") is False:
                add("medium", "document", f"{name} is labelled audited but is not", name, "No auditor's report found.",
                    "Are these draft accounts? Is an audited version available?")
            if d.get("signed") is False:
                add("medium", "document", f"{name} is not signed", name, "Unsigned accounts are treated as drafts.",
                    "Do you have the signed version?")

    # ------------------------------------------------------------ bank statements
    bank = bank_summary(data.get("bank"))
    if bank:
        for p in hist:
            rev = ev.get("revenue", p)
            dep = bank["deposits_by_year"].get(p[:4])
            months = bank["months_by_year"].get(p[:4], 0)
            if rev and dep is not None and months >= 10:
                ratio = dep / rev
                if ratio < 0.6:
                    add("high", "inconsistent", f"Bank deposits are only {ratio:.0%} of reported revenue in {p}",
                        data["bank"].get("account", "Bank statement"),
                        f"Deposits {dep:,.0f} vs revenue {rev:,.0f}.",
                        "Are some sales paid in cash, into another account, or by mobile money? Funders will ask.")
                elif ratio > 1.5:
                    add("medium", "inconsistent", f"Bank deposits are {ratio:.1f}× reported revenue in {p}",
                        data["bank"].get("account", "Bank statement"),
                        f"Deposits {dep:,.0f} vs revenue {rev:,.0f}.",
                        "Do deposits include loans, transfers between accounts or owner money? Or is revenue understated?")
        for x in bank["flags"]:
            add(x["severity"], "bank", x["issue"], data["bank"].get("account", "Bank statement"), x["detail"], x["ask"])

    items.sort(key=lambda x: (SEV[x["severity"]], x["category"]))
    counts = {c: sum(1 for x in items if x["category"] == c) for c in ("missing", "inconsistent", "implausible", "document", "bank")}
    sev = {s: sum(1 for x in items if x["severity"] == s) for s in SEV}
    verdict = ("Not enough to build a model yet: resolve the critical points first." if sev["critical"]
               else "A model can be built, but the high-priority points should be resolved first." if sev["high"]
               else "Good enough to build a model; tidy up the remaining points." if items
               else "No issues found.")
    return {
        "verdict": verdict,
        "counts_by_category": counts,
        "counts_by_severity": sev,
        "history_periods": hist,
        "documents_read": [d.get("name", d["id"]) for d in ev.docs.values()],
        "bank_summary": {k: v for k, v in (bank or {}).items() if k != "flags"} or None,
        "items": items,
        "questions": [f"{x['issue']}: {x['question_for_user']}" for x in items if x["severity"] in ("critical", "high")],
    }


def bank_summary(bank: dict[str, Any] | None) -> dict[str, Any] | None:
    """Monthly totals from transactions (or as recorded), and unusual items."""
    if not bank:
        return None
    flags: list[dict] = []
    months: dict[str, dict[str, float]] = {}
    txs = bank.get("transactions") or []
    for t in txs:
        d, amt = _date(t.get("date")), _num(t.get("amount"))
        if not d or amt is None:
            continue
        m = months.setdefault(d.strftime("%Y-%m"), {"deposits": 0.0, "withdrawals": 0.0, "closing_balance": None})
        if amt >= 0:
            m["deposits"] += amt
        else:
            m["withdrawals"] += -amt
        if _num(t.get("balance")) is not None:
            m["closing_balance"] = _num(t.get("balance"))
    for m in bank.get("months") or []:
        months.setdefault(m["month"], {"deposits": _num(m.get("deposits")) or 0.0,
                                       "withdrawals": _num(m.get("withdrawals")) or 0.0,
                                       "closing_balance": _num(m.get("closing_balance"))})
    if not months:
        return None
    keys = sorted(months)
    dep_values = [months[k]["deposits"] for k in keys]
    med = statistics.median(dep_values) if dep_values else 0
    for k in keys:
        if months[k]["deposits"] == 0:
            flags.append({"severity": "medium", "issue": f"No deposits in {k}", "detail": "A month with no money coming in.",
                          "ask": f"Was the business closed in {k}, or are sales banked elsewhere?"})
        elif med and months[k]["deposits"] > 3 * med:
            flags.append({"severity": "low", "issue": f"Deposits in {k} are {months[k]['deposits'] / med:.1f}× a normal month",
                          "detail": f"{months[k]['deposits']:,.0f} vs a typical {med:,.0f}.",
                          "ask": f"What came in during {k}: a loan, an owner injection, a large order?"})
        cb = months[k]["closing_balance"]
        if cb is not None and cb < 0:
            flags.append({"severity": "medium", "issue": f"Account overdrawn at the end of {k}", "detail": f"Balance {cb:,.0f}.",
                          "ask": "Is there an agreed overdraft? What limit?"})
    bounced = [t for t in txs if any(w in (t.get("description") or "").lower() for w in BOUNCE_WORDS)]
    if bounced:
        flags.append({"severity": "high", "issue": f"{len(bounced)} returned or unpaid item(s)",
                      "detail": "; ".join(f"{t.get('date')} {t.get('description')} {t.get('amount')}" for t in bounced[:5]),
                      "ask": "What happened with these? Lenders read returned payments as a cash-flow warning."})
    if txs:
        deps = sorted((t for t in txs if (_num(t.get("amount")) or 0) > 0), key=lambda t: -_num(t["amount"]))
        total = sum(_num(t["amount"]) for t in deps) or 1
        if deps and _num(deps[0]["amount"]) / total > 0.25:
            t = deps[0]
            flags.append({"severity": "low", "issue": "One deposit is over a quarter of all deposits",
                          "detail": f"{t.get('date')} {t.get('description')} {_num(t['amount']):,.0f}.",
                          "ask": "What was this payment? If it is a loan or owner money it is not sales."})
    for u in bank.get("unusual") or []:
        flags.append({"severity": "low", "issue": f"Unusual item: {u.get('description', '')}"[:80],
                      "detail": f"{u.get('date', '')} {u.get('amount', '')}: {u.get('why', '')}",
                      "ask": "Can you explain this transaction?"})
    by_year: dict[str, float] = defaultdict(float)
    count_year: dict[str, int] = defaultdict(int)
    for k in keys:
        by_year[k[:4]] += months[k]["deposits"]
        count_year[k[:4]] += 1
    return {
        "mode": "transactions" if txs else "monthly totals",
        "months_covered": len(keys), "first_month": keys[0], "last_month": keys[-1],
        "deposits_by_year": dict(by_year), "months_by_year": dict(count_year),
        "monthly": [{"month": k, **months[k]} for k in keys],
        "flags": flags,
    }

# Evidence file (`evidence.json`)

What Claude records after reading a company's documents. `check_documents.py` checks it and
`build_from_documents.py` builds the model from it. A full example is in
`examples/evidence_example.json`.

```json
{
  "company": "Example Ltd",
  "currency": "GHS",
  "as_of": "2026-10-13",
  "documents": [
    {"id": "afs2025", "name": "Audited accounts 2025.pdf", "type": "audited_accounts",
     "period_end": "2025-12-31", "currency": "GHS", "unit": 1000,
     "audited": true, "signed": true, "audit_opinion": "unqualified", "expiry_date": null}
  ],
  "facts": [
    {"metric": "revenue", "period": "2025", "value": 14200, "document": "afs2025", "page": 5}
  ],
  "bank": {
    "account": "Main operating account", "currency": "GHS",
    "transactions": [{"date": "2025-01-03", "description": "Customer payment", "amount": 12000, "balance": 50000}],
    "months": [{"month": "2025-01", "deposits": 900000, "withdrawals": 850000, "closing_balance": 120000}],
    "unusual": [{"date": "2025-09-14", "description": "Transfer from director", "amount": 2000000, "why": "one-off, not sales"}]
  }
}
```

## Documents

`type`: audited_accounts, management_accounts, tax_return, business_plan, financial_model,
bank_statement, loan_agreement, tax_clearance, registration, contract, invoice, payroll, other.

- `unit`: the multiplier the document uses (1, 1000 for "in thousands", 1000000 for "in millions").
  Record values exactly as printed; the checks scale them.
- `audited`, `signed`, `audit_opinion` (unqualified, qualified, adverse, disclaimer) for accounts.
- `expiry_date` for certificates (tax clearance, licences).

When sources disagree, audited accounts are preferred, then tax returns, management accounts,
bank statements, financial models and business plans.

## Facts

One entry per figure per document. `period` is the financial year ("2025") or a date. Record the
same figure from every document that states it.

Metrics: revenue, cogs, gross_profit, operating_expenses, ebitda, depreciation, ebit, interest,
profit_before_tax, tax, net_income, cash, receivables, inventory, other_current_assets, ppe_net,
other_assets, total_assets, payables, other_current_liabilities, total_debt, other_liabilities,
total_liabilities, equity, cfo, cfi, cff, net_change_in_cash, opening_cash, capex, dividends,
new_equity, employees, volume_sold, average_price. Plans may also give revenue_growth and
gross_margin (as fractions) and future-year revenue.

## Bank statements

300 transactions or fewer: record each in `transactions` (positive = money in, negative = money
out). More than 300: record `months` (totals) and the `unusual` items: large or one-off amounts,
returned or unpaid items, transfers to or from owners, months with no income.

## What the checks look for

- **Missing:** statements, years, balance-sheet items, recent figures, loan agreements, bank
  statements, tax clearance, registration.
- **Inconsistent:** totals that do not add up, a balance sheet that does not balance, cash flow
  not reconciling, cash and equity not rolling forward between years, the same figure differing
  between documents, figures in mixed currencies, bank deposits far from reported revenue.
- **Implausible:** margins, growth and payment days outside believable ranges, negative
  balances, numbers that look like a different unit, plans far above the track record.
- **Documents:** expired, unsigned, or a modified audit opinion.
- **Bank:** months with no deposits, overdrafts, returned or unpaid items, unusual large deposits.

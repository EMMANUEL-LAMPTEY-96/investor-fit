# Financial model assumptions

All money in one currency. Rates are fractions: `0.25` means 25%. Anything marked *per year* can be
one number (same every year) or a list with one value per year.

| Field | Meaning | Ask the user |
|---|---|---|
| `company_name`, `currency`, `first_year`, `years` | Basics. `first_year` is the first projected year; `years` 3–10 (default 5) | |
| `revenue_streams[]` | `name`, `unit`, `volume` (year 1), `volume_growth` (per year), `price` (year 1), `price_growth` (per year) | What do you sell, how many units, at what price, growing how fast? |
| `cogs_pct_revenue` | Direct costs as a share of revenue (per year) | Raw materials and direct labour per 100 of sales? |
| `variable_opex_pct_revenue` | Other costs that move with sales (per year) | Commissions, transport, packaging? |
| `fixed_costs[]` | `name`, `amount` (year 1), `growth` (per year) | Salaries, rent, utilities, admin |
| `capex[]` | `name`, `amounts` (list, one per year) | Equipment or buildings to buy, and when |
| `depreciation_years` | Life of new assets | How long will the equipment last? |
| `existing_ppe_remaining_years` | Remaining life of existing assets | |
| `receivable_days`, `inventory_days`, `payable_days` | Working capital | Days customers take to pay, days of stock, days you take to pay suppliers |
| `tax_rate` | Corporate tax rate | |
| `opening_balance` | `cash`, `receivables`, `inventory`, `ppe_net`, `payables` at the start of year 1 | From the latest balance sheet |
| `existing_debt` | `balance`, `interest_rate`, `remaining_years` | Current loans |
| `new_debt` | `amount`, `interest_rate`, `tenor_years`, `grace_years`, `drawdown_year` | The loan being sought |
| `new_equity` | `amount`, `year` | Equity being sought |
| `use_of_funds[]` | `item`, `amount` | What exactly the money pays for |
| `currency` | The model's currency, normally local (e.g. GHS) | |
| `revenue_streams[].currency`, `new_debt.currency`, `existing_debt.currency` | Set when that item is in a foreign currency (e.g. USD) | Is the loan or any sale priced in dollars or euros? |
| `fx` | `rate`: local per 1 foreign unit today; `depreciation`: expected yearly fall (per year) | Current rate; use the currency's recent trend for the fall |
| `new_debt.local_currency_rate` | Interest rate if the same loan were taken in local currency (lets the agent test that option) | Ask local banks or use the central bank's lending-rate data |
| `scenarios` | Shocks for `downside` and `upside`: price, volume, fixed_costs (fractions), cogs_pts, interest_pts (added points), receivable_days, fx_devaluation (one-off fall in year 1) | What does a bad year look like in this sector? |
| `minimum_dscr` | Lender's debt service cover test (default 1.25) | From the funder's terms if known |
| `minimum_cash` | Cash buffer to keep (default 0) | |

## Example

```json
{
  "company_name": "Example Cashew Processing Ltd",
  "currency": "USD",
  "first_year": 2027,
  "years": 5,
  "revenue_streams": [
    {"name": "Cashew kernels (export)", "unit": "tonnes", "volume": 400, "volume_growth": 0.20, "price": 3500, "price_growth": 0.03}
  ],
  "cogs_pct_revenue": 0.62,
  "variable_opex_pct_revenue": 0.05,
  "fixed_costs": [{"name": "Salaries", "amount": 180000, "growth": 0.08}],
  "capex": [{"name": "Processing line upgrade", "amounts": [250000, 0, 0, 100000, 0]}],
  "depreciation_years": 10,
  "receivable_days": 45, "inventory_days": 60, "payable_days": 30,
  "tax_rate": 0.25,
  "opening_balance": {"cash": 50000, "receivables": 120000, "inventory": 150000, "ppe_net": 400000, "payables": 80000},
  "existing_debt": {"balance": 100000, "interest_rate": 0.18, "remaining_years": 2},
  "new_debt": {"amount": 500000, "interest_rate": 0.14, "tenor_years": 5, "grace_years": 1, "drawdown_year": 1},
  "use_of_funds": [{"item": "Processing line upgrade", "amount": 250000}, {"item": "Raw cashew stock", "amount": 250000}],
  "minimum_dscr": 1.25,
  "minimum_cash": 25000
}
```

## Example with a foreign-currency loan

`build_model.py --example-fx example.json` writes the same business modelled in
Ghana cedis, with a USD 500,000 loan and kernel exports priced in USD (`fx.rate` 12, falling 8% a year).

## Model conventions

Annual periods. New loans are drawn at the start of the drawdown year and repaid at year end, in
equal instalments after the grace period. Interest is charged on the balance outstanding during the
year (no circular references). Straight-line depreciation, full year in the year of purchase. Tax on
positive profit only, no loss carry-forward. No dividends. Foreign-currency items use each year's
exchange rate; a loan drawn at the start of a year converts at the opening rate, and loans are
revalued each year (the change is an exchange loss, not cash). Scenario shocks apply to every year.

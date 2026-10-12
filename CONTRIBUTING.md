# Contributing

The most useful contribution is **funder data**: a new funder, a correction, or a confirmation that a
record is still accurate.

## Propose a funder or a correction

Open an issue titled `Funder: <name>` with:

1. The funder's name and the **official page** where its criteria are published.
2. What you checked: countries, sectors, stages, instruments, ticket size, eligibility requirements.
3. For corrections: which field is wrong and the page that shows the right value.

Or edit `data/funders.json` directly and open a pull request. The tests check that your record uses
the allowed values.

## Rules for a record

- **Only facts you read on a source page.** If the funder does not publish a ticket size or a
  requirement, leave it `null`. Never estimate.
- Every record needs at least one `source_urls` entry, preferably the funder's own site.
- Set `confidence`:
  - `high`: every fact read on the funder's official pages
  - `medium`: some facts from news, databases or third-party guides
  - `low`: anything weaker (avoid)
- Set `last_checked` to the date you read the sources.
- New records start as `"verification_status": "needs_human_review"`. A maintainer sets
  `"verified"` after checking the sources.
- Convert other currencies to USD at the rate on the day you checked, and say so in `notes`.

## Allowed values

| Field | Values |
|---|---|
| `type` | dfi, export_credit, impact_fund, impact_lender, vc, pe, bank |
| `geographies` | ISO alpha-2 country codes (GH, NG, CI...) or west_africa, africa, emerging_markets, global |
| `sectors` | agribusiness, agri_processing, agri_fintech, fintech, manufacturing, trade_export, renewable_energy, healthcare, education, infrastructure, financial_institutions, consumer, technology, any |
| `stages` | startup, early, growth, mature (empty list = not stated) |
| `instruments` | equity, quasi_equity, debt, working_capital, trade_finance, guarantee, grant, on_lending |

`on_lending` means the money reaches companies through partner banks or funds; set
`direct_application` to `false` in that case.

## Code changes

```bash
pip install -r requirements.txt pytest
pytest -q
```

Scoring changes need a test, and should keep the benchmark cases in `tests/benchmark.json` passing
(or explain in the pull request why an expectation should change).

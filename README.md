# Investor-Fit Agent

**A capital-raising advisor that lives inside Claude.** It finds the funders that fit a company,
checks the company's documents against each funder's requirements, and builds or reviews the
financial model funders will test.

Two parts, both free:

| Part | What it does | Install |
|---|---|---|
| **Connector** (MCP server) | Funder database and matching, readiness gaps, scoring of any funder worldwide, projections and funding checks | Paste one URL into Claude |
| **Skill** | The advisor workflow, plus scripts that build an editable Excel model and review a company's own model | Upload one zip into Claude |

## What a founder can do

> "Here are our 2024 and 2025 accounts, our registration certificate and our business plan. We
> process cashew in Ghana and need $500K of working capital. Who should we approach, are we ready,
> and does our plan hold up?"

1. **Find funders.** Claude reads the documents and builds a fact sheet in which every figure
   cites its source. The agent ranks funders from the verified database, and Claude searches the
   web for others and scores them the same way, labelled as unverified.
2. **Check readiness.** For each funder, it shows which requirements are met, which are missing,
   and what would unlock each gap: audited accounts, years trading, export history, revenue,
   impact evidence. It also lists which documents the funder asks for and which ones the
   company has.
3. **Build a financial model** if the company doesn't have one. Claude collects the assumptions
   and the skill produces a 5-year, three-statement Excel model with live formulas: assumptions,
   income statement, balance sheet, cash flow, debt schedule, ratios and a funding check.
4. **Review an existing model.** The review covers two things:
   - **Mechanics:** formula errors, numbers typed over formulas, formulas that break their row's
     pattern, assumptions hidden inside formulas, links to other files, hidden sheets, and a
     balance sheet that doesn't balance.
   - **Fit with the ask:** whether growth and margins are believable, whether the business can
     service the loan (DSCR), whether the amount asked matches the cash the plan actually needs,
     and whether the use of funds adds up.

Example from the included sample company: it plans to raise **$500K**, but its own cash flow
shows a peak need of about **$182K**. Debt service cover also drops to **1.04x** in 2028, below
the usual 1.25x lender test. The agent flags both and suggests fixes: a longer grace period, a
smaller loan, or part equity.

## Why it is built this way

- **No invented funders or numbers.** Funder facts come from a source-linked database or a page
  Claude has just read. Company figures come from the user or their documents, with citations.
- **Calculations are code, not guesses.** Matching, scoring, projections and checks are plain,
  tested Python. Claude explains the results; it doesn't make them up.
- **Spreadsheets that hold up.** Every number in the built model is a live formula driven by the
  blue input cells. The tests recalculate each workbook in LibreOffice and check it against the
  Python engine to the cent.
- **Private by design.** Documents stay in the user's own Claude. The server receives only the
  facts it needs and stores nothing.
- **Free to run.** Each user's Claude does the reading and writing; the server only does
  arithmetic.

## Install

**Connector.** In Claude, open **Customize → Connectors → Add custom connector**. Name it
`Investor-Fit Agent` and use the URL `https://<your-deployment>/mcp`. Works on claude.ai and
Claude Desktop, including the Free plan, which allows one custom connector.
For Claude Code: `claude mcp add --transport http investor-fit https://<your-deployment>/mcp`

**Skill.** Download `dist/investor-fit-advisor.zip`. In Claude, open
**Customize → Skills → + → Upload a skill** and choose the zip. The skill needs
**Code execution** switched on under Settings → Capabilities.

## Connector tools

| Tool | Purpose |
|---|---|
| `match_company` | Rank the database's funders for a company: score breakdown, readiness, gaps, how to apply |
| `check_readiness` | One company against one funder, requirement by requirement |
| `score_found_funder` | Score any funder worldwide from criteria Claude read on its website (labelled unverified) |
| `search_funders` / `get_funder` | Browse the database / full record with sources |
| `financial_model_guide` | The questions to ask and a worked example of model assumptions |
| `project_financials` | 3-statement projection, funding analysis and funder-style review from assumptions |
| `review_projections` | Funder-style review of the numbers in a company's own model |
| `list_options`, `memo_template` | Allowed values; memo format |

## Matching method

Funders are first filtered out if they don't cover the country, the type of money, the sector
or the stage, or if their deal size is more than 2× away from the amount sought. Excluded funders
are still reported with the reason. The rest are scored out of 100:

| Factor | Points |
|---|---|
| Sector | 30: exact sector 30, related 18, sector-agnostic 15 |
| Stage | 20: preferred stage 20, one step away 8, not stated 10 |
| Ticket size | 20: inside the range 12–20 (higher near the middle), near miss 4 |
| Impact | 15: impact investor and impact story 15, no mandate 10 |
| Geography | 15: country named 15, sub-region 12, wider region 9–10, emerging markets or global 6 |

Readiness is `ready`, `check_first` (some information is missing) or `not_yet` (a stated
requirement is not met, with what would unlock it).

Regions cover every country: West, East, Central, Southern and North Africa; MENA; South,
Southeast, East and Central Asia; Europe and the EU; North America; Latin America and the
Caribbean; Oceania; emerging markets; global.

## Financial model conventions

Annual periods, 3–10 years. New loans are drawn at the start of the drawdown year and repaid in
equal instalments after the grace period. Interest is charged on the balance outstanding during
the year, so there are no circular references. Depreciation is straight line. Tax is charged only
on positive profit, with no loss carry-forward. No dividends. Working capital is driven by
receivable, inventory and payable days. The full list of assumptions is in
`skill/investor-fit-advisor/references/assumptions.md`.

## Funder data

The verified core currently holds 22 records, strongest on Ghana, Nigeria and Côte d'Ivoire:
DFIs, export credit agencies, impact lenders and funds, and VC/PE. Each record carries source
links, a `confidence` level, a `last_checked` date and a `verification_status`. Run
`python scripts/export_review_sheet.py` to get a spreadsheet for review. To add or correct a
funder, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Run it yourself

```bash
git clone https://github.com/EMMANUEL-LAMPTEY-96/investor-fit && cd investor-fit
pip install -r requirements.txt

python -m investor_fit.server                         # local (stdio) for Claude Desktop / Code
MCP_TRANSPORT=http python -m investor_fit.server      # web server at http://localhost:8000/mcp

pip install pytest && pytest -q                       # 49 tests (Excel tests need LibreOffice)
python scripts/smoke_test.py http://localhost:8000/mcp
python scripts/package_skill.py                       # rebuild dist/investor-fit-advisor.zip

# Build or review a model without Claude
python skill/investor-fit-advisor/scripts/build_model.py --example a.json
python skill/investor-fit-advisor/scripts/build_model.py a.json model.xlsx
python skill/investor-fit-advisor/scripts/review_model.py model.xlsx
```

(Run `python scripts/package_skill.py` once before using the skill scripts from the repo. It
copies the shared model code into the skill folder.)

**Deploy:** Vercel (free; `vercel.json` and `api/index.py` included) or any container host using
the `Dockerfile`. The server is stateless.

## Limits

- The verified database is a starting core. Funders found online are labelled unverified until
  reviewed.
- The model is a planning tool built from the company's own assumptions. It is not audited.
- **This is not financial or investment advice.** Always confirm criteria with the funder.

## Licence

Code: MIT. Funder data: CC BY 4.0 (see `data/LICENSE.md`).

Built by Emmanuel Nii Lante Lamptey.

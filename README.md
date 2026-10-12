# Investor-Fit Agent

**A capital-raising advisor that runs inside Claude.** It finds the funders that fit a company,
checks the company against each funder's requirements, and against any checklist you give it,
using the company's own documents. It also builds or reviews the financial model funders will
test.

One zip file, uploaded to Claude. No server, no API key, no cost.

## What it does

> "Here are our accounts, registration certificate, business plan, and Stanbic's term sheet. We
> process cashew in Ghana and need $500K of working capital. Who should we approach, are we ready,
> and does our plan hold up?"

1. **Reads the documents** and builds a fact sheet in which every figure cites its file and page.
2. **Finds funders from three sources**, in this order of trust:
   - **Your own list:** institutions, term sheets or criteria you provide. These are treated as
     authoritative for your case.
   - **A built-in checked list** of institutions, each with source links.
   - **Live research:** Claude searches the web, reads funders' official criteria pages and adds
     the ones that fit, labelled "found online, not verified".

   If sources disagree, the agent shows both versions and follows yours.
3. **Scores each funder from 0 to 100** and explains why. It lists **readiness gaps**, with what
   would unlock each one: audited accounts, years trading, export history, revenue, impact
   evidence. It also lists **documents** the funder needs that the company doesn't have yet.
   Every institution you named is always reported, including those ruled out, with the reason.
4. **Runs a pre-mortem** on each shortlisted funder: the objections it is likely to raise (for
   example "one customer is 45% of revenue", "dollar loan against cedi revenue", "collateral
   covers 80% of the loan"), why funders care, how to answer, and the evidence to prepare. It
   draws on 32 patterns from public sources: development finance institutions, SME finance
   research and lender guidance. See
   [`references/objections.md`](skill/investor-fit-advisor/references/objections.md).
5. **Checks any checklist** you give it: a bank's requirements, a grant's eligibility rules, an
   investor's document list, your own policy. Each item is marked met, missing, unknown or
   needs review, with the evidence and the fix.
6. **Builds a financial model** if the company has none: a 5-year, three-statement Excel model
   with live formulas and a funding check. It also:
   - **Switches scenarios.** One cell moves the whole model between the base plan, a bad year and
     a good year.
   - **Runs stress tests.** Prices −10%, volumes −20%, costs up, customers paying later, rates up,
     and a 30% currency fall.
   - **Finds breaking points,** e.g. "a 2% price fall leaves repayments uncovered".
   - **Handles currency risk.** It models in local currency with loans or export sales in dollars
     or euros, shows exchange losses, and spots natural hedges.
   - **Suggests loan structures.** It finds the tenor, grace period, amount or currency that would
     pass the lender's test, both in the plan and in a bad year.
7. **Reviews an existing model** in two ways:
   - **Mechanics:** formula errors, numbers typed over formulas, broken patterns, hidden
     assumptions, and a balance sheet that doesn't balance.
   - **Fit with the ask:** whether growth is believable, whether the loan can be repaid (DSCR),
     whether the amount asked matches the real cash need, and whether the use of funds adds up.
8. **Writes an investor-targeting memo** with a readiness plan and next steps.

Example from the included sample company: it plans to raise **$500K**, but its own cash flow
shows a peak need of about **$182K**. Debt service cover is **1.04x** in 2028, against a 1.25x
lender minimum, and a **2%** fall in prices would leave repayments uncovered. The same business
modelled in cedis, with a dollar loan and dollar exports, holds up better: its export revenue
hedges the loan. Borrowing **55%** of the amount would pass even in a bad year.

## Install

**In Claude (web, desktop or mobile), for founders, advisors and anyone else:**

1. Download the skill: **[investor-fit-advisor.zip](https://github.com/EMMANUEL-LAMPTEY-96/investor-fit/raw/main/dist/investor-fit-advisor.zip)**
2. In Claude, go to **Settings → Capabilities** and switch on **Code execution and file
   creation**. Keep web search on for live funder research.
3. Go to **Customize → Skills → + → Create skill → Upload a skill** and choose the zip.
4. Start a chat: *"Help me find funding for my company"*, and attach your documents.

This works on every plan, including Free.

**In Claude Code, one command:**

```
/plugin install investor-fit --marketplace EMMANUEL-LAMPTEY-96/investor-fit
```

On older Claude Code versions:
`/plugin marketplace add EMMANUEL-LAMPTEY-96/investor-fit`, then
`/plugin install investor-fit@investor-fit-marketplace`. The Excel features need
`pip install openpyxl`.

### Bring your own lists

Attach anything: a list of banks, a term sheet, a PDF of eligibility rules. Claude converts it.
For structured input, use the templates in
[`skill/investor-fit-advisor/templates`](skill/investor-fit-advisor/templates):

- `funder_list_template.csv`: the institutions you want checked.
- `checklist_template.csv`: any checklist, using item types: minimum or maximum value, equals,
  one of, yes, document held, or judgement.

## Why it is built this way

- **No invented funders or numbers.** Every institution and requirement comes from your
  material, the checked list, or a web page read during the conversation, with a source. Company
  figures come from your documents, with citations.
- **Calculations are code, not guesses.** Matching, scoring, checklists, projections and model
  checks are plain, tested Python inside the skill. Claude explains the results and handles the
  judgement calls.
- **Spreadsheets that hold up.** Every number in a built model is a live formula driven by blue
  input cells. The tests recalculate each workbook in LibreOffice and compare it with the Python
  engine to the cent.
- **Nothing to host, nothing leaves your Claude.** Documents and data stay in your own
  conversation.

## Scripts inside the skill

| Script | Purpose |
|---|---|
| `match_funders.py` | Rank funders from your list, the built-in list and live research. Shows score breakdown, readiness gaps, documents, sources and conflicts |
| `pre_mortem.py` | Likely objections for one funder or funder type, with how to answer and evidence to prepare |
| `check_checklist.py` | Test the company against any checklist |
| `build_model.py` | Build the Excel financial model from assumptions, with scenarios, stress tests, breaking points and loan options |
| `review_model.py` | Mechanical review of any Excel model, or a funder-style review of its numbers |

### Matching method

A funder is ruled out if it doesn't cover the country, the type of money, the sector or the
stage, or if its deal size is more than 2× away from the amount sought. The rest are scored out
of 100: sector 30, stage 20, ticket size 20, impact 15, geography 15 (country named 15,
sub-region 12, region 9–10, emerging markets or global 6). Readiness is `ready`, `check_first`
(some information is missing) or `not_yet` (a stated requirement is not met, with what would
unlock it). Regions cover every country.

### Financial model conventions

Annual periods, 3–10 years. Loans are drawn at the start of the drawdown year and repaid in equal
instalments after the grace period. Items in a foreign currency use each year's exchange rate, and
loans are revalued each year, with the change shown as an exchange loss. Scenario shocks apply to
every year; the Excel file and the agent's stress tests use the same engine and are checked
against each other. Interest is charged on the balance outstanding during the
year, so there are no circular references. Depreciation is straight line. Tax is charged only on
positive profit, with no loss carry-forward. No dividends. Full list:
`skill/investor-fit-advisor/references/assumptions.md`.

## The built-in list

22 checked records to start, strongest on Ghana, Nigeria and Côte d'Ivoire: DFIs, export credit
agencies, impact lenders and funds, and VC/PE. Each record has source links, a confidence level
and a `last_checked` date (`data/funders.json`; `python scripts/export_review_sheet.py` exports
it as a spreadsheet). To add or correct an institution, see [CONTRIBUTING.md](CONTRIBUTING.md).
A new version of the zip picks up the changes.

## For developers

```bash
git clone https://github.com/EMMANUEL-LAMPTEY-96/investor-fit && cd investor-fit
pip install -r requirements.txt pytest
pytest -q                          # 85 tests (Excel recalculation tests need LibreOffice)
python scripts/package_skill.py    # rebuild the skill zip and the Claude Code plugin (commit both)
```

**Project layout.** `skill/investor-fit-advisor/` is the source of the skill. `investor_fit/` holds
the shared engine (matching, objections, checklists, financial models). `scripts/package_skill.py`
builds `dist/investor-fit-advisor.zip` and the Claude Code plugin in `plugins/investor-fit/` (listed
in `.claude-plugin/marketplace.json`). Publishing a GitHub release attaches the zip to it automatically.

**Optional connector (MCP server).** The same engine is also available as a remote connector for
Claude, Claude Desktop and Claude Code (`investor_fit/server.py`). It offers 10 tools, including
`match_company`, `score_found_funder`, `project_financials` and `review_projections`. It's useful
if you want one hosted, always-current list for many users. Run it with
`MCP_TRANSPORT=http python -m investor_fit.server`, or deploy it with the included `vercel.json`
or `Dockerfile`. The skill does not need it.

## Limits

- The built-in list is a starting set. Funders found online are labelled unverified.
- Results depend on what funders publish; many banks share full criteria only on request. Add
  those through your own list.
- The model is a planning tool built from the company's own assumptions. It is not audited.
- **This is not financial or investment advice.** Always confirm requirements with the funder.

## Licence

Code: MIT. Funder data: CC BY 4.0 (see `data/LICENSE.md`).

Built by Emmanuel Nii Lante Lamptey.

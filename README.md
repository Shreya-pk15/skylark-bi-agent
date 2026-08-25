# Skylark BI Agent

A conversational business-intelligence agent that answers founder-level
questions ("How's our pipeline looking for the energy sector this
quarter?") by querying two live monday.com boards — **Work Orders** and
**Deals** — and reasoning over them with an LLM via Groq.

## Architecture

```
                ┌────────────────────┐
   Streamlit    │      app.py         │   chat UI (the "hosted prototype")
     UI  ─────► │                     │
                └─────────┬───────────┘
                          │
                ┌─────────▼───────────┐
                │   agent/core.py      │   LLM tool-use loop (Groq, free)
                │   (BIAgent)          │
                └────┬──────────┬──────┘
                     │          │
        ┌────────────▼───┐  ┌───▼───────────────┐
        │ agent/tools.py  │  │ agent/             │
        │ (BI functions,  │  │ data_normalize.py  │
        │ Claude tool defs)│ │ (clean + cache)     │
        └────────────┬────┘  └───┬────────────────┘
                     │            │
                     └─────┬──────┘
                           │
                ┌──────────▼───────────┐
                │ agent/monday_client.py│  GraphQL v2, read-only at
                │                       │  query time
                └──────────┬────────────┘
                           │
                     monday.com boards
                  (Work Orders, Deals)
```

- **`app.py`** — Streamlit chat interface. This is what you deploy/host.
- **`agent/core.py`** — the agent loop: sends the conversation + tool
  definitions to the LLM (Groq's API, `llama-3.1-8b-instant` by default),
  executes whatever tools it calls, feeds results back, repeats until it
  has a final answer.
- **`agent/tools.py`** — the actual BI logic (pipeline summary, revenue
  summary, operational metrics, sector breakdown, data-quality report,
  free-text search). These are the "tools" the LLM can call.
- **`agent/data_normalize.py`** — pulls live data from monday.com,
  normalizes messy fields (typos, blank dates, inconsistent casing), and
  caches it for 2 minutes so the agent stays responsive without going
  stale for long.
- **`agent/monday_client.py`** — GraphQL v2 wrapper. The agent only ever
  calls the *read* methods. Write methods exist solely for one-time board
  setup (below) and are never imported by the agent itself.
- **`scripts/clean_data.py`** — turns the two raw source files into clean
  CSVs, ready for import (used once, to prep the monday.com import).
- **`scripts/setup_monday_boards.py`** — one-time script that creates the
  two boards on monday.com with sensible column types and imports the
  cleaned CSVs as items.

## Setup

### 1. Prep the data and create the monday.com boards

```bash
pip install -r requirements.txt

# 1a. Clean the raw source files
python scripts/clean_data.py \
  --work-orders "Work_Order_Tracker_Data.xlsx" \
  --deals "Deal_funnel_Data.xlsx" \
  --out-dir data/

# 1b. Create + populate the two monday.com boards
export MONDAY_API_TOKEN=your_admin_token
python scripts/setup_monday_boards.py
# -> prints MONDAY_WORK_ORDERS_BOARD_ID and MONDAY_DEALS_BOARD_ID
```

(You can also import the CSVs by hand via monday.com's own "Import from
Excel/CSV" board feature if you'd rather map columns visually — the script
just automates that with sensible defaults: `status` columns for
categorical fields like Sector/Execution Status/Deal Stage, `date` for
date fields, `numbers` for currency fields, `text` for identifiers.)

### 2. Configure the agent

```bash
cp .env.example .env
# fill in GROQ_API_KEY (free — get one at https://console.groq.com/keys),
# MONDAY_API_TOKEN, and the two board IDs from step 1b
```

### 3. Run locally

```bash
streamlit run app.py
```

### 4. Host it (free, ~5 minutes)

1. Push this repo to a GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** →
   pick the repo → main file `app.py`.
3. In **Settings → Secrets**, paste the same four values from `.env` in
   TOML form:
   ```toml
   GROQ_API_KEY = "gsk_..."
   MONDAY_API_TOKEN = "..."
   MONDAY_WORK_ORDERS_BOARD_ID = "123456"
   MONDAY_DEALS_BOARD_ID = "123457"
   ```
4. Deploy. You get a public `https://<name>.streamlit.app` link.

## Example questions to try

- "How's our pipeline looking for the Mining sector this quarter?"
- "What's our total outstanding receivable right now?"
- "Give me a leadership update comparing Powerline and Renewables."
- "How reliable is this data — any gaps I should know about?"
- "What's the status of the Sakura deal?"

The agent also supports natural-language follow-ups and these question families:

- **Pipeline:** open/won/dead/on-hold counts, total and average deal value, win
  rate, deal stage, sector, owner, product, and close-date windows.
- **Revenue:** invoiced, billed, collected, receivable, collection rate, billing
  status, sector, and execution-status filters.
- **Operations:** execution-status counts, paused/not-started work, sector
  comparisons, missing delivery dates, and missing invoice dates.
- **Search:** deal, client, sector, status, owner, and keyword lookups across
  both boards.
- **Data health:** missing sectors/values/statuses/dates, negative receivable
  anomalies, and caveats attached to every analytical result.

It states assumptions for relative dates, asks for clarification when a
question is genuinely ambiguous, and says when a requested field is not present
on the connected boards. Monetary values are masked/scaled Rupees.

## Tests

`scripts/clean_data.py` and the tool functions were exercised directly
against the two provided sample files during development (see Decision
Log). There's no formal test suite given the time box — see "what I'd do
differently" in the Decision Log.

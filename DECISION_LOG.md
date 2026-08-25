# Decision Log — Skylark BI Agent

## Interpretation of the brief
I treated this as "build the smallest agent that genuinely queries monday.com
live, handles the specific messiness in the two sample files, and can hold a
real conversation" rather than a maximal feature checklist. Depth on data
resilience and honest caveats over breadth of BI features.

## Key assumptions
- **Read-only means read-only at *query* time.** The two boards still have to
  be created and populated somehow, so I used the monday.com API once for
  that (`scripts/setup_monday_boards.py`), but the agent process itself
  (`agent/core.py`) never imports the write methods — it can only call
  `get_board_items` / `get_board_schema`. This is the one place I diverged
  from a literal reading ("no writes, ever") because a board with nothing in
  it can't be queried.
- **"Quarter" and other relative time references are ambiguous without a
  stated fiscal year**, so the agent is instructed to either state its
  assumption inline (e.g. "assuming Q1 FY26 = Apr–Jun 2026") for mild
  ambiguity, or ask one clarifying question when it truly can't guess (e.g.
  a sector name typed by the user that doesn't match anything on the board).
- **Currency is masked/scaled Rupees**, not real deal values — the agent
  always labels figures "Rs." and never claims they're actual revenue.
- **A "sector" is the right grain for founder questions** ("how's the energy
  sector doing") — I unified `Sector` (Work Orders) and `Sector/service`
  (Deals) into one canonical field so cross-board sector questions
  (`get_sector_breakdown`) are possible at all; they use different column
  names on the two boards.

## Data resilience — specific issues found and how they're handled
1. **Work Orders file has a blank title row above the real header** →
   read with `header=1`.
2. **Deals file has the header row repeated as data rows** (a data row
   whose "Deal Status" cell literally reads `"Deal Status"`) — a classic
   spreadsheet export bug. Detected and dropped by comparing each cell to
   its own column name.
3. **Typo'd categorical values** (`"BIlled"` vs `"Billed"`) — canonicalised
   via lookup maps in `data_normalize.py`, applied both at initial CSV
   cleaning and live on every monday.com pull (since someone could
   re-introduce the typo by hand-editing a board).
4. **Negative "Amount Receivable" values** — real anomaly in the masked
   data (11 of 176 rows). Rather than silently including or excluding them,
   the agent flags the count as a caveat whenever receivables are reported,
   and says explicitly it looks like a masking artifact rather than a real
   credit balance.
5. **Missing values everywhere** (`Masked Deal value` is null on 179/346
   deals; `Sector` occasionally blank) — excluded from sums (not treated as
   zero, which would understate a "no data" case as "no pipeline"), with
   the count of excluded rows surfaced as a caveat so a founder isn't misled
   by a number that's quietly missing 50% of deals.

## Trade-offs and why
- **Groq over a paid LLM API.** Groq's API is
  free with no credit card and is OpenAI-tool-call-compatible, so the agent
  needed no architectural changes beyond the tool-schema format and the
  response-parsing loop — `agent/tools.py` keeps both an Anthropic-shaped
  and an OpenAI-shaped tool definition side by side for exactly this kind of
  swap. The default `llama-3.1-8b-instant` model is configurable with
  `GROQ_MODEL`; model availability can change, so deployment should use a
  model currently enabled for the account. Trade-off: open models can be
  multi-step tool chaining and nuanced clarifying-question judgment than a
  frontier model like Claude or GPT-4-class models; mitigated with an
  explicit, rule-based system prompt (never invent numbers, always call a
  tool first, always surface caveats) rather than relying on the model's
  own judgment for those behaviors.
- **Streamlit over a custom FastAPI + React frontend.** Faster to build and
  to host for free within the time box, and the conversational-chat pattern
  is exactly what Streamlit's `st.chat_message` is built for. Trade-off:
  less UI polish/control than a custom frontend.
- **LLM tool-use over a hand-rolled intent classifier.** Lets the model
  decide which BI function(s) to call and chain them (e.g. call both
  `get_pipeline_summary` and `get_revenue_summary` for a "how's the energy
  sector doing overall" question) instead of me pre-enumerating every
  possible question pattern. Trade-off: less predictable/testable than a
  rules-based router; mitigated by keeping each tool's output structured
  JSON so the model can't silently hallucinate numbers.
- **2-minute cache on board reads**, not a fresh API call every single
  message. Keeps the chat responsive across a multi-turn conversation
  without feeling like it's ignoring live edits for long. Trade-off: a
  monday.com edit made mid-conversation can take up to 2 minutes to show up.
- **CSV cleaning script kept separate from the live normalization module**
  even though they share logic, rather than one shared library, to keep the
  one-time import path simple to read/audit on its own. Trade-off: a small
  amount of duplicated normalization logic between the two.

## "Leadership update" interpretation
I read this as: a founder should be able to ask for one and get an
**executive summary**, not a data dump — headline numbers first, 2-4 bullet
insights, then caveats, per the system prompt's explicit formatting rule.
I did not build a separate scheduled/exported report (e.g. auto-emailed
weekly PDF) — that felt like a distinct feature outside a 6-hour box, and
the conversational path already gets 80% of the value ("give me a leadership
update on Powerline vs Renewables" works today).

## What I'd do differently with more time
- Add a lightweight eval set (10–15 sample founder questions with expected
  tool calls) to catch regressions in the tool-selection prompt.
- Persist conversation history server-side so a refreshed browser tab
  doesn't lose context.
- Let the agent proactively push a scheduled leadership digest (e.g. via
  monday.com automations or email) instead of purely on-demand.
- Add write-back for one narrow, low-risk case: letting the agent flag a
  data-quality issue directly on the offending monday.com item (e.g. an
  "AI flagged" tag), rather than only surfacing it in chat.
- Replace the simple lookup-map canonicalisation with fuzzy matching
  (e.g. rapidfuzz) so novel typos don't need a manually maintained map.

"""
core.py
-------
The conversational agent loop: an LLM (with tool/function calling) <-> our
BI tool functions <-> live monday.com data.

Uses Groq's free API (https://console.groq.com) rather than a paid LLM API —
Groq's free tier needs no credit card and is generous enough for a student
project / demo. Groq exposes an OpenAI-compatible chat.completions endpoint,
so this uses the `openai` Python package pointed at Groq's base_url. The
default model is configurable with GROQ_MODEL.

If you ever want to swap back to a paid model (Anthropic, OpenAI, etc.) only
this file needs to change — agent/tools.py's OPENAI_TOOL_DEFINITIONS already
uses the OpenAI-style tool schema that both Groq and OpenAI expect; see the
bottom of this file for the Anthropic swap-back notes.

Design notes (see DECISION_LOG.md for full rationale):
  - We re-fetch + re-normalize the boards once per turn (short TTL cache in
    data_normalize.py) so the agent always reasons over current monday.com
    state, never a hardcoded snapshot.
  - System prompt instructs the model to (a) ask a clarifying question when
    a query is genuinely ambiguous instead of guessing silently, and
    (b) always surface any `caveats` a tool returns.
  - Max 6 tool-call rounds per turn as a safety valve against loops.
"""
import json
import os

from openai import OpenAI

from .data_normalize import load_board_data
from .monday_client import MondayClient
from .tools import OPENAI_TOOL_DEFINITIONS, call_tool

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL_ALIASES = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-120b",
}
DEFAULT_MODEL = "openai/gpt-oss-120b"
SUPPORTED_MODELS = {DEFAULT_MODEL, "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"}

KNOWN_SECTORS = [
    "Mining", "Powerline", "Renewables", "Railways", "Construction",
    "Tender", "DSP", "Security and Surveillance", "Aviation", "Manufacturing", "Others"
]

SYSTEM_PROMPT = f"""You are Skylark Drones' internal Business Intelligence (BI) AI agent.
You assist founders, CXOs, and business leaders by answering high-level business questions by dynamically querying two live monday.com boards:
1. "Work Orders" (project execution, operational status, invoicing, receivables, billing)
2. "Deals" (sales pipeline, deal stages, close dates, won/lost/on-hold opportunities)

Tracked Sectors in the business:
{", ".join(KNOWN_SECTORS)}

=== QUERY TYPES YOU CAN HANDLE ===

A. PIPELINE & DEALS
   - Total open deal count and value (all or by sector)
   - Deals broken down by stage (Open, Won, Dead, On Hold, In Progress)
   - Pipeline for a specific sector or time period (this quarter, next 30 days)
   - Win rate: Won deals vs total closed (Won + Dead)
   - Deals closing soon (next 30/60/90 days)
   - Average deal value, largest/smallest deals
   - Deal closure probability breakdown
   - Deals by BD/owner personnel code
   - Deals by product/service type

B. REVENUE, BILLING & COLLECTIONS
   - Total invoiced, billed, collected, and outstanding receivable (all or by sector)
   - Cash collection rate (collected / invoiced)
   - Outstanding receivable by sector or billing status
   - Work orders with Stuck billing, Partially Billed, Not Billable, Update Required
   - Overdue or negative receivable anomalies
   - Revenue by document type (PO, LOI, etc.)

C. OPERATIONS & EXECUTION
   - Work order count by Execution Status (Completed, Ongoing, Not Started, Pause/Struck)
   - Sector-wise operational health
   - Projects not yet started or paused
   - Delivery lag: orders with missing Data Delivery Date
   - Work orders by Nature of Work or Type of Work
   - Work orders without a recent invoice

D. CROSS-SECTOR COMPARISONS
   - Full executive sector breakdown (pipeline + revenue side by side)
   - Compare two specific sectors (e.g., Powerline vs Renewables)
   - Best and worst performing sectors by pipeline value or collection rate

E. CLIENT & DEAL LOOKUPS
   - Status of a specific deal by name (e.g., "Sakura deal")
   - All work orders or deals for a specific client code
   - Search by keyword across deal names, client codes, sectors, statuses

F. DATA QUALITY & RELIABILITY
   - Data completeness report (missing values, null fields)
   - Negative receivable artifacts flagged as anomalies
   - Deals missing close dates or sector tags
    - Work orders missing delivery dates, invoice dates, execution status, or sector
   - Overall data confidence score and caveats to trust any figures

G. NATURAL-LANGUAGE FOLLOW-UPS
    - Why/how questions about any returned metric
    - Breakdowns by sector, deal status, deal stage, billing status, execution status, client, or owner
    - Comparisons, rankings, totals, averages, percentages, and record-level lookups
    - Relative date windows such as today, this month, this quarter, next 30/60/90 days, and overdue
    - Conversational follow-ups that refer to the previous result ("what about Renewables?", "show only open ones")

=== RULES FOR REASONING ===
1. Grounding in Real Data: NEVER invent or estimate numbers. Only state figures returned by a tool call. Always call the relevant tool(s) before responding.
2. Query Understanding & Clarification:
   - Unknown sector → tell the user it's not found and list known sectors: {', '.join(KNOWN_SECTORS)}.
   - Vague time period ("this quarter", "Q2") → state your assumed date range inline (e.g. "Assuming Q1 FY26: Apr–Jun 2026") and ask if they prefer another range.
   - Very broad question ("how are things going?") → give headline KPIs across pipeline & revenue, then ask if they want to drill into a specific sector or topic.
   - Questions about fields that don't exist on the boards (e.g., headcount) → honestly say the data isn't available, explain what IS tracked, and suggest an alternative query.
3. Data Caveats: If a tool result contains "caveats", ALWAYS surface them — e.g., missing deal values, negative receivables, low data coverage.
4. Currency & Formatting: All monetary figures are in Indian Rupees (masked/scaled). Prefix with "Rs." and use Lakh/Crore format (e.g., "Rs. 1.25 Cr (Rs. 12,500,000)").
5. Executive Format: For leadership updates or comparisons, use structured tables → headline metrics first → 2–4 key insights → caveats. Crisp and high-signal.
6. Multi-Step Reasoning: If a question requires data from both boards (e.g., sector pipeline vs sector revenue), call multiple tools and synthesize the results.
7. Supported limits: Do not claim fields that are not returned by a tool. For record-level questions, use search_records and clearly say when the result is limited to the first 10 matches.
8. Metric definitions: win rate = Won / (Won + Dead); collection rate = collected / invoiced; average deal value excludes deals with missing values. Report percentages clearly.
"""


class BIAgent:
    def __init__(
        self,
        groq_api_key: str | None = None,
        monday_api_token: str | None = None,
        work_orders_board_id: str | None = None,
        deals_board_id: str | None = None,
        model: str | None = None,
    ):
        api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "No Groq API key found. Get a free one at https://console.groq.com/keys "
                "and set it as GROQ_API_KEY."
            )
        self.client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
        self.monday = MondayClient(monday_api_token)
        self.wo_board_id = work_orders_board_id or os.environ["MONDAY_WORK_ORDERS_BOARD_ID"]
        self.deals_board_id = deals_board_id or os.environ["MONDAY_DEALS_BOARD_ID"]
        configured_model = model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
        configured_model = configured_model.strip().strip('"').strip("'")
        configured_model = MODEL_ALIASES.get(configured_model, configured_model)
        self.model = configured_model if configured_model in SUPPORTED_MODELS else DEFAULT_MODEL
        self.history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, user_message: str, max_tool_rounds: int = 6) -> dict:
        """Run one conversational turn. Returns {"reply": str, "tool_calls": [...]}."""
        board = load_board_data(self.monday, self.wo_board_id, self.deals_board_id)
        self.history.append({"role": "user", "content": user_message})

        tool_call_log = []
        for _ in range(max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=1500,
                tools=OPENAI_TOOL_DEFINITIONS,
                messages=self.history,
            )
            choice = response.choices[0]
            msg = choice.message

            if not msg.tool_calls:
                self.history.append({"role": "assistant", "content": msg.content or ""})
                return {"reply": msg.content or "", "tool_calls": tool_call_log}

            # Record the assistant's tool-call request, then execute each tool
            # and append the results, matching OpenAI/Groq's tool-call protocol.
            self.history.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = call_tool(board, tc.function.name, args)
                tool_call_log.append({"tool": tc.function.name, "input": args, "result": result})
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

        return {"reply": "I couldn't finish gathering the data in time — please try narrowing the question.",
                 "tool_calls": tool_call_log}


# ---------------------------------------------------------------------------
# Swapping back to a paid model later (optional)
# ---------------------------------------------------------------------------
# Anthropic/OpenAI both support the same "tools" pattern shown above with
# minor shape differences (Anthropic wants input_schema instead of
# parameters -- see agent/tools.py's TOOL_DEFINITIONS, which is kept around
# for exactly this reason). To swap: point the client at Anthropic's SDK
# instead of Groq's base_url, pass TOOL_DEFINITIONS instead of
# OPENAI_TOOL_DEFINITIONS, and parse Anthropic's `response.content` blocks
# instead of `response.choices[0].message`.

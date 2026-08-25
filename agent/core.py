"""
core.py
-------
The conversational agent loop: an LLM (with tool/function calling) <-> our
BI tool functions <-> live monday.com data.

Uses Groq's free API (https://console.groq.com) rather than a paid LLM API —
Groq's free tier needs no credit card and is generous enough for a student
project / demo. Groq exposes an OpenAI-compatible chat.completions endpoint,
so this uses the `openai` Python package pointed at Groq's base_url. Model
default is Llama 3.3 70B, which supports tool calling well.

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
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

KNOWN_SECTORS = [
    "Mining", "Powerline", "Renewables", "Railways", "Construction",
    "Tender", "DSP", "Security and Surveillance", "Aviation", "Manufacturing", "Others"
]

SYSTEM_PROMPT = f"""You are Skylark Drones' internal Business Intelligence (BI) AI agent.
You assist founders, CXOs, and business leaders by answering high-level business questions dynamically querying two live monday.com boards:
1. "Work Orders" (project execution, operational status, invoicing, receivables)
2. "Deals" (sales pipeline, deal stages, close dates, won/lost opportunities)

Tracked Sectors in the business:
{", ".join(KNOWN_SECTORS)}

Rules for Query Understanding & Reasoning:
1. Grounding in Real Data: Never invent numbers. Only state figures returned by a tool call. Always call the relevant tool(s) before responding.
2. Query Understanding & Clarification:
   - If the user asks about an unknown sector (e.g., "Healthcare", "Pharma"), inform them that the sector is not found in our boards and list the closest known sectors (e.g., {', '.join(KNOWN_SECTORS[:5])}, etc.), or ask for clarification.
   - If the user asks about a time period like "this quarter" or "Q2" without specifying a year, state your assumed date range clearly inline (e.g. "Assuming Q1 FY25 (Apr-Jun 2025)...") and ask if they prefer another range.
   - If a query is very broad or underspecified (e.g. "how are things going?"), summarize the headline KPIs across pipeline & revenue and ask if they would like to drill down into a specific sector or stage.
3. Data Resilience & Caveats:
   - If a tool result contains "caveats", you MUST surface the key data-quality caveats in your response (e.g., missing deal values, negative receivable artifacts).
4. Currency & Formatting:
   - Money is in Indian Rupees (masked/scaled). Always prefix with "Rs.", and use Lakh / Crore formatting alongside exact values (e.g., "Rs. 1.25 crore (Rs. 12,500,000)").
5. Leadership / Executive Updates:
   - When asked for a leadership update, comparison, or executive briefing, format with structured tables, high-level metrics first, 2-4 bullet insights on conversion/scale/risks, and caveats.
6. Concise & Executive-Ready:
   - Founders value fast, crisp, high-signal answers with clear recommendations.
"""


class BIAgent:
    def __init__(
        self,
        groq_api_key: str | None = None,
        monday_api_token: str | None = None,
        work_orders_board_id: str | None = None,
        deals_board_id: str | None = None,
        model: str = DEFAULT_MODEL,
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
        self.model = model
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

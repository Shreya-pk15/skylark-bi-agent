"""
tools.py
--------
The actual business-intelligence functions the agent can call. Each one
returns a small JSON-serialisable dict: {"data": ..., "caveats": [...]}.
Caveats are always surfaced back to the user by the LLM — this is how the
agent satisfies "communicate data quality issues" instead of silently
dropping rows.

These operate on the BoardData pulled live from monday.com (see
data_normalize.load_board_data) — nothing here is hardcoded from the
original CSVs.
"""
import pandas as pd

from .data_normalize import BoardData

# ---- Tool schemas (Anthropic tool-use format) ------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "get_pipeline_summary",
        "description": (
            "Sales pipeline / deals funnel summary from the Deals board: total "
            "deal value, deal count, and breakdown by stage or status. Filter "
            "by sector and/or a date window on Tentative Close Date to answer "
            "'this quarter' style questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": ["string", "null"], "description": "e.g. 'Mining', 'Powerline', 'Renewables'. Omit or null for all sectors."},
                "close_after": {"type": ["string", "null"], "description": "ISO date (YYYY-MM-DD). Filters Tentative Close Date >= this."},
                "close_before": {"type": ["string", "null"], "description": "ISO date (YYYY-MM-DD). Filters Tentative Close Date <= this."},
                "deal_status": {"type": ["string", "null"], "description": "Open, Won, Dead, On Hold. Omit or null for all."},
            },
        },
    },
    {
        "name": "get_revenue_summary",
        "description": (
            "Revenue / billing / collections summary from the Work Orders board: "
            "invoiced, billed, collected and outstanding-receivable amounts. "
            "Filter by sector and/or execution status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": ["string", "null"], "description": "e.g. 'Mining'. Omit or null for all sectors."},
                "billing_status": {"type": ["string", "null"], "description": "Billed, Partially Billed, Update Required, Stuck, Not Billable."},
            },
        },
    },
    {
        "name": "get_operational_metrics",
        "description": (
            "Operational execution metrics from the Work Orders board: counts of "
            "work orders by Execution Status (Completed, Ongoing, Not Started, "
            "Pause/struck, etc.), optionally filtered by sector."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": ["string", "null"], "description": "e.g. 'Mining', 'Powerline'. Omit or null for all sectors."},
            },
        },
    },
    {
        "name": "get_sector_breakdown",
        "description": (
            "Cross-board comparison: for every sector, shows open pipeline value, "
            "won deal value, and work-order revenue side by side. Good for "
            "'how is X sector performing overall' questions."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_data_quality_report",
        "description": (
            "Returns the current data-quality caveats detected on the live "
            "monday.com boards (missing values, stale/blank dates, etc). Call "
            "this whenever the user asks how reliable/complete the data is, or "
            "proactively include its findings as caveats in any analytical answer."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_records",
        "description": (
            "Free-text search across both boards (deal name, client code, sector, "
            "status, etc.) for 'what's the status of X' style lookups on a "
            "specific client or deal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _filter_sector(df: pd.DataFrame, col: str, sector: str | None) -> pd.DataFrame:
    if not sector or col not in df.columns:
        return df
    return df[df[col].str.lower() == sector.lower()]


def get_pipeline_summary(board: BoardData, sector=None, close_after=None, close_before=None, deal_status=None):
    df = board.deals.copy()
    caveats = list(board.quality_notes)
    if df.empty:
        return {"data": {}, "caveats": caveats + ["Deals board returned no rows."]}

    df = _filter_sector(df, "Sector/service", sector)
    if deal_status and "Deal Status" in df.columns:
        df = df[df["Deal Status"].str.lower() == deal_status.lower()]
    if "Tentative Close Date" in df.columns:
        if close_after:
            df = df[df["Tentative Close Date"] >= pd.to_datetime(close_after)]
        if close_before:
            df = df[df["Tentative Close Date"] <= pd.to_datetime(close_before)]

    total_value = df["Masked Deal value"].sum(skipna=True) if "Masked Deal value" in df.columns else 0
    missing_value_count = int(df["Masked Deal value"].isna().sum()) if "Masked Deal value" in df.columns else 0
    by_stage = (
        df.groupby("Deal Stage")["Masked Deal value"].agg(["count", "sum"]).reset_index().to_dict("records")
        if "Deal Stage" in df.columns else []
    )
    by_status = (
        df.groupby("Deal Status")["Masked Deal value"].agg(["count", "sum"]).reset_index().to_dict("records")
        if "Deal Status" in df.columns else []
    )

    if missing_value_count:
        caveats.append(
            f"{missing_value_count} of {len(df)} matching deals have no deal value recorded "
            "and are excluded from the total value shown."
        )

    return {
        "data": {
            "deal_count": int(len(df)),
            "total_deal_value": float(total_value) if pd.notna(total_value) else 0,
            "by_stage": by_stage,
            "by_status": by_status,
        },
        "caveats": caveats,
    }


def get_revenue_summary(board: BoardData, sector=None, billing_status=None):
    df = board.work_orders.copy()
    caveats = list(board.quality_notes)
    if df.empty:
        return {"data": {}, "caveats": caveats + ["Work Orders board returned no rows."]}

    df = _filter_sector(df, "Sector", sector)
    if billing_status and "Billing Status" in df.columns:
        df = df[df["Billing Status"].str.lower() == billing_status.lower()]

    def col_sum(name):
        return float(df[name].sum(skipna=True)) if name in df.columns else None

    invoiced = col_sum("Amount in Rupees (Incl of GST) (Masked)")
    billed = col_sum("Billed Value in Rupees (Incl of GST.) (Masked)")
    collected = col_sum("Collected Amount in Rupees (Incl of GST.) (Masked)")
    receivable = col_sum("Amount Receivable (Masked)")

    neg = int((df.get("Amount Receivable (Masked)", pd.Series(dtype=float)).fillna(0) < 0).sum())
    if neg:
        caveats.append(
            f"{neg} work order(s) show a negative receivable amount — likely a masking/rounding "
            "artifact in the source data, not an actual credit balance. Treat with caution."
        )

    by_billing_status = (
        df.groupby("Billing Status").size().reset_index(name="count").to_dict("records")
        if "Billing Status" in df.columns else []
    )

    return {
        "data": {
            "work_order_count": int(len(df)),
            "total_invoiced": invoiced,
            "total_billed": billed,
            "total_collected": collected,
            "total_receivable": receivable,
            "by_billing_status": by_billing_status,
        },
        "caveats": caveats,
    }


def get_operational_metrics(board: BoardData, sector=None):
    df = board.work_orders.copy()
    caveats = list(board.quality_notes)
    if df.empty:
        return {"data": {}, "caveats": caveats + ["Work Orders board returned no rows."]}
    df = _filter_sector(df, "Sector", sector)
    by_status = (
        df.groupby("Execution Status").size().reset_index(name="count").to_dict("records")
        if "Execution Status" in df.columns else []
    )
    missing_status = int(df["Execution Status"].isna().sum()) if "Execution Status" in df.columns else 0
    if missing_status:
        caveats.append(f"{missing_status} work order(s) have no Execution Status set.")
    return {"data": {"work_order_count": int(len(df)), "by_execution_status": by_status}, "caveats": caveats}


def get_sector_breakdown(board: BoardData):
    caveats = list(board.quality_notes)
    deals, wo = board.deals, board.work_orders
    sectors = set()
    if "Sector/service" in deals.columns:
        sectors |= set(deals["Sector/service"].dropna().unique())
    if "Sector" in wo.columns:
        sectors |= set(wo["Sector"].dropna().unique())

    rows = []
    for s in sorted(sectors):
        d = deals[deals["Sector/service"] == s] if "Sector/service" in deals.columns else deals.iloc[0:0]
        w = wo[wo["Sector"] == s] if "Sector" in wo.columns else wo.iloc[0:0]
        open_pipeline = d[d["Deal Status"] == "Open"]["Masked Deal value"].sum(skipna=True) if "Deal Status" in d.columns else 0
        won_value = d[d["Deal Status"] == "Won"]["Masked Deal value"].sum(skipna=True) if "Deal Status" in d.columns else 0
        wo_revenue = w["Amount in Rupees (Incl of GST) (Masked)"].sum(skipna=True) if "Amount in Rupees (Incl of GST) (Masked)" in w.columns else 0
        rows.append({
            "sector": s,
            "open_pipeline_value": float(open_pipeline) if pd.notna(open_pipeline) else 0,
            "won_deal_value": float(won_value) if pd.notna(won_value) else 0,
            "work_order_revenue": float(wo_revenue) if pd.notna(wo_revenue) else 0,
            "open_deal_count": int(len(d[d["Deal Status"] == "Open"])) if "Deal Status" in d.columns else 0,
            "work_order_count": int(len(w)),
        })
    return {"data": {"sectors": rows}, "caveats": caveats}


def get_data_quality_report(board: BoardData):
    return {"data": {"notes": board.quality_notes or ["No material data quality issues detected."]}, "caveats": []}


def search_records(board: BoardData, query: str):
    q = query.lower().strip()
    caveats = list(board.quality_notes)

    def row_matches(row):
        return any(q in str(v).lower() for v in row.values if pd.notna(v))

    deal_hits = board.deals[board.deals.apply(row_matches, axis=1)].head(10) if not board.deals.empty else board.deals
    wo_hits = board.work_orders[board.work_orders.apply(row_matches, axis=1)].head(10) if not board.work_orders.empty else board.work_orders

    return {
        "data": {
            "matching_deals": deal_hits.to_dict("records") if not deal_hits.empty else [],
            "matching_work_orders": wo_hits.to_dict("records") if not wo_hits.empty else [],
        },
        "caveats": caveats,
    }


DISPATCH = {
    "get_pipeline_summary": get_pipeline_summary,
    "get_revenue_summary": get_revenue_summary,
    "get_operational_metrics": get_operational_metrics,
    "get_sector_breakdown": get_sector_breakdown,
    "get_data_quality_report": get_data_quality_report,
    "search_records": search_records,
}

# ---- Same tools, in OpenAI/Groq function-calling schema ---------------------
# Groq's API (and OpenAI's) wants {"type": "function", "function": {name,
# description, parameters}} instead of Anthropic's flatter
# {name, description, input_schema}. Kept as a separate constant (rather than
# converting at runtime) so both formats stay easy to read and diff.
OPENAI_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOL_DEFINITIONS
]


def call_tool(board: BoardData, name: str, tool_input: dict):
    if name not in DISPATCH:
        return {"error": f"Unknown tool {name}"}
    return DISPATCH[name](board, **tool_input)

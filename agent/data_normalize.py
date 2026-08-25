"""
data_normalize.py
------------------
Everything the agent needs to turn *whatever is currently on the monday.com
boards* into two clean pandas DataFrames, plus a running data-quality report.

This mirrors scripts/clean_data.py but works on the text values monday.com's
API returns (all column_values come back as strings), and it is re-run on
every conversation turn (with a short TTL cache) so edits made directly in
monday.com are picked up without redeploying the agent.
"""
import time
from dataclasses import dataclass, field

import pandas as pd

from .monday_client import MondayClient

SECTOR_MAP = {
    "mining": "Mining", "powerline": "Powerline", "renewables": "Renewables",
    "railways": "Railways", "construction": "Construction", "tender": "Tender",
    "dsp": "DSP", "security and surveillance": "Security and Surveillance",
    "aviation": "Aviation", "manufacturing": "Manufacturing",
    "others": "Others", "other": "Others",
}
BILLING_STATUS_MAP = {
    "billed": "Billed", "bilied": "Billed", "update required": "Update Required",
    "partially billed": "Partially Billed", "not billable": "Not Billable", "stuck": "Stuck",
}


def _canon(value, lookup):
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower()
    return lookup.get(key, str(value).strip())


def _num(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _date(value):
    if value is None or str(value).strip() == "":
        return pd.NaT
    return pd.to_datetime(value, errors="coerce")


@dataclass
class BoardData:
    work_orders: pd.DataFrame
    deals: pd.DataFrame
    quality_notes: list[str] = field(default_factory=list)
    fetched_at: float = field(default_factory=time.time)


_CACHE: dict[str, BoardData] = {}
_CACHE_TTL_SECONDS = 120


def load_board_data(
    client: MondayClient, work_orders_board_id: str, deals_board_id: str, force_refresh: bool = False
) -> BoardData:
    cache_key = f"{work_orders_board_id}:{deals_board_id}"
    cached = _CACHE.get(cache_key)
    if cached and not force_refresh and (time.time() - cached.fetched_at) < _CACHE_TTL_SECONDS:
        return cached

    wo_items = client.get_board_items(work_orders_board_id)
    deal_items = client.get_board_items(deals_board_id)
    wo_records = client.items_to_records(wo_items)
    deal_records = client.items_to_records(deal_items)

    wo = pd.DataFrame(wo_records)
    deals = pd.DataFrame(deal_records)

    notes: list[str] = []

    if not wo.empty:
        if "Sector" in wo.columns:
            wo["Sector"] = wo["Sector"].apply(lambda v: _canon(v, SECTOR_MAP))
        if "Billing Status" in wo.columns:
            wo["Billing Status"] = wo["Billing Status"].apply(lambda v: _canon(v, BILLING_STATUS_MAP))
        for c in [c for c in wo.columns if "Rupees" in c or "Receivable" in c]:
            wo[c] = wo[c].apply(_num)
        for c in ["Data Delivery Date", "Date of PO/LOI", "Probable Start Date",
                  "Probable End Date", "Last invoice date", "Collection Date"]:
            if c in wo.columns:
                wo[c] = wo[c].apply(_date)
        missing_sector = wo["Sector"].isna().sum() if "Sector" in wo.columns else 0
        if missing_sector:
            notes.append(f"{missing_sector} work order(s) have no Sector set on the board.")
        for column in ["Execution Status", "Data Delivery Date", "Last invoice date"]:
            if column in wo.columns:
                missing = int(wo[column].isna().sum())
                if missing:
                    notes.append(f"{missing} work order(s) have no {column} set on the board.")
        if "Amount Receivable (Masked)" in wo.columns:
            negative_receivables = int((wo["Amount Receivable (Masked)"].fillna(0) < 0).sum())
            if negative_receivables:
                notes.append(f"{negative_receivables} work order(s) have negative receivables; review as source-data anomalies.")

    if not deals.empty:
        if "Sector/service" in deals.columns:
            deals["Sector/service"] = deals["Sector/service"].apply(lambda v: _canon(v, SECTOR_MAP))
        if "Masked Deal value" in deals.columns:
            deals["Masked Deal value"] = deals["Masked Deal value"].apply(_num)
        for c in ["Close Date (A)", "Tentative Close Date", "Created Date"]:
            if c in deals.columns:
                deals[c] = deals[c].apply(_date)
        missing_val = deals["Masked Deal value"].isna().sum() if "Masked Deal value" in deals.columns else 0
        if missing_val:
            notes.append(f"{missing_val} deal(s) have no deal value on the board — excluded from revenue totals.")
        for column in ["Sector/service", "Deal Status", "Deal Stage", "Tentative Close Date"]:
            if column in deals.columns:
                missing = int(deals[column].isna().sum())
                if missing:
                    notes.append(f"{missing} deal(s) have no {column} set on the board.")

    result = BoardData(work_orders=wo, deals=deals, quality_notes=notes)
    _CACHE[cache_key] = result
    return result

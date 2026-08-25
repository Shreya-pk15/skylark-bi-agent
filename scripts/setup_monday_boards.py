"""
setup_monday_boards.py
-----------------------
One-time provisioning script: creates "Work Orders" and "Deals" boards on
monday.com with sensible column types, then imports every row from the
cleaned CSVs (data/work_orders_clean.csv, data/deals_clean.csv) as items.

This is the ONLY part of the project that writes to monday.com — the agent
itself (agent/core.py) is strictly read-only at query time, per the
assignment's integration requirements. Run this once before starting the
agent, then put the two board IDs it prints into your .env file.

Run:
    python scripts/setup_monday_boards.py --work-orders-csv data/work_orders_clean.csv \
                                           --deals-csv data/deals_clean.csv
Requires:
    MONDAY_API_TOKEN env var (Admin-level token, since board creation needs it)
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from agent.monday_client import MondayClient  # noqa: E402

# Column type mapping. monday.com column types used:
#   text, long_text, numbers, date, status (single-select), dropdown
WORK_ORDER_COLUMNS = {
    "Customer Name Code": "text",
    "Nature of Work": "status",
    "Execution Status": "status",
    "Data Delivery Date": "date",
    "Date of PO/LOI": "date",
    "Document Type": "dropdown",
    "Probable Start Date": "date",
    "Probable End Date": "date",
    "BD/KAM Personnel code": "text",
    "Sector": "status",
    "Type of Work": "text",
    "Last invoice date": "date",
    "latest invoice no.": "text",
    "Amount in Rupees (Incl of GST) (Masked)": "numbers",
    "Billed Value in Rupees (Incl of GST.) (Masked)": "numbers",
    "Collected Amount in Rupees (Incl of GST.) (Masked)": "numbers",
    "Amount Receivable (Masked)": "numbers",
    "Invoice Status": "status",
    "WO Status (billed)": "status",
    "Billing Status": "status",
}

DEAL_COLUMNS = {
    "Owner code": "text",
    "Client Code": "text",
    "Deal Status": "status",
    "Close Date (A)": "date",
    "Closure Probability": "status",
    "Masked Deal value": "numbers",
    "Tentative Close Date": "date",
    "Deal Stage": "status",
    "Product deal": "dropdown",
    "Sector/service": "status",
    "Created Date": "date",
}


def clean_val(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


def import_board(client: MondayClient, board_name: str, csv_path: Path, columns: dict, name_col: str):
    print(f"Creating board '{board_name}'...")
    board_id = client.create_board(board_name)
    print(f"  board_id = {board_id}")

    col_ids = {}
    for title, ctype in columns.items():
        try:
            col_ids[title] = client.create_column(board_id, title, ctype)
        except RuntimeError as e:
            print(f"  ! could not create column '{title}' ({ctype}): {e}")

    df = pd.read_csv(csv_path)
    print(f"  Importing {len(df)} rows...")
    for i, row in df.iterrows():
        item_name = str(row.get(name_col, f"Item {i}"))
        col_values = {}
        for title, col_id in col_ids.items():
            if title not in df.columns:
                continue
            val = clean_val(row[title])
            if val is None:
                continue
            ctype = columns[title]
            if ctype == "date":
                col_values[col_id] = {"date": str(val)[:10]}
            elif ctype == "numbers":
                col_values[col_id] = str(val)
            elif ctype in ("status", "dropdown"):
                col_values[col_id] = {"label": str(val)}
            else:
                col_values[col_id] = str(val)
        try:
            client.create_item(board_id, item_name, col_values)
        except RuntimeError as e:
            print(f"  ! row {i} ('{item_name}') failed: {e}")
        if i % 25 == 0:
            print(f"    ...{i}/{len(df)}")

    print(f"Done. {board_name} board_id = {board_id}\n")
    return board_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-orders-csv", default="data/work_orders_clean.csv")
    ap.add_argument("--deals-csv", default="data/deals_clean.csv")
    args = ap.parse_args()

    client = MondayClient()

    wo_id = import_board(client, "Work Orders", Path(args.work_orders_csv), WORK_ORDER_COLUMNS, name_col="Deal name masked")
    deal_id = import_board(client, "Deals", Path(args.deals_csv), DEAL_COLUMNS, name_col="Deal Name")

    print("Add these to your .env / Streamlit secrets:")
    print(f"MONDAY_WORK_ORDERS_BOARD_ID={wo_id}")
    print(f"MONDAY_DEALS_BOARD_ID={deal_id}")


if __name__ == "__main__":
    main()

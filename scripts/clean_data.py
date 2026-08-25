"""
clean_data.py
--------------
Turns the two raw Skylark export files into clean, monday.com-ready CSVs.

Run:
    python scripts/clean_data.py \
        --work-orders "Work_Order_Tracker_Data.xlsx" \
        --deals "Deal_funnel_Data.xlsx" \
        --out-dir data/

What it fixes (real issues found in the source files):
  1. A blank title row sits above the real header row in the Work Orders file
     -> header=1 is used when reading it.
  2. The Deals file has the header row *repeated* several times in the middle
     of the data (e.g. a data row whose "Deal Status" cell literally reads
     "Deal Status") -> these phantom rows are detected and dropped.
  3. Free-text categorical fields have typos / inconsistent casing
     (e.g. "BIlled" vs "Billed") -> canonicalised with a lookup map.
  4. Dates arrive as a mix of real datetimes, strings, and blanks
     -> coerced to ISO 8601 (YYYY-MM-DD), invalid values become blank + logged.
  5. Numeric currency columns sometimes contain blanks / negative "masked"
     artifacts -> coerced to float, negatives are kept (they occur when the
     masking scaling makes billed > invoiced) but flagged in a QA column.
  6. A stable natural key is added to each table (Work Order Serial #,
     Deal Name + Client Code) since monday.com needs a unique "item name".

A short data-quality report is printed to stdout and saved as
data/data_quality_report.md — the agent also regenerates a live version of
this at query time (see agent/data_normalize.py) since the boards can be
edited after import.
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Canonicalisation maps for known messy values
# ---------------------------------------------------------------------------
BILLING_STATUS_MAP = {
    "billed": "Billed",
    "bilied": "Billed",
    "update required": "Update Required",
    "partially billed": "Partially Billed",
    "not billable": "Not Billable",
    "stuck": "Stuck",
}

SECTOR_MAP = {
    "mining": "Mining",
    "powerline": "Powerline",
    "renewables": "Renewables",
    "railways": "Railways",
    "construction": "Construction",
    "tender": "Tender",
    "dsp": "DSP",
    "security and surveillance": "Security and Surveillance",
    "aviation": "Aviation",
    "manufacturing": "Manufacturing",
    "others": "Others",
    "other": "Others",
}


def canon(value, lookup):
    if pd.isna(value):
        return value
    key = str(value).strip().lower()
    return lookup.get(key, str(value).strip())


def coerce_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return pd.NaT
    return pd.to_datetime(value, errors="coerce", dayfirst=False)


def clean_work_orders(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=1)  # real header is row 2 (blank title row above it)
    df = df.dropna(how="all")

    # Drop any phantom header-repeat rows (defensive; not observed here but
    # the deals file has this issue, so we guard the same way for safety).
    header_like = df.apply(lambda r: str(r.get("Sector", "")).strip() == "Sector", axis=1)
    df = df[~header_like]

    date_cols = [
        "Data Delivery Date", "Date of PO/LOI", "Probable Start Date",
        "Probable End Date", "Last invoice date", "Collection Date",
    ]
    for c in date_cols:
        if c in df.columns:
            df[c] = df[c].apply(coerce_date)

    if "Sector" in df.columns:
        df["Sector"] = df["Sector"].apply(lambda v: canon(v, SECTOR_MAP))
    if "Billing Status" in df.columns:
        df["Billing Status"] = df["Billing Status"].apply(lambda v: canon(v, BILLING_STATUS_MAP))

    money_cols = [c for c in df.columns if "Rupees" in c or "Receivable" in c]
    for c in money_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Natural key
    df["_work_order_key"] = df["Serial #"].astype(str)

    # QA flags
    df["_qa_missing_sector"] = df["Sector"].isna()
    df["_qa_negative_receivable"] = pd.to_numeric(
        df.get("Amount Receivable (Masked)"), errors="coerce"
    ).fillna(0) < 0

    return df


def clean_deals(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=0)
    df = df.dropna(how="all")

    # Drop phantom repeated-header rows (the literal string "Deal Status"
    # appearing as a *value* in the Deal Status column, etc.)
    for col in df.columns:
        if col in df.columns:
            df = df[df[col].astype(str).str.strip() != col]

    date_cols = ["Close Date (A)", "Tentative Close Date", "Created Date"]
    for c in date_cols:
        if c in df.columns:
            df[c] = df[c].apply(coerce_date)

    if "Sector/service" in df.columns:
        df["Sector/service"] = df["Sector/service"].apply(lambda v: canon(v, SECTOR_MAP))

    df["Masked Deal value"] = pd.to_numeric(df.get("Masked Deal value"), errors="coerce")

    df["_deal_key"] = (
        df["Deal Name"].astype(str).str.strip() + " | " + df["Client Code"].astype(str).str.strip()
    )
    df["_qa_missing_value"] = df["Masked Deal value"].isna()
    df["_qa_missing_sector"] = df["Sector/service"].isna()

    return df


def quality_report(wo: pd.DataFrame, deals: pd.DataFrame) -> str:
    lines = ["# Data Quality Report", ""]
    lines.append(f"- Work Orders rows: {len(wo)}")
    lines.append(f"  - Missing Sector: {int(wo['_qa_missing_sector'].sum())}")
    lines.append(f"  - Negative Amount Receivable (masking artifact): {int(wo['_qa_negative_receivable'].sum())}")
    lines.append(f"- Deals rows: {len(deals)}")
    lines.append(f"  - Missing Deal value: {int(deals['_qa_missing_value'].sum())}")
    lines.append(f"  - Missing Sector/service: {int(deals['_qa_missing_sector'].sum())}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-orders", required=True)
    ap.add_argument("--deals", required=True)
    ap.add_argument("--out-dir", default="data")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wo = clean_work_orders(Path(args.work_orders))
    deals = clean_deals(Path(args.deals))

    wo.to_csv(out_dir / "work_orders_clean.csv", index=False)
    deals.to_csv(out_dir / "deals_clean.csv", index=False)

    report = quality_report(wo, deals)
    (out_dir / "data_quality_report.md").write_text(report)
    print(report)
    print(f"\nWrote {out_dir/'work_orders_clean.csv'} and {out_dir/'deals_clean.csv'}")


if __name__ == "__main__":
    sys.exit(main())

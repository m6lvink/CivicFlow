# Raw CSV loading and cleanup for model training

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from civicflow.config import (
    COLUMNS_TO_READ,
    CURRENCY_COLS,
    DATE_COLS,
    FLAG_COLS,
    REGRESSOR_WINSOR_QUANTILE,
)


# Currency conversion

_CURRENCY_STRIP = re.compile(r"[\$,\s]")


def _parse_currency(s: pd.Series) -> pd.Series:
    cleaned = (
        s.astype(str)
        .str.replace(_CURRENCY_STRIP, "", regex=True)
    )
    # astype(str) converts None/NaN -> 'None'/'nan'; normalize both to NaN
    # .where avoids a FutureWarning about object downcasting
    null_mask = cleaned.isin({"", "nan", "None", "NaN"})
    cleaned = cleaned.where(~null_mask)   # Positions where True -> NaN
    return pd.to_numeric(cleaned, errors="coerce")


# Flag (Y/N) conversion


def _parse_flag(s: pd.Series) -> pd.Series:
    return s.str.upper().eq("Y")


# Numeric string columns

_NUMERIC_COLS = [
    "totalfloorarea",
    "existingfloorarea",
    "newfloorarea",
    "numroomsadd",
    "numroomsdel",
    "numunitsadd",
    "numunitsdel",
    "finalstories",
]


# Main loader


def load_and_clean(
    path: str | Path,
    *,
    drop_no_issuedate: bool = True,
    winsorise_target: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Raw CSV not found at {path}.\n"
            "Place the Honolulu permits CSV at that path and retry."
        )

    # Read as strings so pandas does not guess mixed-format columns
    # The Python engine handles multi-line quoted contractor strings
    if verbose:
        print(f"Reading {path.name} ...")

    # Only request columns we actually need; keep memory footprint manageable
    usecols = list(COLUMNS_TO_READ)

    df = pd.read_csv(
        path,
        dtype=str,
        usecols=lambda c: c in set(usecols),
        engine="python",  # Required: contractor field contains literal newlines
        on_bad_lines="warn",
    )

    n_raw = len(df)
    if verbose:
        print(f"  Loaded {n_raw:,} rows, {len(df.columns)} columns")

    # Currency columns -> float
    for col in CURRENCY_COLS:
        if col in df.columns:
            df[col] = _parse_currency(df[col])

    # Date columns -> datetime
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

    # Work-type flag columns -> bool
    for col in FLAG_COLS:
        if col in df.columns:
            df[col] = _parse_flag(df[col].fillna("N"))

    # Numeric string columns -> float
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute wait_days target
    df["wait_days_raw"] = (df["issuedate"] - df["createddate"]).dt.days

    # Negative waits are data errors; drop them
    n_negative = (df["wait_days_raw"] < 0).sum()
    if n_negative > 0 and verbose:
        print(f"  Dropping {n_negative:,} rows with negative wait_days (data error)")
    df = df[~(df["wait_days_raw"].notna() & (df["wait_days_raw"] < 0))].copy()

    # Drop never-issued permits when training needs a known target
    n_no_issue = df["issuedate"].isna().sum()
    if verbose:
        print(
            f"  {n_no_issue:,} rows ({n_no_issue/n_raw:.1%}) have no issuedate "
            f"; {'dropping' if drop_no_issuedate else 'keeping'}"
        )
    if drop_no_issuedate:
        df = df.dropna(subset=["issuedate"]).copy()

    # Preserve raw target; winsorisation happens in model.py using training rows
    # winsorise_target stays for compatibility and is now a no-op
    df["wait_days"] = df["wait_days_raw"].copy()
    if verbose:
        wt = df["wait_days"]
        print(f"  wait_days (raw): min: {wt.min():.0f} median: {wt.median():.0f} mean: {wt.mean():.1f}")

    # Filing metadata helpers
    df["filed_year"] = df["createddate"].dt.year.astype("Int16")
    df["filed_month"] = df["createddate"].dt.month.astype("Int8")
    df["filed_dow"] = df["createddate"].dt.dayofweek.astype("Int8")  # 0 = Mon

    # is_fast_track: same-day issuance -- binary label for Stage A classifier
    df["is_fast_track"] = (df["wait_days_raw"] == 0).astype(int)

    # Summary
    if verbose:
        n_final = len(df)
        wt = df["wait_days"]
        print(
            f"\n  Clean dataset: {n_final:,} rows\n"
            f"  wait_days: min: {wt.min():.0f}  median: {wt.median():.0f}  "
            f"mean: {wt.mean():.1f}  p90: {wt.quantile(0.9):.0f}  "
            f"max: {wt.max():.0f}\n"
            f"  Fast-track (0 days): {df['is_fast_track'].mean():.1%}"
        )

    return df

# Feature matrix assembly for training and single-permit inference

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import OrdinalEncoder

from civicflow.config import FLAG_COLS, LEAKAGE_COLS, NON_FEATURE_FLAGS

# Categorical columns encoded for the serve-aligned contract
# Excludes free text and UI-uncollected fields that caused serve-time metric collapse
_CAT_COLS = [
    "buildingpermittype",
    "commercialresidential",
]

# Numeric columns kept as-is; NaN becomes the fit-time median
# Only `estimatedvalueofwork` is collected reliably by the UI
_NUM_COLS = [
    "estimatedvalueofwork",
]

# Work-type boolean flags (already bool in the cleaned df); exclude leakage cols
# and non-feature gov markers so the model's flags match the UI's checkboxes
_FLAG_FEATURE_COLS = [
    c for c in FLAG_COLS if c not in LEAKAGE_COLS and c not in NON_FEATURE_FLAGS
]

# Region extracted from address; retained only for old encoder compatibility
_REGION_COL = "region"


# Helpers

_REGION_RE = re.compile(r"/\s*([^/]+?)\s*\d{5}")  # "/ Waialae Kahala 96816" -> "Waialae Kahala"


def _extract_region(addr: pd.Series) -> pd.Series:
    return addr.fillna("").str.extract(_REGION_RE, expand=False).fillna("Unknown")


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col] if col in df.columns else pd.Series(np.nan, index=df.index, name=col)


# Main builder


def build_features(
    df: pd.DataFrame,
    fit_mask: Optional[pd.Series] = None,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series, Dict[str, Any]]:
    # Sanity: assert no leakage columns sneak in
    leaked = [c for c in LEAKAGE_COLS if c in df.columns]
    if leaked:
        # Exclude unknown categoricals; they should never reach feature assembly
        df = df.drop(columns=leaked)

    # region was removed; user addresses may not match trained regions
    df = df.copy()

    cat_cols_present = [c for c in _CAT_COLS if c in df.columns]
    num_cols_present = [c for c in _NUM_COLS if c in df.columns]
    flag_cols_present = [c for c in _FLAG_FEATURE_COLS if c in df.columns]

    # Fit encoders/medians on training rows when provided to avoid leakage
    fit_rows = df if fit_mask is None else df.loc[fit_mask]

    # Encode categoricals
    enc = OrdinalEncoder(
        handle_unknown="use_encoded_value",
        unknown_value=-1,
        dtype=np.float32,
    )
    # fillna before astype: astype(str) would turn NaN into the literal "nan",
    # so the documented "Unknown" bucket must be filled first
    cat_data = df[cat_cols_present].fillna("Unknown").astype(str)
    enc.fit(fit_rows[cat_cols_present].fillna("Unknown").astype(str))
    cat_encoded = pd.DataFrame(
        enc.transform(cat_data),
        columns=cat_cols_present,
        index=df.index,
    )

    # Numeric: fill NaN with median (computed from fit rows)
    num_data = df[num_cols_present].astype(float)
    num_medians = fit_rows[num_cols_present].astype(float).median()
    num_data = num_data.fillna(num_medians)

    # Flag columns: bool -> int
    flag_data = df[flag_cols_present].astype(int)

    # Assemble
    X = pd.concat([cat_encoded, num_data, flag_data], axis=1)

    # Safety: assert LEAKAGE_COLS are not in X
    bad = [c for c in LEAKAGE_COLS if c in X.columns]
    assert not bad, f"Leakage columns found in feature matrix: {bad}"

    y_class = df["is_fast_track"].astype(int)
    y_reg = np.log1p(df["wait_days"])

    encoders = {
        "ordinal_encoder": enc,
        "cat_cols": cat_cols_present,
        "num_cols": num_cols_present,
        "flag_cols": flag_cols_present,
        "num_medians": num_medians.to_dict(),
    }

    return X, y_class, y_reg, encoders


# Single-row encoder for inference (predict command)


def _coerce_flag_value(x: Any) -> int:
    try:
        if pd.isna(x):
            return 0
    except (TypeError, ValueError):
        pass
    if isinstance(x, str):
        return int(x.strip().upper() in {"Y", "TRUE", "1", "YES"})
    return int(bool(x))


def encode_for_predict(row: Dict[str, Any], encoders: Dict[str, Any]) -> pd.DataFrame:
    df = pd.DataFrame([row])

    # Region
    addr_col = _safe_col(df, "jobaddress").combine_first(_safe_col(df, "joblocation"))
    df[_REGION_COL] = _extract_region(addr_col)

    enc: OrdinalEncoder = encoders["ordinal_encoder"]
    cat_cols: list = encoders["cat_cols"]
    num_cols: list = encoders["num_cols"]
    flag_cols: list = encoders["flag_cols"]
    num_medians: dict = encoders["num_medians"]

    cat_data = (
        df.reindex(columns=cat_cols)
        .fillna("Unknown")
        .astype(str)
    )
    cat_encoded = pd.DataFrame(
        enc.transform(cat_data),
        columns=cat_cols,
        index=df.index,
    )

    # Raw permit JSON may carry formatted number strings
    # Invalid numbers become NaN so median fills handle them
    num_data = df.reindex(columns=num_cols).apply(
        lambda s: pd.to_numeric(
            s.astype(str).str.replace(r"[\$,]", "", regex=True).str.strip(),
            errors="coerce",
        )
    )
    # contractor_score: always fill with neutral prior (50.0) when absent,
    # regardless of the training median, to match the UI promise
    if "contractor_score" in num_data.columns:
        num_data["contractor_score"] = num_data["contractor_score"].fillna(50.0)
    for col, med in num_medians.items():
        if col in num_data.columns:
            num_data[col] = num_data[col].fillna(med)

    # .map avoids a pandas FutureWarning on object-dtype columns
    # _coerce_flag_value handles string false values correctly
    flag_raw = df.reindex(columns=flag_cols)
    flag_data = pd.DataFrame(
        {c: flag_raw[c].map(_coerce_flag_value) for c in flag_cols},
        index=flag_raw.index,
    )

    result = pd.concat([cat_encoded, num_data, flag_data], axis=1)

    # If the encoder recorded exact training feature names, reindex to that order
    # and fill any missing columns (permit dict didn't supply them) with 0
    feature_names: list | None = encoders.get("feature_names")
    if feature_names:
        result = result.reindex(columns=feature_names, fill_value=0)

    return result

# Contractor parsing and leakage-safe credit scoring

from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd


# Parsing patterns

# License number: "State Lic: CT31046" or "State Lic: B18399" (alphanumeric)
_LIC_RE = re.compile(r"State\s+Lic:\s*([A-Za-z0-9]+)", re.I)

# Internal system ID: "ID: 41043291"
_ID_RE = re.compile(r"\bID:\s*(\d+)", re.I)

# Strip "c/o: ..." suffix from the company name (case-insensitive)
_CO_RE = re.compile(r"\s+c/o:.*$", re.I)

# Trailing asterisks / punctuation artefacts
_TRAIL_JUNK = re.compile(r"[\s*]+$")


def _parse_one(raw: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(raw, str) or not raw.strip():
        return None, None, None

    # name - first line (before literal \n embedded in the CSV field)
    name_raw = raw.split("\n")[0].strip()
    name_raw = _CO_RE.sub("", name_raw)   # Remove "c/o: ..."
    name_raw = _TRAIL_JUNK.sub("", name_raw)
    name = name_raw if name_raw and name_raw.upper() not in ("NONE", "N/A", "") else None

    # License
    m = _LIC_RE.search(raw)
    license_num = m.group(1).strip() if m and m.group(1).strip() else None

    # Internal ID (fallback join key)
    m2 = _ID_RE.search(raw)
    internal_id = m2.group(1) if m2 else None

    return name, license_num, internal_id


def extract_contractor_info(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    parsed = df["contractor"].map(_parse_one)
    df["contractor_name"] = parsed.map(lambda t: t[0])
    df["contractor_license"] = parsed.map(lambda t: t[1])
    df["contractor_id_num"] = parsed.map(lambda t: t[2])

    # Only a real primary name may validate the internal ID as a join key
    # Specialty fallback names are display-only
    primary_has_name = df["contractor_name"].notna()

    # Fallback: fill from specialty contractor columns when primary is blank
    for _col in ("contractorelectrical", "contractorplumbing"):
        if _col in df.columns:
            mask = df["contractor_name"].isna() & df[_col].notna()
            df.loc[mask, "contractor_name"] = (
                df.loc[mask, _col]
                .str.strip()
                .replace({"NONE": None, "": None})
            )

    # Prefer license; fall back to internal ID only with a real primary name
    # Shared default IDs get neutral prior, not fabricated history
    df["contractor_key"] = df["contractor_license"].combine_first(
        df["contractor_id_num"].where(primary_has_name)
    )

    return df


# Contractor Credit Score

# Weights sum to 1.0; reliability removed (issued-only data is degenerate)
_WEIGHTS = {
    "avg_wait_score": 0.55,   # Lower avg historical wait -> better score
    "volume_score": 0.25,     # More permits filed -> more experienced
    "recency_score": 0.20,    # Active recently -> not stale data
}

# Neutral prior for contractors with zero history (global median after fitting)
_NEUTRAL_SCORE: float = 50.0


def build_credit_scores(
    df: pd.DataFrame,
    fit_mask: Optional[pd.Series] = None,
) -> pd.DataFrame:
    if "issuedate" not in df.columns:
        raise KeyError(
            "build_credit_scores requires an 'issuedate' column to enforce "
            "outcome-availability leakage safety. Run cleaning first."
        )

    df = df.sort_values("createddate").copy()
    key_col = "contractor_key"
    has_key = df[key_col].notna()

    df["contractor_score"] = _NEUTRAL_SCORE

    if has_key.sum() == 0:
        return df

    # Subset to rows with a valid contractor key
    sub = df.loc[has_key, [key_col, "createddate", "issuedate", "wait_days"]].copy()
    sub["_orig_idx"] = sub.index  # Preserve for re-alignment after merge

    # Provider timeline: each issued permit becomes "known" at its issuedate
    # Cumulative wait-sum/count per contractor along issuedate order
    providers = (
        sub.dropna(subset=["issuedate", "wait_days"])
        .sort_values(["issuedate", key_col])
        .copy()
    )
    pgrp = providers.groupby(key_col, sort=False)
    providers["wait_sum_known"] = pgrp["wait_days"].cumsum()
    providers["count_known"] = pgrp.cumcount() + 1
    providers["known_issuedate"] = providers["issuedate"]

    # Queries: every permit, matched to the latest provider state strictly before
    # its filing date (allow_exact_matches=False => issuedate < createddate)
    queries = sub.dropna(subset=["createddate"]).sort_values("createddate")
    merged = pd.merge_asof(
        queries,
        providers[[key_col, "issuedate", "wait_sum_known", "count_known",
                   "known_issuedate"]],
        left_on="createddate",
        right_on="issuedate",
        by=key_col,
        direction="backward",
        allow_exact_matches=False,
        suffixes=("", "_prov"),
    ).set_index("_orig_idx")

    count_b = merged["count_known"].fillna(0).astype(float)
    avg_wait = merged["wait_sum_known"] / count_b.where(count_b > 0)
    volume = count_b

    cur_ord = merged["createddate"].map(
        lambda d: d.toordinal() if pd.notna(d) else np.nan
    )
    prev_ord = merged["known_issuedate"].map(
        lambda d: d.toordinal() if pd.notna(d) else np.nan
    )
    years_since = ((cur_ord - prev_ord) / 365.25).clip(0, 10)

    stats = pd.DataFrame(
        {
            "avg_wait": avg_wait,
            "volume": volume,
            "years_since": years_since,
        }
    )

    # Fit p5/p95 on training rows when provided so scoring scale does not borrow
    # the future distribution
    if fit_mask is None:
        fit_stats = stats
    else:
        train_idx = stats.index.intersection(fit_mask.index[fit_mask])
        fit_stats = stats.loc[train_idx] if len(train_idx) else stats
    aw_p5, aw_p95 = fit_stats["avg_wait"].quantile([0.05, 0.95])
    stats["avg_wait_score"] = 1.0 - (
        (stats["avg_wait"] - aw_p5) / max(aw_p95 - aw_p5, 1)
    ).clip(0, 1)

    # volume: more is better, log scale; cap at 500
    stats["volume_score"] = (np.log1p(stats["volume"]) / np.log1p(500)).clip(0, 1)

    # recency: closer = better --> invert the years-since measure
    stats["recency_score"] = (1.0 - stats["years_since"] / 10).clip(0, 1).fillna(0)

    # Weighted composite
    composite = (
        stats["avg_wait_score"] * _WEIGHTS["avg_wait_score"]
        + stats["volume_score"] * _WEIGHTS["volume_score"]
        + stats["recency_score"] * _WEIGHTS["recency_score"]
    ) * 100  # Scale to 0-100

    # No knowable prior history (volume == 0) -> neutral prior
    composite = composite.where(stats["volume"] > 0, _NEUTRAL_SCORE)

    # Assign by index: keyed rows with an unparseable createddate are absent from
    # the query set and keep the neutral prior set above
    df.loc[composite.index, "contractor_score"] = composite

    return df

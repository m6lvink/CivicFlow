# Shared paths, column groups, and env settings

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Resolve project root -- one level above this file
ROOT = Path(__file__).resolve().parent.parent

# Load .env if present
load_dotenv(ROOT / ".env", override=False)

# Directory layout
DATA_DIR = ROOT / "data"
ARTIFACTS_DIR = ROOT / "artifacts"
EXAMPLES_DIR = ROOT / "examples"

# Default raw CSV name; place it at data/permits_raw.csv
RAW_CSV = DATA_DIR / "permits_raw.csv"

# Cleaned / feature parquets produced by the pipeline
CLEAN_PARQUET = ARTIFACTS_DIR / "clean.parquet"
FEATURES_PARQUET = ARTIFACTS_DIR / "features.parquet"

# Saved model artifacts
STAGE_A_MODEL = ARTIFACTS_DIR / "stage_a_classifier.joblib"
STAGE_B_MODEL = ARTIFACTS_DIR / "stage_b_regressor.joblib"
ENCODER_FILE = ARTIFACTS_DIR / "encoders.joblib"
CONTRACTOR_SCORES = ARTIFACTS_DIR / "contractor_scores.parquet"

# OpenAI settings

OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
# Optional OpenAI-compatible endpoint (e.g. a self-hosted vLLM server); None -> default OpenAI API
OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL") or None
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
VISION_MAX_PAGES: int = int(os.getenv("VISION_MAX_PAGES", "10"))
# Request timeout; /check degrades to metadata-only on timeout --> /extract returns 502
OPENAI_TIMEOUT: float = float(os.getenv("CIVICFLOW_OPENAI_TIMEOUT", "60"))


# API security settings


def _split_env(name: str, default: str = "") -> List[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


# API keys accepted in the `X-API-Key` header
# Empty means auth is disabled
API_KEYS: List[str] = _split_env("CIVICFLOW_API_KEYS")

# Browser origins allowed by CORS (the Next.js app)
CORS_ORIGINS: List[str] = _split_env(
    "CIVICFLOW_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)

# Host header allow-list (TrustedHostMiddleware); default permits all
ALLOWED_HOSTS: List[str] = _split_env("CIVICFLOW_ALLOWED_HOSTS", "*")

# Per-identity (API key or client IP) request budget, sliding 60s window
RATE_LIMIT_PER_MIN: int = int(os.getenv("CIVICFLOW_RATE_LIMIT_PER_MIN", "240"))

# Daily vision call cap; over budget --> /check degrades to metadata-only
OPENAI_DAILY_CALLS: int = int(os.getenv("CIVICFLOW_OPENAI_DAILY_CALLS", "200"))

# Max plan files accepted per /check request
MAX_PLAN_FILES: int = int(os.getenv("CIVICFLOW_MAX_PLAN_FILES", "10"))


# Column groups

# Keep only needed columns --> lower memory
COLUMNS_TO_READ: List[str] = [
    # Identifiers
    "buildingpermitno",
    "objectid",
    "externalid",
    # Dates (all MM/DD/YYYY strings in source)
    "createddate",
    "issuedate",
    "datereviewscompleted",
    "completeddate",
    # Permit classification
    "buildingpermittype",
    "commercialresidential",
    "proposeduse",
    "statusdescription",
    "statusid",
    # Work-type boolean flags (stored as 'Y'/'N')
    "addition",
    "alteration",
    "newbuilding",
    "demolition",
    "repair",
    "pool",
    "fence",
    "solar",
    "solarvpinstallation",
    "electricalwork",
    "plumbingwork",
    "retainingwall",
    "shellonly",
    "foundationonly",
    "ohana",
    "accessorydwellingunitadu",
    # Occupancy / structure
    "occupancygroupcategory",
    "occupancygroupresidential",
    "typesofconstructionactual",
    "typesofconstructionmin",
    "structurecode",
    # Numeric (stored as currency strings or plain strings)
    "estimatedvalueofwork",
    "acceptedvalue",
    "bpfeescollected",
    "totalfloorarea",
    "existingfloorarea",
    "newfloorarea",
    "numroomsadd",
    "numroomsdel",
    "numunitsadd",
    "numunitsdel",
    "finalstories",
    # Contractor (messy multi-line string)
    "contractor",
    "contractorelectrical",
    "contractorplumbing",
    # Location
    "jobaddress",
    "joblocation",
    "tmk",
    "address",
    # Process routing
    "processreviewtype",
    "locationpermitissued",
    "cityproject",
    "stateproject",
    # Plan/applicant
    "planmaker",
    "applicant",
]

# Currency string columns -> float
CURRENCY_COLS: List[str] = [
    "estimatedvalueofwork",
    "acceptedvalue",
    "bpfeescollected",
]

# Date string columns -> datetime
DATE_COLS: List[str] = [
    "createddate",
    "issuedate",
    "datereviewscompleted",
    "completeddate",
]

# Work-type Y/N flag columns -> boolean
FLAG_COLS: List[str] = [
    "addition",
    "alteration",
    "newbuilding",
    "demolition",
    "repair",
    "pool",
    "fence",
    "solar",
    "solarvpinstallation",
    "electricalwork",
    "plumbingwork",
    "retainingwall",
    "shellonly",
    "foundationonly",
    "ohana",
    "accessorydwellingunitadu",
    "cityproject",
    "stateproject",
]

# Post-filing / leakage columns -- never include in the feature matrix
LEAKAGE_COLS: List[str] = [
    "issuedate",
    "datereviewscompleted",
    "completeddate",
    "statusdescription",
    "statusid",
    "bpfeescollected",   # Collected after issuance
    "locationpermitissued",
]

# Pre-filing feature denylist for values not knowable before filing
# Kept as defense-in-depth for stale or hand-built features.parquet
PREFILING_EXCLUDED_COLS: List[str] = [
    "processreviewtype",
    "acceptedvalue",
    "contractor_score",
]

# Work-type flags that are not model features
# `cityproject` and `stateproject` are constant-zero government markers
NON_FEATURE_FLAGS: List[str] = ["cityproject", "stateproject"]

# Serve-aligned feature contract: only fields the UI collects reliably
# Free text and technical fields caused serve-time metric collapse when imputed
SERVE_COLLECTED_COLS: List[str] = (
    ["buildingpermittype", "commercialresidential", "estimatedvalueofwork"]
    + [c for c in FLAG_COLS if c not in NON_FEATURE_FLAGS]
)

# Model hyper-parameters (sensible defaults; override via CLI flags)
TRAIN_CUTOFF_YEAR: int = 2022   # train on <= this year
VAL_CUTOFF_YEAR: int = 2023     # validate on this year
# test set = 2024-2025 (everything after val cutoff)

REGRESSOR_WINSOR_QUANTILE: float = 0.995  # Clip extreme wait_days for regression target

# Risk band thresholds (days) applied to the combined expected_wait_days output
RISK_BANDS = {
    "Fast": (0, 7),
    "Normal": (7, 60),
    "Slow": (60, 180),
    "High-risk": (180, float("inf")),
}

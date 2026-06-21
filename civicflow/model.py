# Two-stage XGBoost model: fast-track classifier plus duration regressor

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    roc_auc_score,
)
from xgboost import XGBClassifier, XGBRegressor

from civicflow.config import (
    ARTIFACTS_DIR,
    ENCODER_FILE,
    FEATURES_PARQUET,
    REGRESSOR_WINSOR_QUANTILE,
    RISK_BANDS,
    STAGE_A_MODEL,
    STAGE_B_MODEL,
    TRAIN_CUTOFF_YEAR,
    VAL_CUTOFF_YEAR,
)


# Data classes


@dataclass
class PredictionResult:
    expected_wait_days: float
    risk_band: str
    fast_track_probability: float
    top_factors: List[Dict[str, Any]] = field(default_factory=list)
    confidence_low: float = 0.0    # 10th-percentile estimate
    confidence_high: float = 0.0   # 90th-percentile estimate

    def as_dict(self) -> Dict[str, Any]:
        return {
            "expected_wait_days": round(self.expected_wait_days, 1),
            "risk_band": self.risk_band,
            "fast_track_probability": round(self.fast_track_probability, 3),
            "confidence_interval_days": {
                "low": round(self.confidence_low, 1),
                "high": round(self.confidence_high, 1),
            },
            "top_factors": self.top_factors,
        }


# Train / eval helpers


def _time_split(
    X: pd.DataFrame,
    y_class: pd.Series,
    y_reg: pd.Series,
    filed_years: pd.Series,
) -> Tuple[Tuple, Tuple, Tuple]:
    tr = filed_years <= TRAIN_CUTOFF_YEAR
    va = filed_years == VAL_CUTOFF_YEAR
    te = filed_years > VAL_CUTOFF_YEAR

    def _split(mask):
        return X[mask], y_class[mask], y_reg[mask]

    return _split(tr), _split(va), _split(te)


def _risk_band(days: float) -> str:
    for band, (lo, hi) in RISK_BANDS.items():
        if lo <= days < hi:
            return band
    return "High-risk"


def _feature_importance(model: Any, feature_names: List[str], top_n: int = 10) -> List[Dict]:
    try:
        scores = model.feature_importances_
        pairs = sorted(zip(feature_names, scores), key=lambda x: -x[1])[:top_n]
        return [{"feature": f, "importance": round(float(s), 4)} for f, s in pairs]
    except Exception:
        return []


# Training


def train(
    X: pd.DataFrame,
    y_class: pd.Series,
    y_reg: pd.Series,
    filed_years: pd.Series,
    verbose: bool = True,
) -> Tuple[XGBClassifier, XGBRegressor, Dict[str, Any]]:
    (X_tr, yc_tr, yr_tr), (X_va, yc_va, yr_va), (X_te, yc_te, yr_te) = _time_split(
        X, y_class, y_reg, filed_years
    )

    if verbose:
        print(
            f"  Train: {len(X_tr):,}  Val: {len(X_va):,}  Test: {len(X_te):,}"
        )

    # Fail clearly on degenerate splits rather than surfacing opaque XGBoost
    # fit errors deep in the stack
    if len(X_tr) == 0:
        raise ValueError(
            "Training split is empty; check TRAIN_CUTOFF_YEAR against the data's filed years."
        )
    if len(np.unique(yc_tr)) < 2:
        raise ValueError(
            "Training split has only one fast-track class; Stage A cannot be trained."
        )

    # Naive baseline constants from TRAIN review rows (pre-winsorisation), used by
    # the honesty harness in eval_models; captured before yr_tr is winsorised below
    _review_tr0 = yc_tr == 0
    _tr_days = np.expm1(yr_tr[_review_tr0])
    baseline_days = (
        {"mean": float(_tr_days.mean()), "median": float(_tr_days.median())}
        if len(_tr_days)
        else None
    )
    # Test-row filing years for per-year segment metrics
    filed_years_te = filed_years[filed_years > VAL_CUTOFF_YEAR]

    # Winsorise regression target using training-set quantile only (leakage-safe)
    # yr_tr/yr_va/yr_te are log1p(wait_days); back-transform, cap, re-transform
    raw_tr = np.expm1(yr_tr)
    cap = float(raw_tr.quantile(REGRESSOR_WINSOR_QUANTILE))
    yr_tr = np.log1p(raw_tr.clip(upper=cap))
    yr_va = np.log1p(np.expm1(yr_va).clip(upper=cap))
    # yr_te is not capped because test error should use true waits

    # Stage A: fast-track classifier
    clf = XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    # Skip the eval_set when the validation split is empty (avoids opaque errors)
    clf.fit(
        X_tr,
        yc_tr,
        eval_set=[(X_va, yc_va)] if len(X_va) > 0 else None,
        verbose=False,
    )

    # Stage B: duration regressor (review-required rows only)
    # Filter to non-fast-track training rows
    review_mask_tr = yc_tr == 0
    review_mask_va = yc_va == 0

    if int(review_mask_tr.sum()) == 0:
        raise ValueError(
            "No review-track (non-fast-track) rows in the training split; "
            "Stage B regressor cannot be trained."
        )

    reg = XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mae",
        random_state=42,
        n_jobs=-1,
    )
    reg.fit(
        X_tr[review_mask_tr],
        yr_tr[review_mask_tr],
        eval_set=(
            [(X_va[review_mask_va], yr_va[review_mask_va])]
            if int(review_mask_va.sum()) > 0
            else None
        ),
        verbose=False,
    )

    # Metrics on test set (with honesty harness: baselines, route ablation, segments)
    metrics = eval_models(
        X_te, yc_te, yr_te, clf, reg,
        feature_names=list(X.columns),
        baseline_days=baseline_days,
        filed_years_test=filed_years_te,
    )

    if verbose:
        print(
            f"\n  Stage A (classifier)  AUC: {metrics['stage_a_auc']:.4f}  "
            f"AP: {metrics['stage_a_ap']:.4f}"
        )
        print(
            f"  Stage B (regressor)   MAE: {metrics['stage_b_mae']:.1f} days  "
            f"Median-AE: {metrics['stage_b_median_ae']:.1f} days"
        )

    return clf, reg, metrics


# Evaluation


def eval_models(
    X_test: pd.DataFrame,
    y_class_test: pd.Series,
    y_reg_test: pd.Series,
    clf: XGBClassifier,
    reg: XGBRegressor,
    feature_names: Optional[List[str]] = None,
    baseline_days: Optional[Dict[str, float]] = None,
    filed_years_test: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    feature_names = feature_names or list(X_test.columns)

    # Stage A metrics; ROC-AUC / Average-Precision are undefined when the test
    # split has only one class -- guard so a degenerate split can't crash train
    proba_a = clf.predict_proba(X_test)[:, 1]
    single_class = len(np.unique(y_class_test)) < 2
    if single_class:
        auc = float("nan")
        ap = float("nan")
    else:
        auc = roc_auc_score(y_class_test, proba_a)
        ap = average_precision_score(y_class_test, proba_a)

    # Route ablation: permute processreviewtype, re-score Stage A
    auc_route_ablated = float("nan")
    if not single_class and "processreviewtype" in X_test.columns:
        X_perm = X_test.copy()
        rng = np.random.default_rng(42)
        X_perm["processreviewtype"] = rng.permutation(X_perm["processreviewtype"].to_numpy())
        auc_route_ablated = float(roc_auc_score(y_class_test, clf.predict_proba(X_perm)[:, 1]))

    # Stage B metrics (review-required rows only); guard against empty arrays
    review_mask = y_class_test == 0
    baselines: Dict[str, Any] = {}
    mae_by_year: Dict[str, float] = {}
    pred_bias = float("nan")
    if int(review_mask.sum()) == 0:
        mae = float("nan")
        median_ae = float("nan")
    else:
        y_pred_log = reg.predict(X_test[review_mask])
        # Clamp at 0 to match production predict() (waits can't be negative)
        y_pred_days = np.clip(np.expm1(y_pred_log), 0.0, None)
        y_true_days = np.expm1(y_reg_test[review_mask]).to_numpy()
        mae = mean_absolute_error(y_true_days, y_pred_days)
        median_ae = np.median(np.abs(y_true_days - y_pred_days))
        pred_bias = float(np.mean(y_pred_days) - np.mean(y_true_days))

        # Naive constant baselines on the same review rows
        if baseline_days:
            for name, const in baseline_days.items():
                baselines[f"const_{name}_value"] = float(const)
                baselines[f"const_{name}_mae"] = float(np.mean(np.abs(y_true_days - const)))
            best = min((v for k, v in baselines.items() if k.endswith("_mae")), default=float("nan"))
            baselines["best_constant_mae"] = float(best)
            baselines["model_beats_best_constant"] = bool(mae < best)

        # Per-year Stage B MAE (segment metric)
        if filed_years_test is not None:
            yrs = filed_years_test[review_mask].to_numpy()
            for yv in sorted({int(v) for v in yrs[~pd.isna(yrs)]}):
                m = yrs == yv
                if m.sum() > 0:
                    mae_by_year[str(yv)] = float(np.mean(np.abs(y_true_days[m] - y_pred_days[m])))

    return {
        "stage_a_auc": float(auc),
        "stage_a_ap": float(ap),
        "stage_a_auc_route_ablated": auc_route_ablated,
        "stage_b_mae": float(mae),
        "stage_b_median_ae": float(median_ae),
        "stage_b_pred_bias_days": pred_bias,
        "stage_b_baselines": baselines,
        "stage_b_mae_by_year": mae_by_year,
        "stage_a_top_features": _feature_importance(clf, feature_names),
        "stage_b_top_features": _feature_importance(reg, feature_names),
        "n_test": int(len(X_test)),
        "n_review_test": int(review_mask.sum()),
    }


# Inference


def predict(
    X_row: pd.DataFrame,
    clf: XGBClassifier,
    reg: XGBRegressor,
    feature_names: Optional[List[str]] = None,
    log_uncertainty: float = 0.5,   # Heuristic ±log-space half-width; not calibrated from MAE
) -> PredictionResult:
    p_fast = float(clf.predict_proba(X_row)[0, 1])

    # Stage B: predict log-wait for this row regardless of Stage A outcome
    log_wait = float(reg.predict(X_row)[0])
    predicted_days_review = max(0.0, float(np.expm1(log_wait)))

    # Combined expected wait (probability-weighted blend)
    expected_wait = (1.0 - p_fast) * predicted_days_review

    # Confidence interval: ±log_uncertainty in log space
    ci_low = max(0.0, float(np.expm1(max(0, log_wait - log_uncertainty)))) * (1 - p_fast)
    ci_high = max(0.0, float(np.expm1(log_wait + log_uncertainty))) * (1 - p_fast)

    band = _risk_band(expected_wait)

    # Top factors: blend of both models' importances weighted by stage probability
    fn = feature_names or list(X_row.columns)
    factors_a = _feature_importance(clf, fn, top_n=6)
    factors_b = _feature_importance(reg, fn, top_n=6)
    # Merge and deduplicate
    seen = {}
    for f in factors_a:
        seen[f["feature"]] = f["importance"] * p_fast
    for f in factors_b:
        seen[f["feature"]] = seen.get(f["feature"], 0) + f["importance"] * (1 - p_fast)
    top_factors = sorted(
        [{"feature": k, "importance": round(v, 4)} for k, v in seen.items()],
        key=lambda x: -x["importance"],
    )[:8]

    return PredictionResult(
        expected_wait_days=expected_wait,
        risk_band=band,
        fast_track_probability=p_fast,
        top_factors=top_factors,
        confidence_low=ci_low,
        confidence_high=ci_high,
    )


# Persistence


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def save_models(
    clf: XGBClassifier,
    reg: XGBRegressor,
    encoders: Dict[str, Any],
    metrics: Optional[Dict] = None,
) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, STAGE_A_MODEL)
    joblib.dump(reg, STAGE_B_MODEL)
    joblib.dump(encoders, ENCODER_FILE)
    if metrics:
        # Non-finite metric values (possible on degenerate splits) are not valid
        # strict JSON; serialise them as null so /metrics and the frontend parse
        (ARTIFACTS_DIR / "metrics.json").write_text(
            json.dumps(_json_safe(metrics), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        write_model_card(metrics, ARTIFACTS_DIR / "model_card.json")
    print(f"  Models saved to {ARTIFACTS_DIR}/")


# Honesty harness: model card + standalone re-evaluation


def build_model_card(metrics: Dict[str, Any]) -> Dict[str, Any]:
    b = metrics.get("stage_b_baselines", {}) or {}
    notes: List[str] = []

    mae = metrics.get("stage_b_mae")
    best_const = b.get("best_constant_mae")
    if isinstance(mae, (int, float)) and isinstance(best_const, (int, float)) and np.isfinite(best_const):
        if not b.get("model_beats_best_constant", True):
            notes.append(
                f"Stage B does NOT beat a naive constant baseline (model MAE {mae:.1f}d "
                f"vs best constant {best_const:.1f}d). The delay regressor has little/no skill."
            )
        else:
            notes.append(
                f"Stage B beats the best constant baseline (MAE {mae:.1f}d < {best_const:.1f}d)."
            )

    auc = metrics.get("stage_a_auc")
    auc_abl = metrics.get("stage_a_auc_route_ablated")
    if isinstance(auc, (int, float)) and isinstance(auc_abl, (int, float)) and np.isfinite(auc_abl):
        notes.append(
            f"Stage A AUC {auc:.4f} -> {auc_abl:.4f} when 'processreviewtype' is permuted: "
            "material dependence on the routing field. The true route-unknown ceiling "
            "needs a retrain without that feature."
        )

    bias = metrics.get("stage_b_pred_bias_days")
    if isinstance(bias, (int, float)) and np.isfinite(bias):
        notes.append(f"Stage B mean prediction bias: {bias:+.1f} days.")

    return {
        "schema": "civicflow.model_card/v1",
        "metrics": metrics,
        "honesty_notes": notes,
    }


def write_model_card(metrics: Dict[str, Any], path) -> None:
    card = build_model_card(metrics)
    Path(path).write_text(
        json.dumps(_json_safe(card), indent=2, allow_nan=False), encoding="utf-8"
    )


def evaluate_saved(feat_path=FEATURES_PARQUET) -> Dict[str, Any]:
    from civicflow.config import LEAKAGE_COLS, PREFILING_EXCLUDED_COLS

    feat_path = Path(feat_path)
    if not feat_path.exists():
        raise FileNotFoundError(
            f"Features not found: {feat_path}\nRun `civicflow features` first."
        )
    df = pd.read_parquet(feat_path)
    clf, reg, encoders = load_models()

    created = pd.to_datetime(df["createddate"], errors="coerce")
    filed_years = created.dt.year
    meta = ["wait_days", "wait_days_raw", "is_fast_track", "buildingpermitno", "createddate"]
    drop_cols = [c for c in list(LEAKAGE_COLS) + list(PREFILING_EXCLUDED_COLS) + meta if c in df.columns]
    X = df.drop(columns=drop_cols, errors="ignore")
    feature_names = encoders.get("feature_names")
    if feature_names:
        X = X.reindex(columns=feature_names, fill_value=0)

    y_class = df["is_fast_track"].astype(int)
    y_reg = np.log1p(df["wait_days"])
    valid = created.notna() & df["wait_days"].notna() & df["is_fast_track"].notna()
    X, y_class, y_reg, filed_years = X[valid], y_class[valid], y_reg[valid], filed_years[valid]

    te = filed_years > VAL_CUTOFF_YEAR
    tr_review = (filed_years <= TRAIN_CUTOFF_YEAR) & (y_class == 0)
    tr_days = np.expm1(y_reg[tr_review])
    baseline_days = (
        {"mean": float(tr_days.mean()), "median": float(tr_days.median())}
        if int(tr_review.sum())
        else None
    )
    return eval_models(
        X[te], y_class[te], y_reg[te], clf, reg,
        feature_names=list(X.columns),
        baseline_days=baseline_days,
        filed_years_test=filed_years[te],
    )


def load_models() -> Tuple[XGBClassifier, XGBRegressor, Dict[str, Any]]:
    for p in (STAGE_A_MODEL, STAGE_B_MODEL, ENCODER_FILE):
        if not p.exists():
            raise FileNotFoundError(
                f"Model artifact not found: {p}\nRun `civicflow train` first."
            )
    clf = joblib.load(STAGE_A_MODEL)
    reg = joblib.load(STAGE_B_MODEL)
    encoders = joblib.load(ENCODER_FILE)
    return clf, reg, encoders

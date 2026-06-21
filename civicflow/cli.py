# Typer CLI for the CivicFlow pipeline and API server

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="civicflow",
    help="CivicFlow: Honolulu permit delay predictor and requirements agent.",
    add_completion=False,
)
# Use ANSI escape codes even on Windows
# Some terminal emulators choke on Rich's legacy console Unicode path
console = Console(force_terminal=True, legacy_windows=False)


def _load_permit_json(permit_file: Optional[Path], json_str: Optional[str]) -> dict:
    try:
        text = permit_file.read_text(encoding="utf-8") if permit_file else (json_str or "")
        permit = json.loads(text)
    except OSError as exc:
        console.print(f"[red]Error:[/red] Could not read permit file: {exc}")
        raise typer.Exit(1)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Invalid JSON: {exc}")
        raise typer.Exit(1)
    if not isinstance(permit, dict):
        console.print("[red]Error:[/red] Permit JSON must be a JSON object ({...}), not an array or scalar.")
        raise typer.Exit(1)
    return permit


# clean


@app.command(help="Read raw CSV and save clean.parquet.")
def clean(
    src: Path = typer.Option(
        None,
        "--in",
        help="Path to raw permits CSV. Defaults to data/permits_raw.csv",
    ),
    out: Path = typer.Option(
        None,
        "--out",
        help="Output parquet path. Defaults to artifacts/clean.parquet",
    ),
    keep_pending: bool = typer.Option(
        False,
        "--keep-pending",
        help="Keep rows without an issuedate (default: drop them).",
    ),
) -> None:
    from civicflow.cleaning import load_and_clean
    from civicflow.config import ARTIFACTS_DIR, CLEAN_PARQUET, RAW_CSV

    csv_path = src or RAW_CSV
    out_path = out or CLEAN_PARQUET

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold cyan]CivicFlow: clean[/bold cyan]")
    console.print(f"  Source : {csv_path}")
    console.print(f"  Output : {out_path}\n")

    df = load_and_clean(
        csv_path,
        drop_no_issuedate=not keep_pending,
        verbose=True,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False, engine="pyarrow")
    console.print(f"\n[green]OK[/green] Saved {len(df):,} rows -> {out_path}")


# features


@app.command(help="Build features.parquet and contractor scores.")
def features(
    src: Path = typer.Option(
        None, "--in", help="Path to clean.parquet. Defaults to artifacts/clean.parquet"
    ),
    out: Path = typer.Option(
        None, "--out", help="Output features.parquet. Defaults to artifacts/features.parquet"
    ),
) -> None:
    import pandas as pd

    from civicflow.config import ARTIFACTS_DIR, CLEAN_PARQUET, FEATURES_PARQUET, TRAIN_CUTOFF_YEAR
    from civicflow.contractor import build_credit_scores, extract_contractor_info
    from civicflow.features import build_features

    src_path = src or CLEAN_PARQUET
    out_path = out or FEATURES_PARQUET

    if not src_path.exists():
        console.print(f"[red]Error:[/red] {src_path} not found. Run `civicflow clean` first.")
        raise typer.Exit(1)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    console.print("[bold cyan]CivicFlow: features[/bold cyan]")
    console.print(f"  Source : {src_path}")
    console.print(f"  Output : {out_path}\n")

    console.print("  Loading clean data ...")
    df = pd.read_parquet(src_path)
    console.print(f"  {len(df):,} rows")

    console.print("  Parsing contractor strings ...")
    df = extract_contractor_info(df)

    # Shared training-row mask for scoring and feature preprocessing
    # Nullable filed_year means pd.NA rows must be filled out
    train_mask = (df["filed_year"] <= TRAIN_CUTOFF_YEAR).fillna(False)

    console.print("  Computing contractor credit scores (leakage-safe expanding window) ...")
    df = build_credit_scores(df, fit_mask=train_mask)
    contractor_score_stats = df["contractor_score"].describe()
    console.print(f"  Score: mean: {contractor_score_stats['mean']:.1f}  "
                  f"min: {contractor_score_stats['min']:.1f}  "
                  f"max: {contractor_score_stats['max']:.1f}")

    console.print("  Building feature matrix ...")
    import joblib
    from civicflow.config import ENCODER_FILE

    # Fit encoder and numeric medians on training-year rows only to avoid
    # preprocessing leakage from future category levels and distributions
    X, y_class, y_reg, encoders = build_features(df, fit_mask=train_mask)

    # Save feature names so predict/train can stay perfectly aligned
    encoders["feature_names"] = list(X.columns)

    # Attach only the true training targets + identifiers to feat_df
    # (filed_year, contractor_score, etc. are already columns inside X)
    meta_target_cols = ["wait_days", "wait_days_raw", "is_fast_track",
                        "buildingpermitno", "createddate"]
    meta = df[[c for c in meta_target_cols if c in df.columns]].copy()
    feat_df = X.copy()
    for col in meta.columns:
        feat_df[col] = meta[col].values

    out_path.parent.mkdir(parents=True, exist_ok=True)
    feat_df.to_parquet(out_path, index=False, engine="pyarrow")
    joblib.dump(encoders, ENCODER_FILE)
    console.print(f"  Feature matrix: {X.shape[1]} features x {len(X):,} rows")
    console.print(f"\n[green]OK[/green] Saved features -> {out_path}")
    console.print(f"[green]OK[/green] Saved encoders -> {ENCODER_FILE}")


# train


@app.command(help="Train the two-stage delay model.")
def train(
    src: Path = typer.Option(
        None, "--features", help="Path to features.parquet. Defaults to artifacts/features.parquet"
    ),
) -> None:
    import pandas as pd

    from civicflow.config import FEATURES_PARQUET, LEAKAGE_COLS, PREFILING_EXCLUDED_COLS
    from civicflow.model import save_models
    from civicflow.model import train as _train

    feat_path = src or FEATURES_PARQUET

    if not feat_path.exists():
        console.print(f"[red]Error:[/red] {feat_path} not found. Run `civicflow features` first.")
        raise typer.Exit(1)

    console.print("[bold cyan]CivicFlow: train[/bold cyan]")
    console.print(f"  Features: {feat_path}\n")

    df = pd.read_parquet(feat_path)

    # Drop the attached training targets / identifiers plus any leakage or
    # pre-filing-excluded columns (defense-in-depth for stale features.parquet)
    meta_only = ["wait_days", "wait_days_raw", "is_fast_track",
                 "buildingpermitno", "createddate"]
    drop_cols = [
        c for c in LEAKAGE_COLS + PREFILING_EXCLUDED_COLS + meta_only
        if c in df.columns
    ]

    # Extract targets before dropping
    y_class = df["is_fast_track"].astype(int)
    y_reg = df["wait_days"].map(__import__("numpy").log1p)

    # Drop rows with unparseable createddate or missing targets; they have no
    # valid training chronology -- in practice this affects a handful of data errors
    created = pd.to_datetime(df["createddate"], errors="coerce")
    valid_mask = created.notna() & df["wait_days"].notna() & df["is_fast_track"].notna()
    n_dropped = (~valid_mask).sum()
    if n_dropped:
        console.print(f"[yellow]WARN[/yellow] Dropping {n_dropped:,} rows with missing createddate or targets.")
        df = df.loc[valid_mask].copy()
        y_class = y_class.loc[valid_mask]
        y_reg = y_reg.loc[valid_mask]
        created = created.loc[valid_mask]
    # filed_year was removed as a feature (OOD extrapolation risk); derive from createddate
    filed_years = created.dt.year.astype(int)

    X = df.drop(columns=drop_cols, errors="ignore")

    console.print(f"  Feature matrix shape: {X.shape}")
    console.print(f"  Training ...")

    import joblib
    from civicflow.config import ENCODER_FILE

    if not ENCODER_FILE.exists():
        console.print(f"[red]Error:[/red] {ENCODER_FILE} not found. Run `civicflow features` first.")
        raise typer.Exit(1)
    encoders = joblib.load(ENCODER_FILE)
    clf, reg, metrics = _train(X, y_class, y_reg, filed_years, verbose=True)
    save_models(clf, reg, encoders, metrics)

    # Pretty metrics table
    t = Table(title="Test-set Metrics", show_lines=True)
    t.add_column("Stage", style="cyan")
    t.add_column("Metric", style="white")
    t.add_column("Value", style="green")
    t.add_row("Stage A", "ROC-AUC", f"{metrics['stage_a_auc']:.4f}")
    t.add_row("Stage A", "Avg Precision", f"{metrics['stage_a_ap']:.4f}")
    t.add_row("Stage B", "MAE (days)", f"{metrics['stage_b_mae']:.1f}")
    t.add_row("Stage B", "Median-AE (days)", f"{metrics['stage_b_median_ae']:.1f}")
    console.print(t)


# predict


@app.command(help="Predict delay for one permit JSON.")
def predict(
    permit_file: Optional[Path] = typer.Option(
        None, "--permit", help="Path to permit JSON file."
    ),
    json_str: Optional[str] = typer.Option(
        None, "--json", help="Permit data as inline JSON string."
    ),
) -> None:
    from civicflow.config import ENCODER_FILE
    from civicflow.features import encode_for_predict
    from civicflow.model import load_models
    from civicflow.model import predict as _predict

    if not permit_file and not json_str:
        console.print("[red]Error:[/red] Provide --permit <file.json> or --json '<json>'.")
        raise typer.Exit(1)

    permit = _load_permit_json(permit_file, json_str)

    console.print("[bold cyan]CivicFlow: predict[/bold cyan]\n")

    clf, reg, encoders = load_models()
    X_row = encode_for_predict(permit, encoders)
    result = _predict(X_row, clf, reg, feature_names=list(X_row.columns))

    # Output panel
    band_color = {
        "Fast": "green",
        "Normal": "yellow",
        "Slow": "orange1",
        "High-risk": "red",
    }.get(result.risk_band, "white")

    panel_text = (
        f"Expected wait:   [bold]{result.expected_wait_days:.0f} days[/bold]\n"
        f"Risk band:       [{band_color}][bold]{result.risk_band}[/bold][/{band_color}]\n"
        f"Fast-track prob: {result.fast_track_probability:.1%}\n"
        f"Confidence range: {result.confidence_low:.0f}-{result.confidence_high:.0f} days\n"
    )
    console.print(Panel(panel_text, title="Delay Forecast", border_style=band_color))

    if result.top_factors:
        t = Table(title="Top Delay Drivers", show_lines=False)
        t.add_column("Feature", style="cyan")
        t.add_column("Importance", style="white")
        for f in result.top_factors[:6]:
            t.add_row(f["feature"], f"{f['importance']:.4f}")
        console.print(t)


# check


@app.command(help="Check a permit against the DPP checklist.")
def check(
    permit_file: Optional[Path] = typer.Option(
        None, "--permit", help="Path to permit JSON file."
    ),
    json_str: Optional[str] = typer.Option(
        None, "--json", help="Permit data as inline JSON string."
    ),
    plans: Optional[List[Path]] = typer.Option(
        None, "--plans", help="Plan PDF or image files to review (can specify multiple)."
    ),
    output_json: bool = typer.Option(
        False, "--output-json", help="Print full JSON report instead of table."
    ),
) -> None:
    from civicflow.agent.requirements import check_permit

    if not permit_file and not json_str:
        console.print("[red]Error:[/red] Provide --permit <file.json> or --json '<json>'.")
        raise typer.Exit(1)

    permit = _load_permit_json(permit_file, json_str)

    # Suppress the decorative header in JSON mode so stdout is pure JSON
    if not output_json:
        console.print("[bold cyan]CivicFlow: check[/bold cyan]\n")

    report = check_permit(permit, plan_paths=plans)

    if output_json:
        # Plain stdout (not the force_terminal Rich console) so the output is
        # clean, parseable JSON when piped to jq / another program
        print(json.dumps(report.as_dict(), indent=2))
        return

    # Rich table
    status_color = {"READY": "green", "REVIEW": "yellow", "INCOMPLETE": "red"}.get(
        report.overall_status, "white"
    )
    console.print(
        Panel(
            f"[bold]{report.permit_summary}[/bold]\n"
            f"Vision review: {'Yes' if not report.metadata_mode else 'No (metadata only)'}",
            title="Permit Summary",
        )
    )

    t = Table(title="Requirements Check", show_lines=True)
    t.add_column("ID", style="dim", width=8)
    t.add_column("Status", width=10)
    t.add_column("Description")
    t.add_column("Rationale")

    icon_map = {"PASS": "OK", "FLAG": "WARN", "FAIL": "FAIL", "N/A": "--"}
    color_map = {"PASS": "green", "FLAG": "yellow", "FAIL": "red", "N/A": "dim"}
    for f in report.findings:
        icon = icon_map.get(f.status, "?")
        color = color_map.get(f.status, "white")
        t.add_row(
            f.req_id,
            f"[{color}]{icon} {f.status}[/{color}]",
            f.description[:60],
            f.rationale[:60] if f.rationale else "",
        )
    console.print(t)

    console.print(
        f"\nOverall: [{status_color}][bold]{report.overall_status}[/bold][/{status_color}]"
    )

    for w in report.warnings:
        console.print(f"[yellow]WARN {w}[/yellow]")


# eval


def _fmt(v, nd=4):
    try:
        if v is None:
            return "--"
        fv = float(v)
        return "--" if fv != fv else f"{fv:.{nd}f}"  # NaN check
    except (TypeError, ValueError):
        return str(v)


@app.command(help="Report metrics on the held-out test set.")
def eval(
    cached: bool = typer.Option(
        False, "--cached", help="Read the saved metrics.json instead of recomputing."
    ),
) -> None:
    from civicflow.config import ARTIFACTS_DIR, FEATURES_PARQUET

    if not cached and FEATURES_PARQUET.exists():
        from civicflow.model import evaluate_saved, write_model_card
        try:
            m = evaluate_saved()
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1)
        write_model_card(m, ARTIFACTS_DIR / "model_card.json")
        # Refresh metrics.json too so /metrics stays consistent
        from civicflow.model import _json_safe
        (ARTIFACTS_DIR / "metrics.json").write_text(
            json.dumps(_json_safe(m), indent=2), encoding="utf-8"
        )
    else:
        metrics_file = ARTIFACTS_DIR / "metrics.json"
        if not metrics_file.exists():
            console.print("[red]Error:[/red] No metrics.json found. Run `civicflow train` first.")
            raise typer.Exit(1)
        with open(metrics_file, encoding="utf-8") as f:
            m = json.load(f)

    t = Table(title="CivicFlow Model Evaluation (held-out test set)", show_lines=True)
    t.add_column("Stage", style="cyan")
    t.add_column("Metric", style="white")
    t.add_column("Value", style="green bold")

    t.add_row("Stage A: Fast-track classifier", "ROC-AUC", _fmt(m.get("stage_a_auc")))
    t.add_row("Stage A: Fast-track classifier", "ROC-AUC (route ablated)", _fmt(m.get("stage_a_auc_route_ablated")))
    t.add_row("Stage A: Fast-track classifier", "Avg Precision", _fmt(m.get("stage_a_ap")))
    t.add_row("Stage B: Duration regressor", "MAE (days)", _fmt(m.get("stage_b_mae"), 1))
    t.add_row("Stage B: Duration regressor", "Median-AE (days)", _fmt(m.get("stage_b_median_ae"), 1))
    t.add_row("Stage B: Duration regressor", "Pred bias (days)", _fmt(m.get("stage_b_pred_bias_days"), 1))
    t.add_row("Test set", "N total", str(m.get("n_test", "--")))
    t.add_row("Test set", "N review-track", str(m.get("n_review_test", "--")))
    console.print(t)

    # Honesty harness: baselines + verdict
    b = m.get("stage_b_baselines") or {}
    if b:
        tb0 = Table(title="Stage B vs naive baselines (review-track)", show_lines=False)
        tb0.add_column("Predictor", style="cyan")
        tb0.add_column("MAE (days)", style="white")
        tb0.add_row("Model", _fmt(m.get("stage_b_mae"), 1))
        for name in ("mean", "median"):
            if f"const_{name}_mae" in b:
                tb0.add_row(
                    f"Constant train-{name} ({_fmt(b.get(f'const_{name}_value'),0)})",
                    _fmt(b.get(f"const_{name}_mae"), 1),
                )
        console.print(tb0)
        beats = b.get("model_beats_best_constant")
        if beats is False:
            console.print("[red]WARN: Stage B does NOT beat a constant baseline; the delay regressor has little/no skill.[/red]")
        elif beats is True:
            console.print("[green]Stage B beats the best constant baseline.[/green]")

    by_year = m.get("stage_b_mae_by_year") or {}
    if by_year:
        ty = Table(title="Stage B MAE by filing year", show_lines=False)
        ty.add_column("Year", style="cyan")
        ty.add_column("MAE (days)", style="white")
        for yr in sorted(by_year):
            ty.add_row(yr, _fmt(by_year[yr], 1))
        console.print(ty)

    if m.get("stage_a_top_features"):
        ta = Table(title="Stage A: Top Features", show_lines=False)
        ta.add_column("Feature", style="cyan")
        ta.add_column("Importance", style="white")
        for f in m["stage_a_top_features"][:8]:
            ta.add_row(f["feature"], f"{f['importance']:.4f}")
        console.print(ta)

    if m.get("stage_b_top_features"):
        tb = Table(title="Stage B: Top Features", show_lines=False)
        tb.add_column("Feature", style="cyan")
        tb.add_column("Importance", style="white")
        for f in m["stage_b_top_features"][:8]:
            tb.add_row(f["feature"], f"{f['importance']:.4f}")
        console.print(tb)


# serve


@app.command(help="Start the FastAPI web service.")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev mode)."),
) -> None:
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error:[/red] uvicorn is not installed. Run: pip install uvicorn[standard]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]CivicFlow: serve[/bold cyan]")
    console.print(f"  Listening on http://{host}:{port}")
    console.print(f"  OpenAPI docs: http://{host}:{port}/docs\n")
    uvicorn.run("civicflow.api:app", host=host, port=port, reload=reload)


# Entry point


def main() -> None:
    app()


if __name__ == "__main__":
    main()

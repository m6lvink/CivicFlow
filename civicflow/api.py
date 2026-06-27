# FastAPI service for the delay predictor and requirements agent

from __future__ import annotations

import json
import logging
import tempfile
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from civicflow.config import (
    ALLOWED_HOSTS,
    API_KEYS,
    MODELS_DIR,
    CORS_ORIGINS,
    MAX_PLAN_FILES,
    OPENAI_DAILY_CALLS,
    RATE_LIMIT_PER_MIN,
)
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# Application lifespan: load models once at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    from civicflow.model import load_models

    try:
        clf, reg, encoders = load_models()
        app.state.clf = clf
        app.state.reg = reg
        app.state.encoders = encoders
        app.state.models_loaded = True
        logger.info("CivicFlow models loaded successfully.")
    except Exception as exc:
        logger.warning("Models could not be loaded at startup: %s", exc)
        app.state.clf = None
        app.state.reg = None
        app.state.encoders = None
        app.state.models_loaded = False

    if not API_KEYS:
        logger.warning(
            "CIVICFLOW_API_KEYS is empty: API authentication is DISABLED. "
            "Set it in production to require an X-API-Key header on data endpoints."
        )

    yield  # Server runs here

    # Cleanup (nothing to do for joblib objects)
    app.state.models_loaded = False


app = FastAPI(
    title="CivicFlow API",
    description=(
        "Honolulu building-permit delay predictor and DPP requirements agent.\n\n"
        "Run `civicflow serve` to start the server, or `civicflow train` to build "
        "the model files first."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Restrict which Host headers are accepted (defends against host-header attacks)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# Allow the configured browser origins (the Next.js app) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
    expose_headers=["X-Request-ID"],
)


# Security primitives: request IDs, generic errors, auth, rate limiting, budgets


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:  # Unhandled -> generic, no leak
        logger.exception("Unhandled error (request %s)", request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error (request {request_id})"},
            headers={"X-Request-ID": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    return response


def _http_error(status_code: int, detail: str, request: Request) -> HTTPException:
    rid = getattr(request.state, "request_id", "-")
    return HTTPException(status_code=status_code, detail=f"{detail} (request {rid})")


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(request: Request, api_key: Optional[str] = Depends(_api_key_header)) -> None:
    if not API_KEYS:
        return
    if api_key not in API_KEYS:
        raise _http_error(401, "Missing or invalid API key.", request)


class _RateLimiter:
    _MAX_IDENTITIES = 50_000

    def __init__(self) -> None:
        self._hits: Dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def check(self, identity: str, limit_per_min: int) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[identity]
            while dq and dq[0] <= now - 60.0:
                dq.popleft()
            # Bound memory: drop idle identities if the table grows too large
            if len(self._hits) > self._MAX_IDENTITIES:
                for k in [k for k, d in self._hits.items() if not d and k != identity]:
                    del self._hits[k]
            if len(dq) >= limit_per_min:
                return False
            dq.append(now)
            return True


_rate_limiter = _RateLimiter()


def rate_limit(request: Request, api_key: Optional[str] = Depends(_api_key_header)) -> None:
    if api_key and api_key in API_KEYS:
        identity = api_key
    else:
        identity = request.client.host if request.client else "anonymous"
    from civicflow import config as _cfg  # Read limit dynamically (test-patchable)
    if not _rate_limiter.check(identity, _cfg.RATE_LIMIT_PER_MIN):
        raise _http_error(429, "Rate limit exceeded; slow down.", request)


# Combined dependency for protected data endpoints; rate-limit first so that
# unauthenticated/invalid-key attempts are throttled too
_protected = [Depends(rate_limit), Depends(require_api_key)]


class _VisionBudget:
    def __init__(self) -> None:
        self._day = datetime.now(timezone.utc).date()
        self._count = 0
        self._lock = Lock()

    def allow(self) -> bool:
        from civicflow import config as _cfg
        with self._lock:
            today = datetime.now(timezone.utc).date()
            if today != self._day:
                self._day, self._count = today, 0
            if self._count >= _cfg.OPENAI_DAILY_CALLS:
                return False
            self._count += 1
            return True


_vision_budget = _VisionBudget()


# Request / response models


class PermitModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    buildingpermittype: Optional[str] = None
    commercialresidential: Optional[str] = None
    proposeduse: Optional[str] = None
    estimatedvalueofwork: Optional[float] = None
    jobaddress: Optional[str] = None
    applicant: Optional[str] = None
    planmaker: Optional[str] = None
    solar: Optional[Any] = None
    newbuilding: Optional[Any] = None
    alteration: Optional[Any] = None
    electricalwork: Optional[Any] = None


# Internal helpers


def _require_models(request: Request) -> tuple:
    if not request.app.state.models_loaded:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model files not loaded. "
                "Run `civicflow train` then restart the server."
            ),
        )
    return (
        request.app.state.clf,
        request.app.state.reg,
        request.app.state.encoders,
    )


_MAX_PLAN_BYTES = 50 * 1024 * 1024  # 50 MB per uploaded plan file


async def _save_plan_uploads(
    plans: List[UploadFile], request: Request, temp_paths: List[Path]
) -> None:
    for upload in plans:
        suffix = Path(upload.filename or "").suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_paths.append(Path(tmp.name))
            written = 0
            while True:
                chunk = await upload.read(1024 * 1024)  # 1 MB
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_PLAN_BYTES:
                    raise _http_error(
                        413,
                        f"Plan file '{upload.filename}' exceeds the 50 MB limit.",
                        request,
                    )
                tmp.write(chunk)


def _parse_permit_text(text: str) -> Dict[str, Any]:
    try:
        permit = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(permit, dict):
        raise ValueError("Permit JSON must be a JSON object ({...}), not an array or scalar.")
    return permit


# Endpoints


@app.get(
    "/health",
    summary="Legacy health check",
    description="Return service status and whether the model files are loaded.",
)
def health(request: Request) -> Dict[str, Any]:
    return {
        "status": "ok",
        "models_loaded": request.app.state.models_loaded,
    }


@app.get(
    "/live",
    summary="Liveness probe",
    description="Always returns 200 while the process is up.",
)
def live() -> Dict[str, Any]:
    return {"status": "alive"}


@app.get(
    "/ready",
    summary="Readiness probe",
    description="Return 200 only when the model files are loaded, otherwise 503.",
)
def ready(request: Request) -> JSONResponse:
    if request.app.state.models_loaded:
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not_ready"})


@app.get(
    "/metrics",
    summary="Last training run metrics",
    description="Return metrics.json from the last training run.",
    dependencies=_protected,
)
def metrics() -> Dict[str, Any]:
    metrics_file = MODELS_DIR / "metrics.json"
    if not metrics_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No metrics.json found. Run `civicflow train` first.",
        )
    with open(metrics_file, encoding="utf-8") as f:
        return json.load(f)


# Largest categorical cardinality still offered as a dropdown; bigger sets
# (e.g. proposeduse with ~10k free-text values) are reported as high-cardinality
_SCHEMA_MAX_CATEGORICAL = 60


@app.get(
    "/schema",
    summary="Trained input schema (encoder categories)",
    description="Expose trained categorical, flag, and numeric input schema.",
    dependencies=_protected,
)
def schema(request: Request) -> Dict[str, Any]:
    _, _, encoders = _require_models(request)

    enc = encoders["ordinal_encoder"]
    cat_cols = encoders["cat_cols"]
    categorical: Dict[str, List[str]] = {}
    high_cardinality: Dict[str, int] = {}
    for col, values in zip(cat_cols, enc.categories_):
        offered = [str(v) for v in values if str(v) != "Unknown"]
        if len(offered) <= _SCHEMA_MAX_CATEGORICAL:
            categorical[col] = offered
        else:
            high_cardinality[col] = len(offered)

    return {
        "categorical": categorical,
        "high_cardinality": high_cardinality,
        "flags": list(encoders.get("flag_cols", [])),
        "numeric": list(encoders.get("num_cols", [])),
    }


@app.post(
    "/predict",
    summary="Predict permit delay",
    description="Predict the expected wait time for one permit.",
    dependencies=_protected,
)
def predict(permit: PermitModel, request: Request) -> Dict[str, Any]:
    from civicflow.features import encode_for_predict
    from civicflow.model import predict as _predict

    clf, reg, encoders = _require_models(request)
    permit_dict = permit.model_dump(exclude_none=True)

    try:
        X_row = encode_for_predict(permit_dict, encoders)
        result = _predict(X_row, clf, reg, feature_names=list(X_row.columns))
    except Exception as exc:
        rid = getattr(request.state, "request_id", "-")
        logger.exception("Error during predict (request %s)", rid)
        raise _http_error(500, "Internal error during prediction.", request) from exc

    return result.as_dict()


@app.post(
    "/check",
    summary="Check permit against DPP checklist",
    description="Check permit data against the Honolulu DPP submittal checklist.",
    dependencies=_protected,
)
async def check(
    request: Request,
    permit: str = Form(
        ...,
        description="Permit data as a JSON string (same fields as /predict).",
    ),
    plans: Optional[List[UploadFile]] = None,
) -> Dict[str, Any]:
    from civicflow.agent.requirements import _OPENAI_AVAILABLE, check_permit

    # Parse permit JSON from the form field
    try:
        permit_dict = _parse_permit_text(permit)
    except ValueError as exc:
        raise _http_error(400, "Invalid permit JSON.", request) from exc

    if plans and len(plans) > MAX_PLAN_FILES:
        raise _http_error(
            400, f"Too many plan files (max {MAX_PLAN_FILES}).", request
        )

    # Cost guard: over budget, run metadata-only instead of spending
    # Only consume budget when files and OpenAI are both present
    from civicflow import config as _cfg

    budget_exhausted = False
    vision_possible = bool(plans) and bool(_cfg.OPENAI_API_KEY) and _OPENAI_AVAILABLE
    if vision_possible and not _vision_budget.allow():
        plans = None
        budget_exhausted = True

    # Write uploaded plan files to temp paths (deleted in finally)
    temp_paths: List[Path] = []
    try:
        if plans:
            await _save_plan_uploads(plans, request, temp_paths)

        # Run the synchronous PDF/OpenAI work off the event loop so a slow vision
        # call cannot block the worker (and its health probes)
        report = await run_in_threadpool(
            check_permit, permit_dict, plan_paths=temp_paths if temp_paths else None
        )
        if budget_exhausted:
            report.warnings.insert(
                0,
                "Daily vision-review budget exhausted; ran metadata-only check; "
                "plan files were not reviewed.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        rid = getattr(request.state, "request_id", "-")
        logger.exception("Error during check (request %s)", rid)
        raise _http_error(500, "Internal error during check.", request) from exc
    finally:
        for p in temp_paths:
            try:
                p.unlink()
            except OSError:
                pass

    return report.as_dict()


@app.post(
    "/extract",
    summary="Extract permit fields from uploaded documents",
    description="Extract structured permit fields from uploaded documents.",
    dependencies=_protected,
)
async def extract(
    request: Request,
    plans: Optional[List[UploadFile]] = None,
) -> Dict[str, Any]:
    from civicflow import config as _cfg
    from civicflow.agent.extract import _OPENAI_AVAILABLE, extract_permit_fields

    _, _, encoders = _require_models(request)

    if not plans:
        raise _http_error(400, "At least one document file is required.", request)
    if len(plans) > MAX_PLAN_FILES:
        raise _http_error(400, f"Too many plan files (max {MAX_PLAN_FILES}).", request)
    if not (_cfg.OPENAI_API_KEY and _OPENAI_AVAILABLE):
        raise _http_error(
            503, "Document extraction requires OPENAI_API_KEY on the server.", request
        )
    if not _vision_budget.allow():
        raise _http_error(429, "Daily vision budget exhausted; try again tomorrow.", request)

    temp_paths: List[Path] = []
    try:
        await _save_plan_uploads(plans, request, temp_paths)
        # Off the event loop: PDF rendering + the OpenAI call are blocking
        fields, warnings = await run_in_threadpool(
            extract_permit_fields, temp_paths, encoders
        )
    except HTTPException:
        raise
    except Exception as exc:
        rid = getattr(request.state, "request_id", "-")
        logger.exception("Error during extract (request %s)", rid)
        raise _http_error(502, "Document extraction failed.", request) from exc
    finally:
        for p in temp_paths:
            try:
                p.unlink()
            except OSError:
                pass

    return {"fields": fields, "warnings": warnings}

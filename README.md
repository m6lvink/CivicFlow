# CivicFlow

Full-stack AI civic-tech prototype for Honolulu building-permit delay prediction and pre-submission requirements review.
Built on 20 years of Honolulu DPP permit data (2005-2025, ~432K permits).

---

## What it does

| Command | What it does |
|---------|--------------|
| `civicflow predict` | Forecasts permit wait time + risk band (Fast / Normal / Slow / High-risk) with top delay drivers |
| `civicflow check`  | Grades a permit application against the Honolulu DPP checklist; detects missing sheets before you file |

The prediction model is a **two-stage XGBoost pipeline**:
- **Stage A** - fast-track classifier (44% of permits are same-day OTC)
- **Stage B** - duration regressor on review-required permits (`log1p(wait_days)`)

The model uses **only pre-filing fields an applicant can supply before submitting** (permit
type, commercial/residential, estimated value, work-type flags). Routing fields the agency
assigns after intake are excluded, so the reported metrics match what the shipped
form serves (train == serve).

Test-set metrics (held-out 2024-2025 data, 15,511 permits / 4,057 review-track):
- Stage A AUC: **0.951** (Avg Precision 0.957) - same-day OTC eligibility from work type
- Stage B MAE: **85.2 days**, Median-AE: **58.0 days**

Stage B only just edges the naive constant-mean baseline (86.4 days) and runs ~52 days
optimistic on average. Same-day eligibility (Stage A) is genuinely predictable; precise delay
duration (Stage B) is hard with pre-filing fields alone, and the model card reflects this.

---

## Quick start

```powershell
# 1. Install
pip install -e .

# 2. Place the raw CSV
#    data/permits_raw.csv  (the Honolulu permits export, ~321 MB)

# 3. Copy .env.example -> .env and fill in OPENAI_API_KEY (needed for 'check --plans')
copy .env.example .env

# 4. Build the pipeline
civicflow clean          # 432K rows parsed -> models/clean.parquet
civicflow features       # contractor scores + feature matrix
civicflow train          # two-stage model -> models/

# 5. Use it
civicflow predict --permit examples/permit_solar.json
civicflow predict --permit examples/permit_new_building.json
civicflow check  --permit examples/permit_solar.json
civicflow check  --permit examples/permit_solar.json --plans myplans.pdf
civicflow eval   # metrics report
```

---

## Predict input format

Pass any subset of these fields as JSON. Missing fields fall back to training-time medians.

```json
{
  "commercialresidential": "Residential",
  "buildingpermittype": "4 - Addition, alteration or repair (no change in units)",
  "estimatedvalueofwork": 25000,
  "solar": true,
  "solarvpinstallation": true,
  "electricalwork": true,
  "alteration": true
}
```

The model's input is exactly the set of pre-filing fields the web form collects, so a request
built from the UI encodes cleanly (no silent unknowns). Query `GET /schema` for the exact
accepted categorical values and the full flag list.

**Key fields that most influence delay:**
- `commercialresidential`: Residential OTC rate 48%, Commercial 5.6%
- `solar` / `solarvpinstallation`: solar permits are largely same-day
- `alteration` / `newbuilding` / `demolition`: work type drives review-track routing
- `estimatedvalueofwork`

Three fields from earlier versions were **dropped** so reported metrics match production:
`processreviewtype` (the agency's routing decision, not known before filing),
`acceptedvalue` (a post-intake agency adjustment, ~= `estimatedvalueofwork`), and
`contractor_score` (not something an applicant can supply). A server-side contractor lookup is
planned but not yet a model input.

---

## Requirements agent (`check`)

Grades the permit against the **Honolulu DPP submittal checklist** (encoded in `civicflow/agent/checklist.py`).

**Without `--plans`**: deterministic metadata check (no API key needed).

**With `--plans <file.pdf>`**: sends plan pages to **gpt-4o** vision for architectural completeness review (requires `OPENAI_API_KEY`).

Status codes: `PASS` / `FLAG` (needs verification) / `FAIL` (clearly missing).

---

## Web API

Start the FastAPI server after training:

```powershell
civicflow serve              # http://127.0.0.1:8000
civicflow serve --port 8080  # custom port
civicflow serve --reload     # dev mode (auto-restart on code changes)
```

Interactive docs: `http://127.0.0.1:8000/docs`

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Legacy health check; reports `models_loaded` |
| `GET`  | `/live` | Liveness probe; always 200 while the process is up |
| `GET`  | `/ready` | Readiness probe; 200 only when models are loaded, else 503 |
| `GET`  | `/metrics` | Last training run metrics (Stage A AUC, Stage B MAE, ...) |
| `GET`  | `/schema` | Exact trained input categories + flag/numeric field names |
| `POST` | `/predict` | JSON permit body -> delay forecast |
| `POST` | `/check` | Multipart: `permit` form field (JSON) + optional `plans` file uploads -> checklist report |
| `POST` | `/extract` | Multipart: `plans` file uploads -> permit fields read from the documents via gpt-4o vision (requires `OPENAI_API_KEY`) |

**Authentication & limits:** when `CIVICFLOW_API_KEYS` is set, the data endpoints
(`/metrics`, `/schema`, `/predict`, `/check`, `/extract`) require a matching `X-API-Key` header;
the probes (`/health`, `/live`, `/ready`) stay open. All data endpoints are rate-limited per
identity (`CIVICFLOW_RATE_LIMIT_PER_MIN`), and `/check` / `/extract` are bounded by a per-day
OpenAI vision budget and a max plan-file count. See `.env.example` for the full list.

**`/predict` example:**
```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d @examples/permit_solar.json
```

**`/check` example (metadata only):**
```bash
curl -X POST http://127.0.0.1:8000/check \
  -F "permit=$(cat examples/permit_solar.json)"
```

**`/check` with plan upload (triggers gpt-4o vision if `OPENAI_API_KEY` is set):**
```bash
curl -X POST http://127.0.0.1:8000/check \
  -F "permit=$(cat examples/permit_solar.json)" \
  -F "plans=@myplans.pdf"
```

---

## Web UI (frontend)

A Next.js app in `frontend/` built for non-technical users: drop your permit documents
(PDFs or images) onto the page and press **Run**. The app reads the documents with gpt-4o
vision, fills in the permit details it finds (shown in an editable "What we read from your
documents" panel), and runs both the delay forecast and the DPP requirements check in one go.
No documents, or no `OPENAI_API_KEY` on the server? An "Enter details manually" form covers
the same flow by hand.

```powershell
cd frontend
npm install
npm run dev    # http://localhost:3000
```

Requires the FastAPI backend running on port 8000 first. See `frontend/README.md` for details.

---

## Project layout

```
civicflow/
  cli.py            # Typer CLI: clean | features | train | predict | check | eval | serve
  api.py            # FastAPI web service (health/live/ready/metrics/schema/predict/check)
  config.py         # paths, column groups, feature contract, env settings
  cleaning.py       # currency/date/target derivation
  contractor.py     # name/license parsing + Credit Score (batch-computed)
  features.py       # leakage-safe, serve-aligned feature assembly
  model.py          # two-stage XGBoost train/predict/eval + honest model card
  agent/
    checklist.py    # Honolulu DPP encoded requirements
    requirements.py # OpenAI gpt-4o vision agent
    extract.py      # gpt-4o permit-field extraction from uploaded documents

data/               # raw CSV (gitignored)
models/          # runtime models tracked; generated parquets remain gitignored
examples/           # sample permit JSONs
```

---

## Deployment & license

- **License:** proprietary - see [`LICENSE`](LICENSE). All rights reserved.
- **Reproducible installs:** `requirements.lock` pins the direct dependencies to exact
  versions; install with `pip install -r requirements.lock`.
- **Health probes:** `/live` (liveness) and `/ready` (readiness, 503 until models load) for
  orchestrated deployments.
- **Render:** apply `render.yaml` to create one private Docker API service and one Next.js
  Web Service. Enter `OPENAI_API_KEY` when prompted. Render generates and shares the backend
  API key; no secrets use `NEXT_PUBLIC_*`.
- **Pilot limits:** one API instance and worker, 60 requests/minute, 50 vision calls/day,
  four files/request, and ten rendered pages/request. In-memory limits require one process.
- **Operations:** use `/live` for liveness and `/ready` for model readiness. Render must alert
  on failed deploys/readiness and OpenAI must enforce a spend limit. Review errors, fallbacks,
  and vision usage daily during the pilot. Roll back by restoring the previous Render deploy,
  which also restores its versioned model files.
- **Document handling:** uploads are held in temporary files for one request, deleted in a
  `finally` block, and never intentionally logged or persisted.
- **LLM direction:** cloud LLM calls are transitional; a self-hosted Jetstream2 LLM behind the CivicFlow API is the planned backend.

---

## Data notes

- Raw CSV: `data/permits_raw.csv` (321 MB, ~432K records)
- **Known gotcha**: `wc -l` reports 831K lines - the contractor field contains literal `\n` inside quoted CSV strings. Always parse with `engine='python'` (pandas handles this correctly).
- Never-issued permits (~13.7%) are excluded from model training; they have no ground-truth wait time.
- `datereviewscompleted` is excluded from all features (only knowable mid-process, not at submission).
- `filed_year` is excluded from features - tree models can't extrapolate past training max year (2022) to 2024-2025 test data.

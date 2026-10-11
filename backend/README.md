# Budgeted Research Agent Backend

This directory is the self-contained Python project for the research engine,
provider integrations, CLI, API, persistence, evaluation code, and backend tests.

From this directory, install the development environment and run the tests with:

```bash
uv sync --extra dev
uv run pytest -v
```

Run a deterministic research workflow and inspect its generated artifacts:

```bash
uv run bra offline-demo
```

The command writes a self-contained run directory under `runs/<run_id>/`.

## Live fixed-depth research

Create a local environment file and fill in credentials plus an account-available,
JSON-mode-capable Moonshot model:

```bash
cp .env.example .env
```

Then run the real fixed-depth baseline:

```bash
uv run bra providers-check
uv run bra research "Compare LangGraph, AutoGen, and CrewAI for an internal agent platform"
```

Select the adaptive policy explicitly to make evidence-aware allocation and stopping
decisions. Use larger search and page budgets so it has room to deepen weak branches:

```bash
uv run bra research \
  "Compare LangGraph, AutoGen, and CrewAI for an internal agent platform" \
  --policy adaptive \
  --max-searches 8 \
  --max-page-fetches 20
```

For a minimal live end-to-end check, use the smoke profile. It keeps the normal
fixed-depth defaults untouched while using one subquestion, one search, one valid
page, two selected chunks, and at most two evidence items:

```bash
uv run bra research "Python list 和 tuple 的主要区别是什么？" --smoke
uv run bra research "Python list 和 tuple 的主要区别是什么？" --policy adaptive --smoke
```

`REQUEST_TIMEOUT_SECONDS` controls Tavily and page-download requests, while
`MOONSHOT_TIMEOUT_SECONDS` separately controls slower LLM generations. If a live run
reaches evidence extraction and times out, retry one subquestion from its persisted
pages without issuing new searches or downloads:

```bash
uv run bra extraction-check runs/<run_id> --subquestion sq_01
```

`PROVIDER_MAX_RETRIES` defaults to `1`. Moonshot uses it for transient API retries,
Tavily uses it only for connection/timeout, HTTP 408/429, and 5xx failures, and the
Planner uses it for schema-invalid JSON. Other 4xx responses are not retried. Retry
usage from schema-invalid Planner responses is accumulated rather than hidden.

The `.env` file and generated `runs/` directory are ignored by Git. Model pricing
is deliberately configuration-driven because it varies by model and over time.

## Persistent API

Start the FastAPI application from `backend/`:

```bash
uv sync --extra dev
uv run bra serve --reload
```

By default the service stores run metadata, state, action events, evidence and
reports in the local `data/budgeted-research.db` SQLite file. SQLite is embedded;
there is no database server to install or deploy. Set `BRA_DATABASE_PATH` and
`BRA_RUNS_PATH` to override the database and artifact locations. The local Vite
origin is allowed by default; `BRA_CORS_ORIGINS` accepts a comma-separated list
when the frontend runs elsewhere.

Create an Adaptive run:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Python list 和 tuple 的主要区别是什么？",
    "policy": "adaptive",
    "profile": "smoke",
    "budget": {
      "max_tokens": 20000,
      "max_searches": 2,
      "max_page_fetches": 4,
      "max_elapsed_seconds": 600
    }
  }'
```

`profile` accepts `standard` (the default full policy) or `smoke`. The Smoke
profile is shared with the CLI `--smoke` flag and limits the policy to one
subquestion, two search candidates, and a small source/evidence set. Budget
limits remain independently controlled by the request.

The returned run ID can be used with these endpoints:

- `GET /api/v1/runs` and `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events`
- `GET /api/v1/runs/{run_id}/events/stream` (SSE with `Last-Event-ID` replay)
- `GET /api/v1/runs/{run_id}/evidence`
- `GET /api/v1/runs/{run_id}/report` and `report.md`
- `POST /api/v1/runs/{run_id}/cancel`

OpenAPI documentation is available at `http://127.0.0.1:8000/docs` while the
service is running. Runs that were still pending or running when the process
stopped are marked failed on restart; completed history remains queryable.
User-cancelled runs keep a `cancelled` terminal status and aggregate usage from
the actions completed before cancellation.

The repository-level product documentation is available in [`../docs/`](../docs/README.md).

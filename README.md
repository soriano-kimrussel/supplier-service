# Supplier Service

A small FastAPI service that owns one business responsibility: supplier records. It ingests them
from an external directory, normalises and stores them in PostgreSQL, queues each one for
enrichment by Claude, and serves them to other services over a versioned REST API. Nothing else
in the system talks to the supplier directory or to the suppliers table directly.

It is a self-contained example, not an extract from a production codebase.

```
external directory  ->  POST /api/v1/ingestion/suppliers/{id}  ->  PostgreSQL
                                                                      |
                                                            enrichment_jobs
                                                                      |
                                                        worker  ->  Claude  ->  PostgreSQL
```

## Setup

```bash
python -m venv .venv                            # any Python 3.12+
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                            # database, directory and Claude settings
.venv/bin/uvicorn app.main:app --reload         # API on port 8000
.venv/bin/python -m app.workers.enrichment_worker   # background enrichment, separate process
```

The API needs PostgreSQL (`DATABASE_URL`, async driver). `docker compose up` starts Postgres, the
API and the worker together. Without `ANTHROPIC_API_KEY` everything still runs; enrichment jobs
are marked `skipped` instead of calling the model.

Interactive docs are at http://localhost:8000/docs.

## Endpoints

- `POST /api/v1/suppliers` - create a supplier. 409 if its `external_id` is already known.
- `GET /api/v1/suppliers` - list, with `limit`, `offset` and `country`.
- `GET /api/v1/suppliers/{id}` - read one. 404 if there is none.
- `POST /api/v1/ingestion/suppliers/{external_id}` - pull one supplier from the directory. 202,
  because the record is stored but its enrichment has only been queued.
- `GET /health`, `GET /ready` - liveness, and readiness including the database.

## Layout

```
app/
  api/           routers and dependency wiring - the only layer that knows about HTTP
  services/      business rules and transaction boundaries
  repositories/  all SQL for suppliers and for the job queue
  clients/       the external directory and the Claude API, each behind one interface
  models/        SQLAlchemy tables
  schemas/       request and response models
  workers/       the enrichment worker process
```

A request goes API -> service -> repository. Services raise domain errors (`SupplierNotFound`,
`UpstreamUnavailable`); `app/main.py` is the single place that maps those to status codes.
Validation happens in the schemas, before any business code runs.

## Ingestion and enrichment

Ingestion is idempotent: suppliers are matched on `external_id`, so re-running it updates the
existing row instead of creating a second one, and a lost race on insert is resolved as an update.
The supplier row and its enrichment job are committed together, so the queue can never point at a
supplier that was never stored.

Enrichment is a separate process, because a model call takes seconds and no HTTP request should
wait for one. The worker claims jobs with `SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL, so
several workers can share the queue. Claude is asked for structured output and the answer is
validated into a Pydantic model before it reaches the database. Failures that could succeed later
(rate limits, dropped connections) are requeued up to `WORKER_MAX_ATTEMPTS`; a refusal or a bad
request is not retried.

## Tests

```bash
.venv/bin/python -m pytest      # 26 tests, no database or network needed
```

The tests run the real application against SQLite, with the directory and the model replaced by
stubs. They cover the endpoints, normalisation, retry behaviour against the directory, and the
worker's success, skip and retry paths.

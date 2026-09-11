# ADR-002 — Batch Processing: Celery + Redis Worker Fleet

**Status:** Accepted (supersedes ADR-001 Option C)  
**Date:** 2026-09-10  
**Replaces:** ADR-001 § "Option C — Dual-pipeline within FastAPI"

---

## Context

ADR-001 selected Option C (APScheduler within FastAPI) and rejected Option B (Celery + Redis) with the note:

> *"Rejected for v1. Operational overhead: Redis Sentinel or Cluster, Celery beat, worker autoscaling. Adds ~3 moving parts with no additional capability vs. Option C for the current team size."*

After reviewing the full implementation, the decision is revised to **Option B**. The arguments that initially made Option C attractive — single deployable unit, no scheduler process — are outweighed by concrete limitations that surfaced during implementation:

1. **APScheduler inside FastAPI shares process memory.** A crashing worker task could corrupt the API process. Celery workers crash independently.
2. **`asyncio.create_task` is not recoverable.** If the API pod restarts mid-job, the in-memory job state is lost and the task cannot be retried. Celery's `acks_late=True` + `reject_on_worker_lost=True` re-queues interrupted tasks automatically.
3. **No horizontal scaling path.** APScheduler runs one scheduler per process. Celery lets you `--scale worker-batch=N` with zero code changes.
4. **No native retry with backoff.** The APScheduler poller was a `while True` loop. Celery's `self.retry(countdown=N)` releases the worker between polls.
5. **No visibility.** APScheduler has no monitoring UI. Flower provides a real-time task dashboard on port 5555.

The "3 moving parts" objection was accurate but understates the benefit: those 3 parts (Redis Sentinel, Beat, worker fleet) are precisely what make the architecture fault-tolerant at scale.

---

## Decision

Deploy a dedicated Celery worker fleet. The FastAPI process becomes **API-only** — it accepts requests and dispatches tasks. No background threads, no schedulers, no `asyncio.create_task` for batch work.

### Process Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│  redis (DB 0 = cache, DB 1 = broker, DB 2 = result backend)        │
└──────┬──────────────────────────────────────────────────────────────┘
       │ pub/sub + queue
       ├──────────────────────┬──────────────────────┬────────────────┐
       ▼                      ▼                      ▼                ▼
  api (FastAPI)       worker-interactive      worker-batch         beat
  port 8000           queue=interactive       queue=batch       (single)
  HTTP + WS only      concurrency=4           concurrency=8      RedBeat
  2 uvicorn workers   soft_limit=45s          soft_limit=3600s   periodic
  no background work  hard_limit=60s          hard_limit=7200s   tasks

                              │                      │
                              └──────────┬───────────┘
                                         ▼
                                  flower (optional)
                                  port 5555
                                  monitoring UI
```

### Queue Routing

| Queue | Workers | Tasks | SLA |
|---|---|---|---|
| `interactive` | worker-interactive | `process_interactive_recipe` | < 60s hard |
| `batch` | worker-batch (1–N) | `run_bulk_pipeline`, all extraction/adaptation/cart tasks, beat tasks | 24h |

### Task Chain (batch pipeline)

```
run_bulk_pipeline (entry point)
  └─ chord([chunk_chain_1, chunk_chain_2, ...], finalize_bulk_job)
       └─ chunk_chain_n = chain(
            fetch_transcripts_for_chunk
            | submit_extraction_batch       → OpenAI Batch API
            | poll_extraction_batch         → self.retry() every 30–120s
            | submit_adaptation_batch       → OpenAI Batch API
            | poll_adaptation_batch         → self.retry() every 30–120s
            | build_carts_for_chunk
          )
```

**Key: `poll_*` tasks use `self.retry(countdown=N)` not `while True`.** The worker is released between retries and can pick up other tasks. Backoff is `min(30 × 1.5^retries, 120)` seconds.

### Reliability Properties

| Property | Mechanism |
|---|---|
| Task not lost on worker crash | `task_acks_late=True` + `task_reject_on_worker_lost=True` |
| Exactly-once result | Celery result backend (Redis DB 2), 7-day TTL |
| Beat schedule survives restart | RedBeat stores schedule in Redis, not a file |
| Job state survives API restart | `job_store.py` writes all state to Redis hash keys |
| Stale job cleanup | Beat task `reap_stale_jobs` runs hourly, marks stuck IN_PROGRESS as FAILED |
| Cost visibility | Beat task `log_cost_summary` every 6h; structured log → Datadog |

---

## Consequences

**Positive:**
- Worker crash is fully isolated from the API process
- Interrupted batch tasks are automatically re-queued
- Scale batch throughput with `docker compose up --scale worker-batch=N` — no code change
- Flower provides real-time task visibility at `:5555`
- Beat's `reap_stale_jobs` catches any jobs orphaned by unexpected crashes
- RedBeat means Beat can be restarted without losing the periodic schedule

**Negative / Accepted trade-offs:**
- `docker compose up` now starts 5 services instead of 2 (redis, api, worker-interactive, worker-batch, beat). This is acceptable; they are all defined in one compose file.
- Beat **must be a single replica**. `docker compose --scale beat=2` would double-fire every periodic task. The compose file comments this constraint clearly.
- Redis is now both broker and cache. A single Redis failure affects everything. Mitigation: upgrade `REDIS_URL` to a Redis Sentinel or Upstash URL — no code changes required.

---

## Operational Runbook

```bash
# Start full stack (dev)
docker compose up

# Start with Flower monitoring
docker compose --profile monitoring up

# Scale batch workers to 3
docker compose up --scale worker-batch=3

# Inspect task queue depths
docker compose exec redis redis-cli llen batch

# View recent tasks
open http://localhost:5555   # Flower UI

# Force-requeue a stuck task
docker compose exec worker-batch celery -A app.workers.celery_app inspect active

# Drain a queue (e.g. before deploy)
docker compose exec worker-batch celery -A app.workers.celery_app control cancel_consumer batch

# Run a one-off task directly (debug)
docker compose exec worker-batch python -c "
from app.workers.tasks.pipeline import run_bulk_pipeline
run_bulk_pipeline.apply_async(args=['test-job', [...], 'openai', ''])
"
```

---

## Files Changed (vs ADR-001)

| File | Change |
|---|---|
| `app/main.py` | Removed APScheduler lifespan hook; added Celery broker health check |
| `app/workers/celery_app.py` | New — Celery app factory, queue config, routing |
| `app/workers/job_store.py` | New — Redis-backed job state (replaces in-memory `_bulk_jobs` dict) |
| `app/workers/tasks/pipeline.py` | New — `run_bulk_pipeline` chord entry point |
| `app/workers/tasks/extraction.py` | New — `fetch_transcripts_for_chunk` |
| `app/workers/tasks/batch_api.py` | New — `submit/poll_extraction_batch`, `submit/poll_adaptation_batch` |
| `app/workers/tasks/cart.py` | New — `build_carts_for_chunk`, `notify_webhook` |
| `app/workers/beat/schedule.py` | New — `health_check`, `reap_stale_jobs`, `log_cost_summary`, `cleanup_old_results` |
| `app/workers/batch_poller.py` | **Deleted** — replaced by Celery |
| `docker-compose.yml` | Updated — 5 services: redis, api, worker-interactive, worker-batch, beat |
| `worker/Dockerfile` | New — worker image |
| `worker/entrypoint.sh` | New — role-based entrypoint (interactive/batch/beat/flower) |
| `requirements.txt` | Added: `celery[redis]`, `flower`, `kombu`, `redbeat` |

# ADR-004 — Drop the Celery Worker Fleet for a Synchronous Pipeline

**Status:** Accepted (supersedes ADR-002 in full)
**Date:** 2026-09-11
**Supersedes:** [[ADR-002-celery-worker-fleet]]

---

## Context

ADR-002 introduced a Celery + Redis worker fleet to run two things:

1. **Interactive single-recipe extraction** (queue `interactive`) — a user
   pastes a URL and waits for a cart.
2. **Bulk/batch recipe imports** via the OpenAI/Anthropic Batch API (queue
   `batch`) — a chain/chord pipeline processing many recipes asynchronously
   over hours.

The product docs that followed this session — `ARCHITECTURE.md`, `PRD.md` —
describe neither of ADR-002's justifications the way ADR-002 assumed:

- **No bulk/batch import feature exists anywhere in the PRD.** Every feature
  spec (4.1–4.7) is about a single user submitting a single URL and getting a
  cart back. There is no "bulk import" job type in scope for Phase 0–1.
- **The interactive path's own latency budget fits inside one HTTP request.**
  PRD §4.1 and §5 set a P95 cart-build time of **<15 seconds** — extraction +
  nutrition scoring + cart assembly, in one measurement. That's comfortably
  within a single synchronous request/response cycle; it doesn't need a
  worker released between polls the way a Celery task does.
- **`ARCHITECTURE.md` §3 describes a synchronous FastAPI pipeline directly** —
  `services/ai_pipeline.py` calling stage functions in sequence inside the
  request handler, with `API Waterfall` retries handled via `asyncio.sleep`
  rather than task re-queuing.

Once the actual product scope is "one URL in, one cart out, under 15
seconds," the reasons ADR-002 gave for Celery — worker crash isolation,
horizontal `--scale worker-batch=N`, `self.retry(countdown=N)` release
between long polls — stop applying. There's no long-running batch job to
protect a crash from, and no multi-hour poll loop to release a worker during.

## Decision

Drop the Celery worker fleet entirely. FastAPI processes each recipe request
synchronously, in-process, running the 7-stage AI pipeline from
`ARCHITECTURE.md` §3.2 directly inside the request handler.

### What's removed

| Removed | Reason |
|---|---|
| `app/workers/celery_app.py` | No task queue — pipeline runs in-process |
| `app/workers/job_store.py` | Bulk-job status tracking; no bulk jobs exist |
| `app/workers/tasks/pipeline.py`, `batch_api.py`, `extraction.py`, `cart.py` | Celery task definitions for both queues |
| `app/workers/beat/schedule.py` | Periodic maintenance tasks (`reap_stale_jobs`, `log_cost_summary`) only made sense for long-running bulk jobs |
| `batch_router` and `/api/batch/jobs*` endpoints | No bulk-import feature in the PRD |
| `ws_router` and `/ws/jobs/{id}` | Progress streaming isn't needed once processing completes within one request |
| `celery[redis]`, `kombu` from `requirements.txt` | No longer used |

### What's kept

- **Redis** — repurposed as the nutrition-lookup cache `ARCHITECTURE.md` §6's
  infra table calls for (`Upstash Redis — Nutrition lookup cache`), and as a
  lightweight store so a processed recipe can be fetched again by ID for the
  share/reload flows (`recipe.html`, `share.html`) — not as a job queue.
- **The stub services** (`extractor.py`, `adaptor.py`, `cart_builder.py`,
  `openai_batch.py`) — reused as the implementation behind the new
  synchronous pipeline stages, still returning placeholder data per
  [[preplink-backend-stub]] until Phase 0's real extraction/scoring work
  lands.

### New request flow

```
POST /api/recipe/process
    │
    ▼
FastAPI handler (synchronous, in-process)
    │  await extractor.extract_recipe(url)
    │  await adaptor.run_adaptation_pass(...)
    │  await cart_builder.build_instacart_cart(...)
    ▼
Response: { status: "complete", recipe, cart }   ← same request/response
    │
    ▼
recipe_store.save(job_id, recipe, cart)  # Redis, for later GET by id
```

No dispatch, no polling, no WebSocket — the client gets the finished result
in the same HTTP response that started the job.

## Consequences

**Positive:**
- Far less operational surface: no worker processes, no broker, no beat
  scheduler, no Flower. `docker-compose.yml` drops from 5+ services to API +
  Redis.
- Matches the actual PRD scope exactly — no speculative infrastructure for a
  bulk-import feature that isn't being built.
- Simpler client code: `index.html`'s JS goes from "POST, then open a
  WebSocket, then redirect" to "POST, then redirect" — one round trip.

**Negative / accepted trade-offs:**
- If a future phase reintroduces bulk import (there is no roadmap item for
  this currently — `ROADMAP.md`'s Phase 0 explicitly excludes it), the
  Celery fleet would need to be rebuilt rather than resumed. Accepted: it's
  cheaper to rebuild a worker fleet later, once a real bulk feature is
  scoped, than to carry unused infrastructure now.
- The 15-second P95 budget means a slow LLM Waterfall exhaustion (all three
  providers rate-limited) now blocks the request thread instead of hibernating
  a background worker. `ARCHITECTURE.md` §3.3's hibernation logic
  (`await asyncio.sleep(sleep_secs)`) still applies per-request but with no
  requeue — a client whose request times out during hibernation must retry.
  This is an accepted Phase 0 limitation, not solved here.
- Redis is now optional in the sense that nothing breaks catastrophically if
  it's unavailable (cache/recipe-store calls degrade gracefully), which is a
  behavior change from ADR-002 where the batch queue depended on it entirely.

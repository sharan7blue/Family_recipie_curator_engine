# ADR-003 — Production Deploy Pipeline: Six-Gate CI/CD

**Status:** Accepted (documents intent; see "Implementation Status" below for what's wired up vs. stubbed)
**Date:** 2026-09-11
**Depends on:** [[ADR-002-celery-worker-fleet]] (backend deploy target is the API + Celery worker fleet described there)

---

## Context

PrepLink serves parents making health/safety decisions for infants and children (age-adapted recipes, allergy/dietary filtering). A bad deploy isn't just downtime — a regression in the safety-rule engine or an inaccessible UI has real consequences for the people using it. The pipeline is designed around that: correctness and accessibility are hard gates; performance/SEO are advisory.

Two workflows split the work:

- **`ci.yml`** — runs Gate 1 on every PR, fast feedback before merge.
- **`production.yml`** — runs all six gates in sequence on every merge to `main`. Each gate must pass before the next starts; a failure stops the pipeline before it reaches deploy.

---

## Decision — The Six Gates

| Gate | What | Blocks merge/deploy on |
|---|---|---|
| 1 | **Full test suite** — Ruff lint, TypeScript strict check, Pydantic schema imports, all 10 nutrition safety rule tests, pytest, frontend build | Any failure |
| 2 | **Security audit** — Bandit (Python), `npm audit` (Node) | Bandit HIGH severity, npm `critical` severity only. Lower severities are reported but non-blocking. |
| 3 | **Lighthouse baseline** — runs against the built frontend | `categories:accessibility < 0.85` only. Performance/SEO scores are warnings surfaced in the PR/run comment, not blockers. |
| 4 | **Deploy frontend → Vercel production** | Deploy failure |
| 5 | **Deploy backend → Fly.io production** (API + Celery workers) | Deploy failure |
| 6 | **Smoke tests** — `GET /health` on the live API, `GET /` on the live frontend expects 200 | Either check failing flags the deploy immediately. On success, a `production_deploy` event is sent to PostHog (commit SHA, actor, timestamp) so deploys can be correlated with analytics spikes/drops. |

### Why accessibility is the one hard UI gate

Performance and SEO regressions are recoverable and don't block anyone from using the app. An accessibility regression can mean a parent using a screen reader can't get through the allergy-safety flow — that's treated the same severity class as a failing safety-rule test, not as a nice-to-have.

### Why Fly.io for the backend (Gate 5)

Fly.io was chosen over Railway for the API + Celery worker fleet:

- **Cost:** free for 3 shared VMs — enough to run the API and one worker at no cost; additional VMs are ~$1.94/month each, so scaling `worker-batch` stays cheap.
- **Docker-native:** the fleet is already defined as Docker services in `docker-compose.yml` (ADR-002) — Fly deploys those images directly, no translation layer.
- **Multi-process app:** Fly's `[processes]` in `fly.toml` maps cleanly onto the api / worker-interactive / worker-batch / beat topology from ADR-002, each scaled independently.
- **Global edge + fast deploys:** deploys land in ~30 seconds, and edge placement matters for the interactive recipe pipeline's latency budget (soft limit 45s, hard limit 60s).
- **Redis:** moves to Upstash (free tier, 10k commands/day) rather than a self-hosted Fly Redis app, since Upstash is serverless-billed and needs no capacity planning at this scale.

### Why Bandit/npm audit only fail on the top severity

Flagging every MEDIUM/LOW finding as a merge-blocker trains people to bypass the gate. Restricting the hard fail to HIGH (Bandit `-lll`) / `critical` (`npm audit --audit-level=critical`) keeps the gate meaningful — when it's red, it's red for a real reason — while lower-severity findings still surface in CI output for triage.

---

## Implementation Status

This ADR was written against the current state of the repo, which does **not yet have**:
- a `frontend/` directory (TypeScript check, frontend build, and Lighthouse gates have nothing to run against yet)
- a `tests/` suite, including the "10 nutrition safety rule tests" referenced in Gate 1
- a `fly.toml` / Fly app, or Vercel / PostHog projects, or any of their secrets configured in this GitHub repo

`.github/workflows/ci.yml` and `production.yml` are scaffolded to match this design, but steps that depend on the above **detect their target is missing and emit a `::warning::` annotation instead of hard-failing**, so CI stays green during early development instead of permanently red. Each such step is marked `# TODO(gate-N):` in the workflow file. As each piece lands (frontend app, safety-rule test suite, deploy secrets), remove the corresponding guard so the gate becomes a real hard gate as designed here.

Required GitHub Actions secrets once deploy gates go live:

| Secret | Used by |
|---|---|
| `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | Gate 4 |
| `FLY_API_TOKEN` | Gate 5 |
| `PRODUCTION_API_URL`, `PRODUCTION_FRONTEND_URL` | Gate 6 |
| `POSTHOG_API_KEY`, `POSTHOG_HOST` | Gate 6 |

---

## Consequences

**Positive:**
- A merge to `main` either fully ships (all 6 gates green) or stops cleanly before touching production — no partial deploys.
- Accessibility can't silently regress; nutrition-safety logic can't silently regress.
- PostHog correlation on every deploy makes "did the last deploy cause this metric shift" a 30-second lookup instead of a guess.

**Negative / accepted trade-offs:**
- Six sequential gates add latency to every merge vs. a single "deploy on green" step. Accepted because the two things gated hardest (safety rules, accessibility) are exactly the two categories where a regression reaching production is unacceptable.
- Until the guarded steps are un-stubbed (see Implementation Status), the pipeline doesn't yet enforce what it documents. Treat a green `production.yml` run today as "the parts that exist are fine," not "all six gates meaningfully passed."

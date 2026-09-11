"""
PrepLink Celery Beat Schedule
================================
Periodic tasks run by `celery beat`. These are maintenance and monitoring tasks
that do NOT need to run on-demand.

Tasks defined here:
  health_check          every 60s   — ping Redis and log worker count
  reap_stale_jobs       every 1h    — mark timed-out IN_PROGRESS jobs as FAILED
  log_cost_summary      every 6h    — emit cost metrics to logger (→ Datadog/CloudWatch)
  cleanup_old_results   every 24h   — expire Celery results older than 7 days

Beat runs as a separate container (see docker-compose.yml) using
Redis as its schedule store (no file-based schedule.db needed).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from celery.utils.log import get_task_logger
from celery.schedules import crontab

from app.workers.celery_app import celery_app
from app.schemas.batch import BatchJobStatus

logger = get_task_logger(__name__)


# ─── Beat schedule ────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    "health-check-60s": {
        "task":     "app.workers.beat.schedule.health_check",
        "schedule": 60.0,
        "options":  {"queue": "batch", "expires": 55},
    },
    "reap-stale-jobs-1h": {
        "task":     "app.workers.beat.schedule.reap_stale_jobs",
        "schedule": crontab(minute=0),          # top of every hour
        "options":  {"queue": "batch", "expires": 3500},
    },
    "log-cost-summary-6h": {
        "task":     "app.workers.beat.schedule.log_cost_summary",
        "schedule": crontab(minute=0, hour="*/6"),
        "options":  {"queue": "batch", "expires": 21000},
    },
    "cleanup-old-results-daily": {
        "task":     "app.workers.beat.schedule.cleanup_old_results",
        "schedule": crontab(minute=0, hour=3),   # 3 AM UTC
        "options":  {"queue": "batch", "expires": 82800},
    },
}


# ─── Task implementations ─────────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.beat.schedule.health_check",
    queue="batch",
    ignore_result=True,
)
def health_check():
    """Ping Redis and log a heartbeat. Alerts if Redis is unreachable."""
    import redis as _redis
    from app.core.config import settings
    try:
        r = _redis.from_url(settings.REDIS_CACHE_URL, socket_timeout=3)
        r.ping()
        logger.info("[BEAT] health_check: Redis OK")
    except Exception as e:
        logger.error(f"[BEAT] health_check: Redis UNREACHABLE — {e}")


@celery_app.task(
    name="app.workers.beat.schedule.reap_stale_jobs",
    queue="batch",
    ignore_result=True,
)
def reap_stale_jobs():
    """
    Mark IN_PROGRESS bulk jobs as FAILED if they've been running for more
    than STALE_THRESHOLD_HOURS. Guards against worker crashes that left a job
    in IN_PROGRESS state without a watchdog.
    """
    from app.workers import job_store
    STALE_THRESHOLD_HOURS = 25    # Slightly more than 24h batch SLA

    jobs = job_store.list_jobs(limit=500)
    reaped = 0
    for job in jobs:
        if job.get("status") != BatchJobStatus.IN_PROGRESS.value:
            continue
        started_at = job.get("started_at", "")
        if not started_at:
            continue
        try:
            started = datetime.fromisoformat(started_at)
            age_hours = (datetime.now(timezone.utc) - started).total_seconds() / 3600
            if age_hours > STALE_THRESHOLD_HOURS:
                job_store.set_status(job["bulk_job_id"], BatchJobStatus.FAILED)
                logger.warning(
                    f"[BEAT] Reaped stale job {job['bulk_job_id']} "
                    f"(running {age_hours:.1f}h)"
                )
                reaped += 1
        except Exception as e:
            logger.error(f"[BEAT] Error reaping job {job.get('bulk_job_id')}: {e}")

    if reaped:
        logger.info(f"[BEAT] Reaped {reaped} stale jobs")


@celery_app.task(
    name="app.workers.beat.schedule.log_cost_summary",
    queue="batch",
    ignore_result=True,
)
def log_cost_summary():
    """
    Compute and log aggregate cost metrics from the Redis job store.
    In production, emit as structured metrics to Datadog/CloudWatch.
    """
    from app.workers import job_store
    from app.schemas.batch import estimate_cost

    jobs = job_store.list_jobs(limit=1000)
    total_input  = 0
    total_output = 0
    job_count    = 0

    for job in jobs:
        # Only count jobs from the last 6h
        created_at = job.get("created_at", "")
        try:
            created = datetime.fromisoformat(created_at)
            if (datetime.now(timezone.utc) - created) > timedelta(hours=6):
                continue
        except Exception:
            continue

        import redis as _redis
        from app.core.config import settings
        r = _redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
        inp  = int(r.hget(f"bulk_job:{job['bulk_job_id']}", "input_tokens") or 0)
        out  = int(r.hget(f"bulk_job:{job['bulk_job_id']}", "output_tokens") or 0)
        total_input  += inp
        total_output += out
        job_count    += 1

    cost = estimate_cost(total_input, total_output, "gpt-4o-2024-08-06", is_batch=True)
    logger.info(
        f"[BEAT] Cost summary (last 6h): "
        f"jobs={job_count} "
        f"input_tokens={total_input:,} "
        f"output_tokens={total_output:,} "
        f"cost_usd=${cost:.4f}"
    )


@celery_app.task(
    name="app.workers.beat.schedule.cleanup_old_results",
    queue="batch",
    ignore_result=True,
)
def cleanup_old_results():
    """
    Force-expire any bulk_job Redis keys older than 7 days that may have
    slipped through normal TTL management (e.g. keys set before TTL was added).
    """
    import redis as _redis
    from app.core.config import settings

    r   = _redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
    ttl = settings.BULK_JOB_TTL_SECONDS
    count = 0

    for key in r.scan_iter("bulk_job:*"):
        if r.ttl(key) == -1:          # No expiry set
            r.expire(key, ttl)
            count += 1

    if count:
        logger.info(f"[BEAT] Set TTL on {count} keys missing expiry")

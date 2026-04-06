"""
Job persistence and lifecycle logic.

All functions accept a psycopg connection so callers control
transaction boundaries.  This module must not import from
api/, web/, cli/, mcp/, or workers/.
"""

import json
from datetime import datetime, timezone


def enqueue(conn, job_type, payload=None, max_attempts=3, available_at=None):
    """Insert a new job and return its id."""
    row = conn.execute(
        """INSERT INTO jobs (job_type, payload_json, max_attempts, available_at)
           VALUES (%s, %s, %s, COALESCE(%s, NOW()))
           RETURNING id""",
        (job_type, json.dumps(payload or {}), max_attempts, available_at),
    ).fetchone()
    return row["id"]


def claim_next(conn, job_types=None):
    """Atomically claim the next available job.

    Uses FOR UPDATE SKIP LOCKED so multiple workers never grab the
    same row.  Returns the job dict or None.
    """
    type_filter = ""
    params = []
    if job_types:
        placeholders = ", ".join(["%s"] * len(job_types))
        type_filter = f"AND job_type IN ({placeholders})"
        params.extend(job_types)

    row = conn.execute(
        f"""UPDATE jobs
            SET status = 'running',
                locked_at = NOW(),
                attempt_count = attempt_count + 1,
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM jobs
                WHERE status = 'queued'
                  AND available_at <= NOW()
                  {type_filter}
                ORDER BY available_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, job_type, payload_json, attempt_count, max_attempts""",
        params,
    ).fetchone()
    conn.commit()
    return row


def mark_succeeded(conn, job_id):
    """Mark a job as succeeded."""
    conn.execute(
        """UPDATE jobs
           SET status = 'succeeded', updated_at = NOW()
           WHERE id = %s""",
        (job_id,),
    )
    conn.commit()


def mark_failed(conn, job_id, error, attempt_count, max_attempts):
    """Mark a job as failed or re-queue it for retry.

    If attempts remain, the job goes back to 'queued' with an
    exponential backoff delay.  Otherwise it stays 'failed'.
    """
    if attempt_count < max_attempts:
        delay_seconds = min(2 ** attempt_count * 5, 300)
        conn.execute(
            """UPDATE jobs
               SET status = 'queued',
                   last_error = %s,
                   available_at = NOW() + make_interval(secs => %s),
                   locked_at = NULL,
                   updated_at = NOW()
               WHERE id = %s""",
            (error, delay_seconds, job_id),
        )
    else:
        conn.execute(
            """UPDATE jobs
               SET status = 'failed',
                   last_error = %s,
                   locked_at = NULL,
                   updated_at = NOW()
               WHERE id = %s""",
            (error, job_id),
        )
    conn.commit()


def get_job(conn, job_id):
    """Fetch a single job by id."""
    return conn.execute(
        """SELECT id, job_type, payload_json, status,
                  attempt_count, max_attempts, available_at,
                  locked_at, last_error, created_at, updated_at
           FROM jobs WHERE id = %s""",
        (job_id,),
    ).fetchone()


def get_failed_jobs(conn, limit=50):
    """Return the most recent failed jobs for inspection."""
    return conn.execute(
        """SELECT id, job_type, payload_json, attempt_count, max_attempts,
                  last_error, created_at, updated_at
           FROM jobs WHERE status = 'failed'
           ORDER BY updated_at DESC
           LIMIT %s""",
        (limit,),
    ).fetchall()


def has_pending_job(conn, job_type, payload):
    """Check if a queued or running job with identical type+payload exists.

    Used for idempotency: callers should check before enqueuing
    duplicate work.
    """
    row = conn.execute(
        """SELECT 1 FROM jobs
           WHERE job_type = %s
             AND payload_json = %s
             AND status IN ('queued', 'running')
           LIMIT 1""",
        (job_type, json.dumps(payload or {})),
    ).fetchone()
    return row is not None


def enqueue_unique(conn, job_type, payload=None, max_attempts=3, available_at=None):
    """Enqueue a job only if no queued/running duplicate exists.

    Returns the job id if enqueued, or None if a duplicate was found.
    """
    if has_pending_job(conn, job_type, payload):
        return None
    return enqueue(conn, job_type, payload, max_attempts, available_at)

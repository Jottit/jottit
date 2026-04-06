"""
Background job worker.

Polls the jobs table, claims available work, and dispatches to
handlers registered in core/job_handlers.py.

Run standalone:  python -m workers.job_worker
"""

import logging
import os
import signal
import sys
import time
import traceback

# Ensure project root is importable when run as a module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.job_handlers import get_handler
from core.jobs import claim_next, mark_failed, mark_succeeded
from db import get_db, init_db, run_migrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

POLL_INTERVAL = float(os.environ.get("WORKER_POLL_INTERVAL", "2"))
SHUTDOWN = False


def _handle_signal(signum, frame):
    global SHUTDOWN
    log.info("Received signal %s, shutting down after current job", signum)
    SHUTDOWN = True


def process_one():
    """Try to claim and execute one job.  Returns True if a job was processed."""
    with get_db() as conn:
        job = claim_next(conn)

    if job is None:
        return False

    job_id = job["id"]
    job_type = job["job_type"]
    payload = job["payload_json"]
    attempt = job["attempt_count"]
    max_attempts = job["max_attempts"]

    handler = get_handler(job_type)
    if handler is None:
        log.error("No handler for job type %r (job %s)", job_type, job_id)
        with get_db() as conn:
            mark_failed(conn, job_id, f"Unknown job type: {job_type}", attempt, max_attempts)
        return True

    log.info("Processing job %s type=%s attempt=%s/%s", job_id, job_type, attempt, max_attempts)
    try:
        with get_db() as conn:
            handler(conn, payload)
        with get_db() as conn:
            mark_succeeded(conn, job_id)
        log.info("Job %s succeeded", job_id)
    except Exception:
        error = traceback.format_exc()
        log.error("Job %s failed:\n%s", job_id, error)
        with get_db() as conn:
            mark_failed(conn, job_id, error, attempt, max_attempts)

    return True


def run_loop():
    """Main worker loop.  Polls until SHUTDOWN is set."""
    log.info("Worker starting, poll interval=%.1fs", POLL_INTERVAL)
    while not SHUTDOWN:
        try:
            did_work = process_one()
        except Exception:
            log.exception("Unexpected error in worker loop")
            did_work = False

        if not did_work:
            time.sleep(POLL_INTERVAL)

    log.info("Worker stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    init_db()
    run_migrations()
    run_loop()

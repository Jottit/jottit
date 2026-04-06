import json
import time

from core.job_handlers import get_handler
from core.jobs import (
    claim_next,
    enqueue,
    enqueue_unique,
    get_failed_jobs,
    get_job,
    has_pending_job,
    mark_failed,
    mark_succeeded,
)
from db import enqueue_publish_job, get_db, save_page
from workers.job_worker import process_one


# --- Enqueue ---


def test_enqueue_creates_queued_job():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", {"key": "value"})
        conn.commit()

    with get_db() as conn:
        job = get_job(conn, job_id)

    assert job is not None
    assert job["job_type"] == "test_job"
    assert job["payload_json"] == {"key": "value"}
    assert job["status"] == "queued"
    assert job["attempt_count"] == 0
    assert job["max_attempts"] == 3


def test_enqueue_custom_max_attempts():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", max_attempts=5)
        conn.commit()

    with get_db() as conn:
        job = get_job(conn, job_id)

    assert job["max_attempts"] == 5


def test_enqueue_with_available_at():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", available_at="2099-01-01T00:00:00Z")
        conn.commit()

    with get_db() as conn:
        job = get_job(conn, job_id)

    assert job["status"] == "queued"
    # Should not be claimable since available_at is in the future
    with get_db() as conn:
        claimed = claim_next(conn)
    assert claimed is None


# --- Claim ---


def test_claim_next_returns_job():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", {"x": 1})
        conn.commit()

    with get_db() as conn:
        job = claim_next(conn)

    assert job is not None
    assert job["id"] == job_id
    assert job["job_type"] == "test_job"
    assert job["payload_json"] == {"x": 1}
    assert job["attempt_count"] == 1


def test_claim_next_returns_none_when_empty():
    with get_db() as conn:
        job = claim_next(conn)
    assert job is None


def test_claim_sets_running_status():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job")
        conn.commit()

    with get_db() as conn:
        claim_next(conn)

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "running"
    assert job["locked_at"] is not None


def test_claim_skips_running_jobs():
    with get_db() as conn:
        enqueue(conn, "test_job", {"first": True})
        enqueue(conn, "test_job", {"second": True})
        conn.commit()

    with get_db() as conn:
        first = claim_next(conn)
    with get_db() as conn:
        second = claim_next(conn)

    assert first["payload_json"]["first"] is True
    assert second["payload_json"]["second"] is True


def test_claim_filters_by_job_type():
    with get_db() as conn:
        enqueue(conn, "type_a", {"a": True})
        enqueue(conn, "type_b", {"b": True})
        conn.commit()

    with get_db() as conn:
        job = claim_next(conn, job_types=["type_b"])

    assert job["job_type"] == "type_b"
    assert job["payload_json"]["b"] is True


# --- Success ---


def test_mark_succeeded():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job")
        conn.commit()

    with get_db() as conn:
        claim_next(conn)

    with get_db() as conn:
        mark_succeeded(conn, job_id)

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "succeeded"


# --- Failure and retries ---


def test_mark_failed_requeues_when_attempts_remain():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", max_attempts=3)
        conn.commit()

    with get_db() as conn:
        claim_next(conn)

    with get_db() as conn:
        mark_failed(conn, job_id, "something broke", attempt_count=1, max_attempts=3)

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "queued"
    assert job["last_error"] == "something broke"
    assert job["locked_at"] is None


def test_mark_failed_permanent_at_max_attempts():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", max_attempts=2)
        conn.commit()

    with get_db() as conn:
        claim_next(conn)

    with get_db() as conn:
        mark_failed(conn, job_id, "still broken", attempt_count=2, max_attempts=2)

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "failed"
    assert job["last_error"] == "still broken"


def test_failed_jobs_are_inspectable():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", max_attempts=1)
        conn.commit()

    with get_db() as conn:
        claim_next(conn)

    with get_db() as conn:
        mark_failed(conn, job_id, "total failure", attempt_count=1, max_attempts=1)

    with get_db() as conn:
        failed = get_failed_jobs(conn)
    assert len(failed) == 1
    assert failed[0]["id"] == job_id
    assert failed[0]["last_error"] == "total failure"


def test_retry_increments_attempt_count():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", max_attempts=3)
        conn.commit()

    # First attempt
    with get_db() as conn:
        job = claim_next(conn)
    assert job["attempt_count"] == 1

    # Fail and re-queue
    with get_db() as conn:
        mark_failed(conn, job_id, "error1", attempt_count=1, max_attempts=3)

    # Make the job available now (override the backoff delay)
    with get_db() as conn:
        conn.execute("UPDATE jobs SET available_at = NOW() WHERE id = %s", (job_id,))
        conn.commit()

    # Second attempt
    with get_db() as conn:
        job = claim_next(conn)
    assert job is not None
    assert job["attempt_count"] == 2


def test_retries_stop_at_max_attempts():
    with get_db() as conn:
        job_id = enqueue(conn, "test_job", max_attempts=2)
        conn.commit()

    # Attempt 1
    with get_db() as conn:
        claim_next(conn)
    with get_db() as conn:
        mark_failed(conn, job_id, "err", attempt_count=1, max_attempts=2)
    with get_db() as conn:
        conn.execute("UPDATE jobs SET available_at = NOW() WHERE id = %s", (job_id,))
        conn.commit()

    # Attempt 2
    with get_db() as conn:
        claim_next(conn)
    with get_db() as conn:
        mark_failed(conn, job_id, "err again", attempt_count=2, max_attempts=2)

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "failed"
    assert job["attempt_count"] == 2


# --- Idempotency ---


def test_has_pending_job():
    with get_db() as conn:
        enqueue(conn, "test_job", {"page_id": 42})
        conn.commit()

    with get_db() as conn:
        assert has_pending_job(conn, "test_job", {"page_id": 42}) is True
        assert has_pending_job(conn, "test_job", {"page_id": 99}) is False
        assert has_pending_job(conn, "other_job", {"page_id": 42}) is False


def test_enqueue_unique_prevents_duplicates():
    with get_db() as conn:
        first = enqueue_unique(conn, "test_job", {"key": 1})
        conn.commit()

    with get_db() as conn:
        second = enqueue_unique(conn, "test_job", {"key": 1})
        conn.commit()

    assert first is not None
    assert second is None


def test_enqueue_unique_allows_different_payloads():
    with get_db() as conn:
        first = enqueue_unique(conn, "test_job", {"key": 1})
        conn.commit()

    with get_db() as conn:
        second = enqueue_unique(conn, "test_job", {"key": 2})
        conn.commit()

    assert first is not None
    assert second is not None


def test_enqueue_unique_allows_after_success():
    with get_db() as conn:
        job_id = enqueue_unique(conn, "test_job", {"key": 1})
        conn.commit()

    with get_db() as conn:
        claim_next(conn)
    with get_db() as conn:
        mark_succeeded(conn, job_id)

    with get_db() as conn:
        second = enqueue_unique(conn, "test_job", {"key": 1})
        conn.commit()

    assert second is not None


# --- Worker process_one ---


def test_worker_processes_job():
    with get_db() as conn:
        job_id = enqueue(conn, "page_published", {"page_id": 999, "slug": "test"})
        conn.commit()

    did_work = process_one()
    assert did_work is True

    with get_db() as conn:
        job = get_job(conn, job_id)
    # page_published handler will log a warning (page doesn't exist) but succeed
    assert job["status"] == "succeeded"


def test_worker_returns_false_when_no_jobs():
    did_work = process_one()
    assert did_work is False


def test_worker_handles_unknown_job_type():
    with get_db() as conn:
        job_id = enqueue(conn, "totally_unknown_type", max_attempts=1)
        conn.commit()

    did_work = process_one()
    assert did_work is True

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["status"] == "failed"
    assert "Unknown job type" in job["last_error"]


def test_worker_retries_failing_handler():
    # Register a handler that always fails (temporarily via monkeypatch)
    import core.job_handlers as handlers

    original = handlers.HANDLERS.copy()

    def bad_handler(conn, payload):
        raise RuntimeError("boom")

    handlers.HANDLERS["exploding"] = bad_handler
    try:
        with get_db() as conn:
            job_id = enqueue(conn, "exploding", max_attempts=2)
            conn.commit()

        process_one()

        with get_db() as conn:
            job = get_job(conn, job_id)
        assert job["status"] == "queued"
        assert "boom" in job["last_error"]
        assert job["attempt_count"] == 1
    finally:
        handlers.HANDLERS = original


# --- Integration: enqueue_publish_job ---


def test_enqueue_publish_job_creates_job():
    slug = save_page("test-page", "# Test\n\nContent", "listed")

    job_id = enqueue_publish_job(slug)
    assert job_id is not None

    with get_db() as conn:
        job = get_job(conn, job_id)
    assert job["job_type"] == "page_published"
    assert job["payload_json"]["slug"] == slug


def test_enqueue_publish_job_is_idempotent():
    slug = save_page("test-page", "# Test\n\nContent", "listed")

    first = enqueue_publish_job(slug)
    second = enqueue_publish_job(slug)

    assert first is not None
    assert second is None


def test_enqueue_publish_job_nonexistent_page():
    result = enqueue_publish_job("no-such-page")
    assert result is None


# --- Handler registry ---


def test_handler_registry():
    assert get_handler("page_published") is not None
    assert get_handler("publish_notification") is not None
    assert get_handler("nonexistent") is None

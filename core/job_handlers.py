"""
Job handler registry.

Each handler is a plain function that receives (conn, payload)
and does its work.  Handlers should call shared services rather
than reimplementing business logic.

This module must not import from api/, web/, cli/, mcp/, or workers/.
"""

import logging

log = logging.getLogger(__name__)


def handle_publish_notification(conn, payload):
    """Placeholder for publish notification delivery.

    In Phase 6 this will send email/archive notifications to
    subscribers when a page is published or updated.  For now
    it just logs the intent so the pipeline is exercisable end-to-end.
    """
    page_id = payload.get("page_id")
    slug = payload.get("slug")
    log.info("publish_notification: page_id=%s slug=%s (no-op placeholder)", page_id, slug)


def handle_page_published(conn, payload):
    """React to a page being published or updated.

    This is the fan-out point: future phases will enqueue
    subscriber-specific delivery jobs from here.  For now
    it validates the payload and returns.
    """
    page_id = payload.get("page_id")
    if page_id is None:
        raise ValueError("page_published job missing page_id")

    row = conn.execute(
        "SELECT id, slug, visibility FROM pages WHERE id = %s",
        (page_id,),
    ).fetchone()
    if row is None:
        log.warning("page_published: page %s no longer exists, skipping", page_id)
        return

    log.info("page_published: page_id=%s slug=%s visibility=%s",
             row["id"], row["slug"], row["visibility"])


# Registry: job_type -> handler function
HANDLERS = {
    "publish_notification": handle_publish_notification,
    "page_published": handle_page_published,
}


def get_handler(job_type):
    """Look up the handler for a job type.  Returns None if unknown."""
    return HANDLERS.get(job_type)

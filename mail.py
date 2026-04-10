import logging
import os

import resend

resend.api_key = os.environ.get("RESEND_API_KEY")

logger = logging.getLogger(__name__)


def send_verification_email(email, code):
    if not resend.api_key:
        print(f"[DEV] Verification code for {email}: {code}")
        return

    try:
        resend.Emails.send(
            {
                "from": "Jottit <noreply@jottit.org>",
                "to": email,
                "subject": "Your Jottit verification code",
                "text": f"Your Jottit verification code is: {code}\n\nThis code expires in 10 minutes.",
            }
        )
    except Exception:
        logger.exception("Failed to send verification email to %s", email)
        raise


def send_comment_notification(author_email, page_url, commenter_name, comment_body):
    if not resend.api_key:
        print(
            f"[DEV] Comment notification for {author_email}: {commenter_name} commented on {page_url}"
        )
        return

    display_name = commenter_name or "Someone"
    preview = comment_body[:200] + ("..." if len(comment_body) > 200 else "")

    try:
        resend.Emails.send(
            {
                "from": "Jottit <noreply@jottit.org>",
                "to": author_email,
                "subject": f"{display_name} commented on your Jottit page",
                "text": f"{display_name} left a comment on your page:\n\n{preview}\n\nView it at: {page_url}",
            }
        )
    except Exception:
        logger.exception("Failed to send comment notification to %s", author_email)

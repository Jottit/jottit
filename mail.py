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

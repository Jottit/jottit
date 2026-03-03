import os

import resend

resend.api_key = os.environ.get("RESEND_API_KEY")


def send_verification_email(email, code):
    if not resend.api_key:
        print(f"[DEV] Verification code for {email}: {code}")
        return

    resend.Emails.send(
        {
            "from": "Jottit <noreply@jottit.org>",
            "to": email,
            "subject": "Your Jottit verification code",
            "text": f"Your Jottit verification code is: {code}\n\nThis code expires in 10 minutes.",
        }
    )

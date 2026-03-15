import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _otp_expiration_minutes():
    seconds = max(int(getattr(settings, "OTP_EXPIRATION_SECONDS", 300)), 60)
    return max(seconds // 60, 1)


def send_otp_email(email: str, otp_value: str):
    subject = getattr(
        settings,
        "OTP_EMAIL_SUBJECT",
        "Votre code OTP Christlumen",
    )
    message = (
        "Bonjour,\n\n"
        f"Votre code de confirmation Christlumen est : {otp_value}\n\n"
        f"Ce code expire dans {_otp_expiration_minutes()} minute(s).\n"
        "Si vous n'etes pas a l'origine de cette demande, ignorez ce message.\n"
    )

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Email OTP failed for %s", email)
        return {
            "status": "error",
            "message": "Service email indisponible",
            "status_code": 502,
            "details": str(exc),
        }

    if sent_count < 1:
        return {
            "status": "error",
            "message": "Email OTP non envoye",
            "status_code": 502,
        }

    return {"status": "success", "delivery": "email"}

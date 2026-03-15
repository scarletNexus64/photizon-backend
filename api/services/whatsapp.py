import random
import requests
from django.utils import timezone
from django.conf import settings
import logging
import re
from api.models import OTP

logger = logging.getLogger(__name__)


def _get_whatsapp_phone_id():
    return (
        getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
        or getattr(settings, "META_PHONE_ID", "")
    )


def _get_whatsapp_access_token():
    return (
        getattr(settings, "WHATSAPP_API_TOKEN", "")
        or getattr(settings, "META_WA_TOKEN", "")
        or getattr(settings, "META_WHATSAPP_API_KEY", "")
    )


def _get_template_name():
    return getattr(settings, "WHATSAPP_TEMPLATE_NAME", "") or "hello_world"


def _get_otp_template_name():
    return (
        getattr(settings, "WHATSAPP_OTP_TEMPLATE_NAME", "")
        or getattr(settings, "WHATSAPP_TEMPLATE_NAME", "")
    )


def _get_template_language():
    language = getattr(settings, "WHATSAPP_LANGUAGE", "") or "en_US"
    if "_" in language:
        return language
    if language.lower() == "fr":
        return "fr_FR"
    if language.lower() == "en":
        return "en_US"
    return language


def _otp_expiration_minutes():
    seconds = max(int(getattr(settings, "OTP_EXPIRATION_SECONDS", 300)), 60)
    return max(seconds // 60, 1)


def _build_otp_payload(phone, otp_value):
    normalized_to = re.sub(r"\D", "", phone)
    template_name = _get_otp_template_name()

    if template_name:
        return {
            "messaging_product": "whatsapp",
            "to": normalized_to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": _get_template_language()},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": otp_value}],
                    }
                ],
            },
        }

    return {
        "messaging_product": "whatsapp",
        "to": normalized_to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": (
                f"Votre code Christlumen est {otp_value}. "
                f"Il expire dans {_otp_expiration_minutes()} minute(s)."
            ),
        },
    }

def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_whatsapp(phone, otp_value=None):
    otp_entry, created = OTP.objects.get_or_create(phone=phone)

    # Anti spam (cooldown)
    if not otp_entry.can_resend() and not created:
        return {
            "status": "error",
            "message": "Attendez quelques secondes avant de renvoyer un OTP",
            "status_code": 429,
        }

    otp_value = otp_value or generate_otp()
    otp_entry.otp = otp_value
    otp_entry.last_sent_at = timezone.now()
    otp_entry.save()

    whatsapp_enabled = getattr(settings, "WHATSAPP_ENABLED", False)
    whatsapp_phone_id = _get_whatsapp_phone_id()
    whatsapp_access_token = _get_whatsapp_access_token()

    # In local development, keep a debug fallback when WhatsApp is not configured.
    if not whatsapp_enabled or not whatsapp_access_token or not whatsapp_phone_id:
        logger.info("OTP debug for %s => %s", phone, otp_value)
        return {
            "status": "success",
            "delivery": "debug",
            "debug_otp": otp_value,
            "otp": otp_value,
        }

    # Requête API Meta WhatsApp
    url = f"https://graph.facebook.com/v22.0/{whatsapp_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_access_token}",
        "Content-Type": "application/json"
    }

    payload = _build_otp_payload(phone, otp_value)

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code >= 400:
            return {
                "status": "error",
                "message": "Erreur WhatsApp",
                "status_code": 502,
                "details": res.text,
                "otp": otp_value,
            }
        return {"status": "success", "delivery": "whatsapp", "otp": otp_value}
    except requests.RequestException:
        return {
            "status": "error",
            "message": "Service WhatsApp indisponible",
            "status_code": 502,
            "otp": otp_value,
        }


def verify_otp(phone, otp):
    try:
        otp_entry = OTP.objects.get(phone=phone)
    except OTP.DoesNotExist:
        return {"status": "error", "message": "OTP non trouvé"}

    if otp_entry.is_expired():
        return {"status": "error", "message": "OTP expiré"}

    if otp_entry.otp != otp:
        return {"status": "error", "message": "OTP incorrect"}

    # Si tout est bon
    otp_entry.delete()
    return {"status": "success"}




def send_whatsapp_template(to_phone: str, template_name: str, parameters: list, language="fr_FR"):
    """
    Send a template message. parameters is list of strings (text parameters).
    Returns dict (response json) or raises request exception.
    """

    whatsapp_phone_id = _get_whatsapp_phone_id()
    whatsapp_access_token = _get_whatsapp_access_token()

    if not whatsapp_phone_id or not whatsapp_access_token:
        raise requests.RequestException("WhatsApp configuration missing")

    url = f"https://graph.facebook.com/v22.0/{whatsapp_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language.split("_")[0] + "_" + language.split("_")[-1]},
        }
    }

    # Build components for template body parameters
    components = []
    if parameters:
        components = [{
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in parameters]
        }]
    
    payload["template"]["components"] = components

    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

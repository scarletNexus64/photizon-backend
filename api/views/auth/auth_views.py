from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from datetime import timedelta
import re
from rest_framework_simplejwt.tokens import RefreshToken
from api.models import Church, Subscription, SubscriptionPlan, User, OTP, Payment
from api.serializers import SubscriptionSerializer, SubscriptionPlanSerializer, UserSerializer
from api.services.email import send_otp_email
from api.services.whatsapp import send_otp_whatsapp
from api.permissions import IsAuthenticatedUser, IsSuperAdmin, is_church_admin
from rest_framework.decorators import api_view, permission_classes, authentication_classes

from api.services.notify import create_and_send_whatsapp_notification
from api.services.notification_preferences import create_in_app_notification


def _normalize_phone(raw_phone):
    if raw_phone is None:
        return ""

    text = str(raw_phone).strip()
    # Si le numéro commence par +, on garde le + et on ne garde que les chiffres restants
    if text.startswith("+"):
        return "+" + re.sub(r"\D", "", text)
    
    # Si le numéro commence par 00, on remplace par +
    if text.startswith("00"):
        return "+" + re.sub(r"\D", "", text[2:])

    # Sinon, on ne garde que les chiffres. Si le numéro est long (> 10 chiffres), 
    # on suppose que c'est un numéro international sans le +
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
        
    if len(digits) > 10:
        return f"+{digits}"
    
    return digits # Numéro local ou incomplet, on ne force pas le + qui serait faux (ex: +06...)


def _normalize_email(raw_email):
    if raw_email is None:
        return ""

    email = str(raw_email).strip().lower()
    if not email:
        return ""

    validate_email(email)
    return email


@api_view(["POST"])
@authentication_classes([])
def send_otp_view(request):
    phone = _normalize_phone(request.data.get("phone"))
    try:
        email = _normalize_email(request.data.get("email"))
    except ValidationError:
        return Response({"error": "Email invalide"}, status=400)

    if not phone:
        return Response({"error": "Le numéro est requis"}, status=400)

    whatsapp_result = send_otp_whatsapp(phone)
    if whatsapp_result.get("status") == "error" and not whatsapp_result.get("otp"):
        return Response(
            {"error": whatsapp_result.get("message", "Impossible d'envoyer le code OTP")},
            status=whatsapp_result.get("status_code", status.HTTP_400_BAD_REQUEST),
        )

    channels = []
    failed_channels = {}
    debug_otp = whatsapp_result.get("debug_otp")
    otp_value = whatsapp_result.get("otp")

    if whatsapp_result.get("status") == "success":
        if whatsapp_result.get("delivery") == "whatsapp":
            channels.append("whatsapp")
    else:
        failed_channels["whatsapp"] = whatsapp_result.get("message", "Erreur WhatsApp")

    if email:
        email_result = send_otp_email(email, otp_value)
        if email_result.get("status") == "success":
            channels.append("email")
        else:
            failed_channels["email"] = email_result.get("message", "Erreur email")

    if not channels and not debug_otp:
        error_message = failed_channels.get("whatsapp") or failed_channels.get("email") or "Impossible d'envoyer le code OTP"
        return Response(
            {"error": error_message, "failed_channels": failed_channels},
            status=502,
        )

    payload = {
        "message": "OTP envoye",
        "phone": phone,
        "channels": channels,
    }
    if email:
        payload["email"] = email
    if failed_channels:
        payload["failed_channels"] = failed_channels
    if debug_otp:
        payload["debug_otp"] = debug_otp
    return Response(payload, status=200)

@api_view(["POST"])
@authentication_classes([])
def verify_otp_view(request):
    phone = _normalize_phone(request.data.get("phone"))
    code = re.sub(r"\D", "", str(request.data.get("code", "")))
    try:
        email = _normalize_email(request.data.get("email"))
    except ValidationError:
        return Response({"error": "Email invalide"}, status=400)

    if not phone or not code:
        return Response({"error": "phone et code obligatoires"}, status=400)
    if len(code) != 6:
        return Response({"error": "Le code OTP doit contenir 6 chiffres"}, status=400)

    # 1. Vérification OTP
    try:
        otp_obj = OTP.objects.get(phone=phone, otp=code)
    except OTP.DoesNotExist:
        return Response({"error": "OTP incorrect"}, status=400)

    if otp_obj.is_expired():
        return Response({"error": "OTP expiré"}, status=400)
    

    # 2. Récupérer / créer l'utilisateur
    user, created = User.objects.get_or_create(
        phone_number=phone,
    )
    if created:
        create_in_app_notification(
            user=user,
            title="Bienvenue sur Christlumen",
            message="Bienvenue sur Christlumen ! Entrez le code de votre eglise pour acceder aux contenus de votre communaute et rester connecte a votre famille d'eglise.",
            notif_type="SUCCESS",
            category="general",
        )
        create_and_send_whatsapp_notification(
        user=user,
        title_eng="Welcome to Christlumen",
        title="Bienvenue sur Christlumen",
        message="Bienvenue sur Christlumen ! Entrez le code de votre eglise pour acceder aux contenus de votre communaute.",
        message_eng="Welcome to Christlumen! Enter your church code to access your community content and stay connected with your church family.",
        template_name="welcome_message",  # Nom du template WhatsApp que tu as créé sur Meta
        template_params=[user.phone_number]  # Paramètres dynamiques si nécessaire
        )
    if email and not User.objects.filter(email=email).exclude(id=user.id).exists():
        user.email = email
        user.save(update_fields=["email", "updated_at"])
    # 3. Générer le token JWT (access + refresh)
    refresh = RefreshToken.for_user(user)

    # 4. Supprimer l'OTP après succès
    otp_obj.delete()

    # 5. Retour
    return Response({
        "success": True,
        "is_new_user": created,
        "user": UserSerializer(user).data,
        "access": str(refresh.access_token),
        "refresh": str(refresh)
    }, status=200)


def _user_can_manage_subscription(user, church):
    return user.role == "SADMIN" or is_church_admin(user, church)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def get_church_subscription(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)

    sub = getattr(church, "subscription", None)
    if not sub:
        return Response({"detail": "No subscription"}, status=404)
   
    return Response(SubscriptionSerializer(sub).data)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser, IsSuperAdmin])
def create_subscription(request):
    church_id = request.data.get("church_id")
    plan = request.data.get("plan", "FREE")
    expires_at = request.data.get("expires_at")

    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    if hasattr(church, "subscription"):
        return Response({"detail": "Subscription already exists"}, status=400)

    sub = Subscription.objects.create(
        church=church,
        plan=plan,
        expires_at=expires_at
    )

    if plan and plan != "FREE":
        amount = sub.get_plan_price()
        Payment.objects.create(
            user=request.user,
            church=church,
            order=None,
            donation=None,
            amount=amount,
            currency="XAF",
            gateway=request.data.get("gateway", "MOMO"),
            gateway_transaction_id=request.data.get("gateway_transaction_id"),
            status="SUCCESS",
            metadata={"created_via": "create_subscription", "plan": plan},
            processed_by=request.user if getattr(request.user, "is_staff", False) else None,
        )

    return Response(SubscriptionSerializer(sub).data, status=201)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser])
def update_subscription(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)

    # Vérifier si la subscription existe ou la créer
    sub, created = Subscription.objects.get_or_create(
        church=church,
        defaults={
            "expires_at": timezone.now() + timedelta(days=30)
        }
    )

    # Si l'utilisateur n'envoie pas expires_at → définir une valeur par défaut
    data = request.data.copy()

    if "expires_at" not in data or not data.get("expires_at"):
        # seulement si c'est une mise à jour partielle
        if not sub.expires_at:
            data["expires_at"] = (timezone.now() + timedelta(days=30)).isoformat()

    serializer = SubscriptionSerializer(sub, data=data, partial=True)

    if serializer.is_valid():
        serializer.save()
        if created and serializer.instance.plan and serializer.instance.plan != "FREE":
            amount = serializer.instance.get_plan_price()
            Payment.objects.create(
                user=request.user,
                church=church,
                amount=amount,
                currency="XAF",
                gateway=request.data.get("gateway", "MOMO"),
                gateway_transaction_id=request.data.get("gateway_transaction_id"),
                status="SUCCESS",
                metadata={"created_via": "update_subscription_auto_create", "plan": serializer.instance.plan},
                processed_by=request.user if getattr(request.user, "is_staff", False) else None,
            )
        return Response({
            "created": created,      # True = subscription auto-créée
            "subscription": serializer.data
        })

    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_subscription(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)
    sub = getattr(church, "subscription", None)

    if not sub:
        return Response({"detail": "No subscription"}, status=404)

    sub.delete()
    return Response({"detail": "Subscription deleted"})

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def change_subscription_plan(request, church_id):
    plan = request.data.get("plan")
    if plan not in ["FREE", "STARTER", "PRO", "PREMIUM"]:
        return Response({"error": "Invalid plan"}, status=400)

    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)
    sub = church.subscription

    # Mettre à jour le plan
    sub.plan = plan

    # Mettre à jour expire_at => maintenant + 1 mois
    sub.expires_at = timezone.now() + timedelta(days=30)

    sub.save()

    if plan and plan != "FREE":
        amount = sub.get_plan_price()
        Payment.objects.create(
            user=request.user,
            church=church,
            amount=amount,
            currency="XAF",
            gateway=request.data.get("gateway", "MOMO"),
            gateway_transaction_id=request.data.get("gateway_transaction_id"),
            status="SUCCESS",
            metadata={"created_via": "change_subscription_plan", "plan": plan},
            processed_by=request.user if getattr(request.user, "is_staff", False) else None,
        )
    return Response({
        "detail": f"Plan updated to {plan}",
        "expire_at": sub.expires_at,
        "expires_at": sub.expires_at,
    })

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def toggle_subscription_status(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)
    sub = church.subscription

    sub.is_active = not sub.is_active
    sub.save()

    return Response({"active": sub.is_active})

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def renew_subscription(request, church_id):
    months = int(request.data.get("months", 1))
    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)
    sub = church.subscription
 
    # extend expiry date
    if sub.expires_at:
        sub.expires_at += timezone.timedelta(days=30 * months)
    else:
        sub.expires_at = timezone.now() + timezone.timedelta(days=30 * months)
    sub.is_active = True

    sub.save()

    if sub.plan and sub.plan != "FREE":
        unit = sub.get_plan_price()
        total = unit * months
        Payment.objects.create(
            user=request.user,
            church=church,
            amount=total,
            currency="XAF",
            gateway=request.data.get("gateway", "MOMO"),
            gateway_transaction_id=request.data.get("gateway_transaction_id"),
            status="SUCCESS",
            metadata={"created_via": "renew_subscription", "plan": sub.plan, "months": months},
            processed_by=request.user if getattr(request.user, "is_staff", False) else None,
        )

    return Response({"detail": "Subscription renewed", "expires_at": sub.expires_at})

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def check_subscription_status(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not _user_can_manage_subscription(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)

    sub = church.subscription

    if not sub:
        return Response({"status": "none"})

    now = timezone.now()
    status_value = "active" if sub.is_active and (not sub.expires_at or sub.expires_at > now) else "expired"

    return Response({
        "plan": sub.plan,
        "status": status_value,
        "expires_at": sub.expires_at
    })
@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_subscriptions(request):
    qs = Subscription.objects.select_related("church").order_by("-started_at")
    return Response(SubscriptionSerializer(qs, many=True).data)

@api_view(["GET"])
@authentication_classes([])
def list_subscription_plans(request):
    """Liste tous les plans de souscription actifs (accessible sans authentification)"""
    qs = SubscriptionPlan.objects.filter(is_active=True).order_by("order", "price")
    return Response(SubscriptionPlanSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def get_subscription_plan(request, plan_id):
    """Récupère les détails d'un plan de souscription"""
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    return Response(SubscriptionPlanSerializer(plan).data)

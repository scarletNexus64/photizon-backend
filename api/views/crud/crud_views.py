from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from api.models import Church,ChurchAdmin, ChurchCommission, Deny,Subscription,User
from api.serializers import ChurchAdminSerializer, OwnerSerializer,SubChurchCreateSerializer,ChurchCreateSerializer, MemberSerializer,SubscriptionSerializer,ChurchSerializer, ChurchUpdateSerializer, UserMeSerializer, UserSelfUpdateSerializer, UserSerializer
from api.permissions import IsAuthenticatedUser, IsSuperAdmin, user_is_church_admin, user_is_church_owner
from rest_framework import status
from django.db.models import Count
from django.db.models import Q
from api.services.notify import create_and_send_whatsapp_notification
from django.utils.text import slugify
from django.db import transaction
from django.core.files.storage import default_storage

from api.utils import can_join_church

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def create_church_view(request):
    serializer = ChurchCreateSerializer(data=request.data)
    user = request.user
    user.refresh_from_db()
    if serializer.is_valid():
        # save church without owner FK; ownership is created via ChurchAdmin
        church = serializer.save()
        # add owner as ChurchAdmin (OWNER role)
        ChurchAdmin.objects.create(church=church, user=request.user, role="OWNER")
        # create free subscription
        Subscription.objects.create(church=church, plan="FREE", is_active=True)
        create_and_send_whatsapp_notification(
        user=request.user,
        title="Eglise Créée Avec Succès",
        title_eng="Church created successfully",
        message="Votre église a été créée avec succès. Merci de procéder à la certification et de compléter les informations nécessaires afin d’activer l’accès à l’enregistrement et à la publication de contenu.",
        message_eng="Your church has been created successfully! To unlock all features, please verify your church and complete its information. You will then be able to publish content",
        template_name="welcome_message",  # Nom du template WhatsApp que tu as créé sur Meta
        template_params=[]  # Paramètres dynamiques si nécessaire
        )
        if hasattr(user, "current_church"):
            user.current_church = church
            user.save(update_fields=["current_church"])
        return Response(ChurchSerializer(church).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def create_subchurch_view(request, church_id):
    parent_church = get_object_or_404(Church, id=church_id)
    if not getattr(parent_church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    serializer = SubChurchCreateSerializer(data=request.data)
    user = request.user
    user.refresh_from_db()

    if serializer.is_valid():
        # injecter le parent ICI !!!
        church = serializer.save(parent=parent_church)

        # add owner as ChurchAdmin (OWNER role)
        ChurchAdmin.objects.create(church=church, user=user, role="OWNER")

        # create free subscription
        Subscription.objects.create(church=church, plan="FREE", is_active=True)

        create_and_send_whatsapp_notification(
            user=user,
            title="Eglise Créée Avec Succès",
            title_eng="Church created successfully",
            message=(
                "Votre église a été créée avec succès. "
                "Merci de procéder à la certification et de compléter les informations nécessaires "
                "afin d’activer l’accès à l’enregistrement et à la publication de contenu."
            ),
            message_eng=(
                "Your church has been created successfully! To unlock all features, "
                "please verify your church and complete its information. "
                "You will then be able to publish content"
            ),
            template_name="welcome_message",
            template_params=[]
        )

        # update current_church
        if hasattr(user, "current_church"):
            user.current_church = church
            user.save(update_fields=["current_church"])

        return Response(ChurchSerializer(church).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_my_churches(request):
    # Return churches where the user is OWNER/ADMIN recorded in ChurchAdmin
    qs = Church.objects.filter(admins__user=request.user).distinct()
    serializer = ChurchSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def retrieve_church(request, church_id):
    church = get_object_or_404(Church, id=church_id)

    has_access = (
        request.user.role == "SADMIN"
        or request.user.current_church_id == church.id
        or ChurchAdmin.objects.filter(user=request.user, church=church).exists()
        or church.is_public
    )
    if not has_access:
        return Response({"detail": "Forbidden"}, status=403)

    return Response(ChurchSerializer(church).data)

@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def verify_church_view(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    action = request.data.get("action")
    if action == "APPROVE":
        church.status = "APPROVED"
        church.is_verified = True
        church.activated_at = timezone.now()
        church.save()
        # create notification to owner (in-app + whatsapp)
        from api.services.notify import create_and_send_whatsapp_notification
        # Notify all owners recorded in ChurchAdmin (not the Church.owner field)
        owner_entries = ChurchAdmin.objects.filter(church=church, role="OWNER")
        for entry in owner_entries:
            create_and_send_whatsapp_notification(entry.user, "Église approuvée", f"Votre église {church.title} a été approuvée.", template_name="church_approved", template_params=[church.title])
        return Response({"status":"ok","message":"approved"})
    elif action == "REJECT":
        church.status = "REJECTED"
        church.is_verified = False
        church.save()
        return Response({"status":"ok","message":"rejected"})
    return Response({"error":"invalid action"}, status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def add_church_admin(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    # only existing church owner (via ChurchAdmin) or SADMIN can add admins
    if not user_is_church_owner(request.user, church):
        return Response({"error":"Not allowed"}, status=403)
    user_id = request.data.get("user_id")
    role = request.data.get("role","ADMIN")
    # get user
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error":"user not found"}, status=404)
    # Prevent assigning a role to a user who has been banned from this church
    if Deny.objects.filter(user=user, church=church).exists():
        return Response({"detail": "User is banned from this church."}, status=403)

    if user.current_church_id != church.id:
        return Response(
            {"error": "User must join the church before receiving a role."},
            status=400
        )
    ca, created = ChurchAdmin.objects.get_or_create(church=church, user=user, defaults={"role":role})
    if not created:
        ca.role = role
        ca.save()
    return Response(ChurchAdminSerializer(ca).data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_sub_churches(request, church_id):
    parent = get_object_or_404(Church, id=church_id)
    if not getattr(parent, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    subs = parent.sub_churches.all()
    serializer = ChurchSerializer(subs, many=True)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def list_users(request):
    users = User.objects.all()
    serializer = UserSerializer(users, many=True)
    return Response(serializer.data)

@api_view(["PUT", "PATCH"])
@permission_classes([IsSuperAdmin])
def update_church(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    serializer = ChurchUpdateSerializer(church, data=request.data, partial=True)

    if serializer.is_valid():
        updated = serializer.save()
        return Response(ChurchSerializer(updated).data)

    return Response(serializer.errors, status=400)



@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser])
def update_self(request):
    user = request.user
    data = request.data.copy()

    if "picture" in request.FILES:
        uploaded_file = request.FILES["picture"]
        file_name = default_storage.save(
            f"profiles/{user.id}_{uploaded_file.name}",
            uploaded_file,
        )
        data["picture_url"] = request.build_absolute_uri(default_storage.url(file_name))

    serializer = UserSelfUpdateSerializer(user, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(UserSerializer(user).data)
    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_self(request):
    user = request.user
    user.delete()
    return Response({"detail": "Your account has been deleted"})

@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def list_churches(request):
    churches = Church.objects.all()
    serializer = ChurchSerializer(churches, many=True)
    return Response(serializer.data)


# 
@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def list_owners(request):
    owners = User.objects.filter(church_roles__role="OWNER").distinct()
    serializer = OwnerSerializer(owners, many=True)
    return Response(serializer.data)

@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_church(request, church_id):
    church = get_object_or_404(Church, id=church_id)

    if not user_is_church_owner(request.user, church):
        return Response(
            {"detail": "You are not allowed to delete this church."},
            status=403
        )

    church.delete()
    return Response({"detail": "Church deleted successfully"})

@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser])
def update_church_by_owner(request, church_id):

    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    # 🔥 Vérifier que l'utilisateur est OWNER via ChurchAdmin
    is_owner = ChurchAdmin.objects.filter(
        church=church,
        user=request.user,
        role="OWNER"
    ).exists()

    if not is_owner:
        return Response(
            {"detail": "You are not allowed to update this church."},
            status=403
        )

    serializer = ChurchUpdateSerializer(church, data=request.data, partial=True)

    if serializer.is_valid():
        updated_church = serializer.save()
        return Response(ChurchSerializer(updated_church).data)

    return Response(serializer.errors, status=400)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def me(request):
    serializer = UserMeSerializer(request.user)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def churches_metrics(request):
    user = request.user
    if user.role != "SADMIN":
        return Response({"detail": "Unauthorized"}, status=403)

    total_churches = Church.objects.count()
    approved_churches = Church.objects.filter(status="APPROVED").count()
    pending_churches = Church.objects.filter(status="PENDING").count()
    rejected_churches = Church.objects.filter(status="REJECTED").count()

    total_users = User.objects.count()

    members_by_month = (
        User.objects
        .extra(select={'month': "strftime('%%m', created_at)"})
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    top_churches = (
        Church.objects
        .annotate(members_c=Count("members"))
        .order_by("-members_c")[:10]
        .values("id", "title", "members_c")
    )

    return Response({
        "stats": {
            "total_churches": total_churches,
            "approved_churches": approved_churches,
            "pending_churches": pending_churches,
            "rejected_churches": rejected_churches,
            "total_users": total_users,
            "members_by_month": list(members_by_month),
            "top_churches": list(top_churches),
        }
    })

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def get_user_by_id(request, user_id):
    """Récupère les informations publiques d'un utilisateur par son ID"""
    user_obj = get_object_or_404(User, id=user_id)
    # On utilise UserMeSerializer pour avoir les rôles et l'église actuelle
    return Response(UserMeSerializer(user_obj).data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def get_current_user(request):
    serializer = UserMeSerializer(request.user)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def filter_church_members(request, church_id):
    # Paramètres
    admin_role = request.GET.get("admin_role")
    commission_role = request.GET.get("commission_role")
    commission_id = request.GET.get("commission_id")
    search = request.GET.get("search")

    # Tous les membres de l’église
    qs = User.objects.filter(current_church_id=church_id)

    # Recherche nom / téléphone
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone_number__icontains=search)
        )

    # Filtre par rôle ChurchAdmin
    # → related_name = "church_roles"
    if admin_role:
        qs = qs.filter(
            church_roles__church_id=church_id,
            church_roles__role=admin_role
        ).distinct()

    # Filtre par rôle Commission
    # → related_name = "church_commissions"
    if commission_role or commission_id:
        commission_filter = Q(church_commissions__church_id=church_id)

        if commission_role:
            commission_filter &= Q(church_commissions__role=commission_role)

        if commission_id:
            commission_filter &= Q(church_commissions__commission_id=commission_id)

        qs = qs.filter(commission_filter).distinct()

    return Response(UserMeSerializer(qs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def join_church(request, church_code):
    church = get_object_or_404(Church, code=church_code)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    user = request.user
    can_join, msg = can_join_church(user, church)
    if not can_join:
        return Response({"detail": msg}, status=403)
    # Déjà membre ?
    if user.current_church_id == church.id:
        return Response({"detail": "You are already a member of this church."}, status=400)

    # Lier l'utilisateur à l'église via current_church
    user.current_church = church
    user.save(update_fields=["current_church"])

    return Response({
        "detail": "You joined the church.",
        "church_code": church.code
    })
@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def leave_church(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    user = request.user

    # Vérifier qu'il est membre
    if user.current_church_id != church.id:
        return Response({"detail": "You are not a member of this church."}, status=status.HTTP_400_BAD_REQUEST)

    # Récupérer l'entrée ChurchAdmin (si existe)
    membership = ChurchAdmin.objects.filter(church=church, user=user).first()

    # Si l'utilisateur n'a pas de rôle ChurchAdmin -> simple départ
    if membership is None:
        user.current_church = None
        user.save(update_fields=["current_church", "updated_at"])
        return Response({"detail": "You have left the church."})

    # Si ce n'est pas un OWNER -> on peut partir normalement
    if membership.role != "OWNER":
        with transaction.atomic():
            # supprimer tout rôle éventuel (admin/mod)
            ChurchAdmin.objects.filter(church=church, user=user).delete()
            user.current_church = None
            user.save(update_fields=["current_church", "updated_at"])
        return Response({"detail": "You have left the church."})

    # C'est un OWNER -> vérifier s'il existe d'autres owners
    owners_count = ChurchAdmin.objects.filter(church=church, role="OWNER").exclude(user=user).count()

    if owners_count < 1:
        # aucun autre owner — on empêche le départ pour éviter église sans owner
        return Response(
            {"detail": "Cannot leave: you are the only owner. Transfer ownership before leaving."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Il y a au moins un autre owner -> autoriser le départ
    with transaction.atomic():
        # supprimer tous les rôles pour cet utilisateur sur cette église
        ChurchAdmin.objects.filter(church=church, user=user).delete()
        # détacher current_church
        user.current_church = None
        user.save(update_fields=["current_church", "updated_at"])

    return Response({"detail": "Owner left the church (another owner exists)."})
@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def deny_user(request, church_id, user_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    user = request.user  # l'admin qui fait l'action

    # Vérifier si admin ou owner
    if not ChurchAdmin.objects.filter(church=church, user=user, role__in=["OWNER", "ADMIN"]).exists() and user.role != "SADMIN":
        return Response({"detail": "Not allowed."}, status=403)

    target_user = get_object_or_404(User, id=user_id)

    # Ne pas permettre de bannir quelqu'un qui n'appartient pas à l'église
    is_member = (target_user.current_church_id == church.id)
    has_role = ChurchAdmin.objects.filter(church=church, user=target_user).exists()
    if not (is_member or has_role) and user.role != "SADMIN":
        return Response({"detail": "User is not a member of this church."}, status=400)

    # Empêcher de bannir le dernier OWNER de l'église
    owner_count_excluding_target = ChurchAdmin.objects.filter(church=church, role="OWNER").exclude(user=target_user).count()
    is_target_owner = ChurchAdmin.objects.filter(church=church, user=target_user, role="OWNER").exists()
    if is_target_owner and owner_count_excluding_target < 1:
        return Response({"detail": "Cannot ban the only owner. Transfer ownership first."}, status=status.HTTP_403_FORBIDDEN)

    # Supprimer du current_church si nécessaire
    if target_user.current_church_id == church.id:
        target_user.current_church = None
        target_user.save(update_fields=["current_church", "updated_at"])

    # Supprimer les rôles admin/modérateur
    ChurchAdmin.objects.filter(church=church, user=target_user).delete()

    # Créer l'entrée Deny
    deny, created = Deny.objects.get_or_create(user=target_user, church=church, defaults={"reason": request.data.get("reason", "")})
    if not created:
        deny.reason = request.data.get("reason", "")
        deny.save()

    return Response({"detail": f"{target_user.phone_number} has been banned from {church.title}."})
@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def unban_user(request, church_id, user_id):
    """
    Débannir un utilisateur d'une église.
    Seuls les admins/owners de l'église ou SADMIN peuvent le faire.
    """
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    admin_user = request.user

    # Vérifier si admin ou owner
    if not ChurchAdmin.objects.filter(church=church, user=admin_user, role__in=["OWNER", "ADMIN"]).exists() and admin_user.role != "SADMIN":
        return Response({"detail": "Not allowed."}, status=403)

    # Récupérer l'utilisateur à débannir
    from django.contrib.auth import get_user_model
    User = get_user_model()
    target_user = get_object_or_404(User, id=user_id)

    # Supprimer l'entrée Deny
    Deny.objects.filter(user=target_user, church=church).delete()

    # Restaurer le current_church si il est vide
    if target_user.current_church is None:
        target_user.current_church = church
        target_user.save(update_fields=["current_church", "updated_at"]) 

    return Response({"detail": f"{target_user.phone_number} has been unbanned from {church.title}."})

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def leave_commission(request, church_id, commission_id):
    user = request.user

    # Vérifier si l'utilisateur appartient à la bonne église
    if str(user.current_church_id) != str(church_id):
        return Response({"detail": "Vous n'appartenez pas à cette église."}, status=400)

    # Supprimer le lien dans les commissions
    deleted, _ = ChurchCommission.objects.filter(
        user=user,
        church_id=church_id,
        commission_id=commission_id
    ).delete()

    if deleted == 0:
        return Response({"detail": "Vous ne faites pas partie de cette commission."}, status=404)

    return Response({"detail": "Vous avez quitté la commission avec succès."})

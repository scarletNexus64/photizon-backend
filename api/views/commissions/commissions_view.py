from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from api.models import Church,ChurchAdmin, ChurchCommission, Commission,Subscription,User
from api.serializers import ChurchAdminSerializer, ChurchCommissionSerializer, ChurchCreateSerializer, CommissionSerializer, MemberSerializer,SubscriptionSerializer,ChurchSerializer, UserMeSerializer, UserSerializer, CommissionWithMembersSerializer
from api.permissions import IsAuthenticatedUser, IsSuperAdmin, is_church_admin, user_is_church_admin, user_is_church_owner
from rest_framework import status
from django.db.models import Count

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser, IsSuperAdmin])
def create_commission(request):
    serializer = CommissionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_commissions(request):
    commissions = Commission.objects.all()
    serializer = CommissionSerializer(commissions, many=True)
    return Response(serializer.data)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser, IsSuperAdmin])
def update_commission(request, commission_id):
    commission = get_object_or_404(Commission, id=commission_id)
    serializer = CommissionSerializer(commission, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser, IsSuperAdmin])
def delete_commission(request, commission_id):
    commission = get_object_or_404(Commission, id=commission_id)
    commission.delete()
    return Response({"detail": "Commission deleted successfully"})

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def add_member_to_church_commission(request, church_id, commission_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    
    # vérifier si le request.user est OWNER ou ADMIN de cette église
    if not is_church_admin(request.user, church):
        return Response({"detail": "You are not allowed."}, status=403)

    commission = get_object_or_404(Commission, id=commission_id)

    user_id = request.data.get("user_id")
    role = request.data.get("role", "MEMBER")

    user = get_object_or_404(User, id=user_id)

    # vérifier que l'utilisateur est bien membre de l'église
    if user.current_church_id != church.id:
        return Response({"detail": "User is not a member of this church."}, status=400)

    link, created = ChurchCommission.objects.get_or_create(
        church=church,
        commission=commission,
        user=user,
        defaults={"role": role}
    )

    if not created:
        return Response({"detail": "User already in this commission."}, status=400)

    serializer = ChurchCommissionSerializer(link)
    return Response(serializer.data, status=201)



@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_church_commissions(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    commissions = ChurchCommission.objects.filter(church=church).select_related("commission")

    serializer = ChurchCommissionSerializer(commissions, many=True)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def church_commissions_summary(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)

    commissions = ChurchCommission.objects.filter(church=church)

    data = {
        "total_commissions": commissions.values("commission").distinct().count(),
        "total_members": commissions.count(),
        "commissions": CommissionSerializer(
            Commission.objects.filter(
                id__in=commissions.values_list("commission_id", flat=True).distinct()
            ),
            many=True
        ).data
    }

    return Response(data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_church_commission_members(request, church_id, commission_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    commission = get_object_or_404(Commission, id=commission_id)
    # Return the commission with its members nested (users with their roles)
    serializer = CommissionWithMembersSerializer(commission, context={"church_id": church.id})
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def add_member_to_commission(request, church_id, commission_id):
    church = get_object_or_404(Church, id=church_id)
    commission = get_object_or_404(Commission, id=commission_id)

    # Check permissions
    if not user_is_church_admin(request.user, church):
        return Response({"detail": "Permission denied"}, status=403)

    user_id = request.data.get("user_id")
    user = get_object_or_404(User, id=user_id)

    obj, created = ChurchCommission.objects.get_or_create(
        church=church,
        commission=commission,
        user=user,
        defaults={"role": request.data.get("role", "MEMBER")}
    )

    serializer = ChurchCommissionSerializer(obj)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def join_commission(request, church_id, commission_id):
    church = get_object_or_404(Church, id=church_id)
    commission = get_object_or_404(Commission, id=commission_id)

    if str(request.user.current_church_id) != str(church.id) and request.user.role != "SADMIN":
        return Response({"detail": "You must belong to this church."}, status=403)

    obj, created = ChurchCommission.objects.get_or_create(
        church=church,
        commission=commission,
        user=request.user,
        defaults={"role": "MEMBER"},
    )

    serializer = ChurchCommissionSerializer(obj)
    return Response(serializer.data, status=201 if created else 200)

@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def remove_member_from_commission(request, church_id, commission_id, user_id):
    church = get_object_or_404(Church, id=church_id)
    commission = get_object_or_404(Commission, id=commission_id)

    if not user_is_church_admin(request.user, church):
        return Response({"detail": "Permission denied"}, status=403)

    obj = get_object_or_404(
        ChurchCommission,
        church=church,
        commission=commission,
        user_id=user_id
    )

    obj.delete()
    return Response({"detail": "Member removed"})

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def update_member_role_in_commission(request, church_id, commission_id, user_id):
    church = get_object_or_404(Church, id=church_id)
    commission = get_object_or_404(Commission, id=commission_id)

    if not user_is_church_admin(request.user, church):
        return Response({"detail": "Permission denied"}, status=403)

    obj = get_object_or_404(
        ChurchCommission,
        church=church,
        commission=commission,
        user_id=user_id
    )

    new_role = request.data.get("role")
    if not new_role:
        return Response({"detail": "Missing role"}, status=400)

    obj.role = new_role
    obj.save()

    serializer = ChurchCommissionSerializer(obj)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_church_commissions_with_members(request, church_id):
    church = get_object_or_404(Church, id=church_id)

    # toutes les associations commission <-> church
    if not user_is_church_owner(request.user, church):
        return Response({"detail": "Permission denied"}, status=403)
    links = (
        ChurchCommission.objects
        .filter(church=church)
        .select_related("commission", "user")
        .order_by("commission__name")
    )

    # Regrouper par commission
    commissions_map = {}

    for link in links:
        cid = link.commission.id

        if cid not in commissions_map:
            commissions_map[cid] = {
                "commission": {
                    "id": link.commission.id,
                    "name": link.commission.name,
                    "logo": link.commission.logo,
                },
                "members": []
            }

        commissions_map[cid]["members"].append({
            "id": link.user.id,
            "name": link.user.name,
            "phone_number": link.user.phone_number,
            "picture_url": link.user.picture_url,
            "role": link.role,
        })

    # convertir en liste
    result = list(commissions_map.values())

    return Response(result)

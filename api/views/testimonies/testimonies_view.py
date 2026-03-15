from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q, Sum
from api.models import Testimony, Church, User, TestimonyLike, Notification
from api.serializers import (
    TestimonySerializer,
    TestimonyCreateSerializer,
    TestimonyUpdateSerializer,
    TestimonyListSerializer,
    TestimonyApprovalSerializer,
    TestimonyLikeSerializer
)
from api.permissions import IsTestimonyOwner
from api.services.notification_preferences import create_in_app_notification


def _build_testimony_notification_meta(testimony, *, action, actor=None, extra=None):
    meta = {
        "testimony_id": str(testimony.id),
        "testimony_title": testimony.title,
        "church_id": str(testimony.church_id),
        "interaction_type": action,
        "target_type": "TESTIMONY",
    }
    if actor is not None:
        meta["actor_id"] = str(actor.id)
        meta["actor_name"] = actor.name
    if extra:
        meta.update(extra)
    return meta


def _notify_testimony_owner(
    testimony,
    *,
    title,
    message,
    action,
    actor=None,
    allow_self=False,
    extra=None,
):
    owner = testimony.user
    if owner is None:
        return
    if actor is not None and owner.id == actor.id and not allow_self:
        return

    create_in_app_notification(
        user=owner,
        title=title,
        message=message,
        notif_type="INFO",
        category="social",
        meta=_build_testimony_notification_meta(
            testimony,
            action=action,
            actor=actor,
            extra=extra,
        ),
    )


# =====================================================
# Create Testimony
# =====================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_testimony(request, church_id):
    """
    Create a new testimony (text or audio)
    Body: {
        "type": "TEXT" or "AUDIO",
        "title": "string",
        "text_content": "string (for TEXT type)",
        "audio_url": "URL (for AUDIO type)",
        "duration": number (for AUDIO type in seconds),
        "is_public": boolean
    }
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is a member of the church
    if request.user.current_church_id != church.id and request.user.role != "SADMIN":
        return Response(
            {"error": "You must be a member of this church to create a testimony"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = TestimonyCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    testimony = Testimony.objects.create(
        church=church,
        user=request.user,
        **serializer.validated_data
    )
    
    return Response(
        TestimonySerializer(testimony).data,
        status=status.HTTP_201_CREATED
    )


# =====================================================
# Update Testimony
# =====================================================

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_testimony(request, church_id, testimony_id):
    """
    Update a testimony (only the owner or church admin can update)
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is the testimony owner
    if testimony.user != request.user and request.user.role != "SADMIN":
        return Response(
            {"error": "You can only update your own testimonies"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Can't update if already approved
    if testimony.status == "APPROVED":
        return Response(
            {"error": "Cannot update an approved testimony"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = TestimonyUpdateSerializer(testimony, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    
    return Response(TestimonySerializer(testimony).data)


# =====================================================
# Delete Testimony
# =====================================================

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_testimony(request, church_id, testimony_id):
    """
    Delete a testimony (owner, church admin, or SADMIN can delete)
    """
    from api.permissions import is_church_admin
    
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user can delete: owner, church admin, or SADMIN
    is_owner = testimony.user == request.user
    is_admin = is_church_admin(request.user, church)
    is_superadmin = request.user.role == "SADMIN"
    
    if not (is_owner or is_admin or is_superadmin):
        return Response(
            {"error": "Only the testimony owner or church admin can delete this testimony"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    testimony.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# =====================================================
# Retrieve Testimony
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def retrieve_testimony(request, church_id, testimony_id):
    """
    Retrieve a single testimony
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check visibility
    if request.user.role != "SADMIN":
        if testimony.status != "APPROVED" and testimony.user != request.user:
            return Response(
                {"error": "This testimony is not yet approved"},
                status=status.HTTP_403_FORBIDDEN
            )
    
    serializer = TestimonySerializer(testimony, context={"request": request})
    return Response(serializer.data)


# =====================================================
# List Testimonies for a Church
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_church_testimonies(request, church_id):
    """
    List all approved public testimonies for a church
    Query params:
    - type: TEXT, AUDIO
    - limit: number of results (default: 20)
    - offset: pagination offset (default: 0)
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get testimonies
    qs = Testimony.objects.filter(
        church=church,
        status="APPROVED",
        is_public=True
    )
    
    # Filter by type if provided
    testimony_type = request.query_params.get('type')
    if testimony_type in ['TEXT', 'AUDIO']:
        qs = qs.filter(type=testimony_type)
    
    # Pagination
    limit = int(request.query_params.get('limit', 20))
    offset = int(request.query_params.get('offset', 0))
    
    total_count = qs.count()
    testimonies = qs[offset:offset + limit]
    
    serializer = TestimonyListSerializer(
        testimonies,
        many=True,
        context={"request": request},
    )
    
    return Response({
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "results": serializer.data
    })


# =====================================================
# List User Testimonies (admin/owner only)
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_testimonies(request, user_id):
    """
    List all testimonies from a specific user (admin/owner only for other users)
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"error": "User not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    # 1. User can see their own testimonies
    if request.user.id != user.id:
        # 2. SuperAdmin can see all testimonies
        if request.user.role != "SADMIN":
            # 3. Church owner/admin can see testimonies of users in their church
            from api.permissions import is_church_admin
            # Check if both users are in the same church
            user_church = user.current_church_id
            request_user_church = request.user.current_church_id
            
            if user_church and request_user_church:
                try:
                    church = Church.objects.get(id=user_church)
                    if not is_church_admin(request.user, church):
                        return Response(
                            {"error": "You don't have permission to view this user's testimonies"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                except Church.DoesNotExist:
                    return Response(
                        {"error": "You don't have permission to view this user's testimonies"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                return Response(
                    {"error": "You don't have permission to view this user's testimonies"},
                    status=status.HTTP_403_FORBIDDEN
                )
    
    # Get user's testimonies
    qs = Testimony.objects.filter(user=user)
    
    serializer = TestimonyListSerializer(qs, many=True, context={"request": request})
    
    return Response({
        "count": qs.count(),
        "results": serializer.data
    })


# =====================================================
# List My Testimonies (current user)
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_testimonies(request):
    """
    List all testimonies of the currently authenticated user
    """
    # Get current user's testimonies
    qs = Testimony.objects.filter(user=request.user).order_by('-created_at')
    
    # Optional filters
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    
    type_filter = request.query_params.get('type')
    if type_filter:
        qs = qs.filter(type=type_filter)
    
    serializer = TestimonyListSerializer(qs, many=True, context={"request": request})
    
    return Response({
        "count": qs.count(),
        "results": serializer.data
    })


# =====================================================
# Approve/Reject Testimony (Church Owners/Admins only)
# =====================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_testimony(request, church_id, testimony_id):
    """
    Approve a pending testimony
    Body: empty (no parameters needed)
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions - only church owner/admin
    from api.permissions import is_church_admin
    if not is_church_admin(request.user, church) and request.user.role != "SADMIN":
        return Response(
            {"error": "Only church owners can approve testimonies"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Approve the testimony
    testimony.approve(request.user)

    _notify_testimony_owner(
        testimony,
        title=f"Temoignage approuve: {testimony.title}",
        message="Votre temoignage a ete approuve et est maintenant visible.",
        action="TESTIMONY_APPROVED",
        actor=request.user,
        allow_self=True,
    )

    serializer = TestimonySerializer(testimony, context={"request": request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_testimony(request, church_id, testimony_id):
    """
    Reject a testimony with a reason
    Body: {"rejection_reason": "string"}
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions - only church owner/admin
    from api.permissions import is_church_admin
    if not is_church_admin(request.user, church) and request.user.role != "SADMIN":
        return Response(
            {"error": "Only church owners can reject testimonies"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get rejection reason
    reason = request.data.get('rejection_reason', '')
    if not reason:
        return Response(
            {"error": "rejection_reason is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Reject the testimony
    testimony.reject(reason)

    _notify_testimony_owner(
        testimony,
        title=f"Temoignage refuse: {testimony.title}",
        message=f"Votre temoignage a ete refuse. Motif: {reason}",
        action="TESTIMONY_REJECTED",
        actor=request.user,
        allow_self=True,
        extra={"rejection_reason": reason},
    )

    serializer = TestimonySerializer(testimony, context={"request": request})
    return Response(serializer.data)


# =====================================================
# List Pending Testimonies (for moderation)
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_pending_testimonies(request, church_id):
    """
    List all pending testimonies for moderation (church owner/admin only)
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions - only church owner/admin
    from api.permissions import is_church_admin
    if not is_church_admin(request.user, church) and request.user.role != "SADMIN":
        return Response(
            {"error": "Only church owners can view pending testimonies"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get pending testimonies
    qs = Testimony.objects.filter(church=church, status="PENDING").order_by('-created_at')
    
    serializer = TestimonyListSerializer(qs, many=True, context={"request": request})
    
    return Response({
        "count": qs.count(),
        "results": serializer.data
    })


# =====================================================
# Increment View Count
# =====================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def increment_testimony_views(request, church_id, testimony_id):
    """
    Increment the view count for a testimony
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if testimony is public and approved
    if testimony.status != "APPROVED" or not testimony.is_public:
        return Response(
            {"error": "This testimony is not publicly available"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Increment view count
    testimony.views_count += 1
    testimony.save(update_fields=['views_count'])
    
    return Response({
        "views_count": testimony.views_count
    })


# =====================================================
# Statistics
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def testimony_stats_for_church(request, church_id):
    """
    Get statistics about testimonies for a church (church owner/admin only)
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions - only church owner/admin
    from api.permissions import is_church_admin
    if not is_church_admin(request.user, church) and request.user.role != "SADMIN":
        return Response(
            {"error": "Only church owners can view testimony statistics"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    testimonies = Testimony.objects.filter(church=church)
    
    stats = {
        "total": testimonies.count(),
        "pending": testimonies.filter(status="PENDING").count(),
        "approved": testimonies.filter(status="APPROVED").count(),
        "rejected": testimonies.filter(status="REJECTED").count(),
        "text": testimonies.filter(type="TEXT").count(),
        "audio": testimonies.filter(type="AUDIO").count(),
        "public": testimonies.filter(is_public=True).count(),
        "total_views": testimonies.aggregate(total=Sum('views_count'))['total'] or 0,
    }
    
    return Response(stats)


# =====================================================
# Toggle Like on Testimony
# =====================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_like_testimony(request, church_id, testimony_id):
    """
    Toggle like on a testimony (add or remove like)
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if testimony is public and approved
    if testimony.status != "APPROVED" or not testimony.is_public:
        return Response(
            {"error": "This testimony is not publicly available"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Toggle like
    like_obj, created = TestimonyLike.objects.get_or_create(
        testimony=testimony,
        user=request.user
    )
    
    if not created:
        # Like already exists, so remove it
        like_obj.delete()
        return Response({
            "liked": False,
            "likes_count": testimony.likes.count()
        })
    else:
        # Like was created
        _notify_testimony_owner(
            testimony,
            title=f"Nouveau like sur {testimony.title}",
            message=f"{request.user.name} a aime votre temoignage.",
            action="LIKE",
            actor=request.user,
        )
        return Response({
            "liked": True,
            "likes_count": testimony.likes.count()
        })


# =====================================================
# Get Testimony Likes
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_testimony_likes(request, church_id, testimony_id):
    """
    Get all likes for a testimony
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Church not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        testimony = Testimony.objects.get(id=testimony_id, church=church)
    except Testimony.DoesNotExist:
        return Response(
            {"error": "Testimony not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get likes
    likes = testimony.likes.all()
    user_liked = likes.filter(user=request.user).exists()
    
    serializer = TestimonyLikeSerializer(likes, many=True)
    
    return Response({
        "count": likes.count(),
        "user_liked": user_liked,
        "results": serializer.data
    })

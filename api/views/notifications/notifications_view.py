from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from api.models import Notification
from api.permissions import IsAuthenticatedUser
from api.serializers import NotificationPreferencesSerializer, NotificationSerializer
from api.services.notification_preferences import normalize_notification_preferences


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_notifications(request):
    try:
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
    except ValueError:
        limit = 20
        offset = 0

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")
    total_count = notifications.count()
    paginated = notifications[offset:offset + limit]

    return Response(
        {
            "count": total_count,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total_count else None,
            "unread_count": notifications.filter(is_read=False).count(),
            "results": NotificationSerializer(paginated, many=True).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def mark_notification_as_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return Response(NotificationSerializer(notification).data)


@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def mark_all_notifications_as_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"detail": "All notifications marked as read"}, status=status.HTTP_200_OK)


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser])
def notification_preferences(request):
    if request.method == "GET":
        serializer = NotificationPreferencesSerializer(
            normalize_notification_preferences(request.user.notification_preferences),
        )
        return Response(serializer.data)

    serializer = NotificationPreferencesSerializer(
        data=request.data,
        partial=request.method == "PATCH",
    )
    serializer.is_valid(raise_exception=True)

    current_preferences = normalize_notification_preferences(
        request.user.notification_preferences,
    )
    updated_preferences = normalize_notification_preferences(
        {
            **current_preferences,
            **serializer.validated_data,
        },
    )

    request.user.notification_preferences = updated_preferences
    request.user.save(update_fields=["notification_preferences"])

    return Response(NotificationPreferencesSerializer(updated_preferences).data)

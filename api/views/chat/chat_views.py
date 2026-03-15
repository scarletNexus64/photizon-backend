from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import OuterRef, Subquery
from django.core.files.storage import default_storage
from django.utils import timezone

from api.models import (
    ChatRoom,
    ChatMessage,
    ChatMessageRead,
    Church,
    ChurchAdmin,
    Commission,
    Notification,
    User,
)
from api.serializers import (
    ChatRoomSerializer,
    ChatRoomListSerializer,
    ChatRoomCreateUpdateSerializer,
    ChatMessageSerializer,
)
from api.permissions import IsAuthenticatedUser
from api.services.notification_preferences import build_in_app_notifications


def _build_chat_notification_meta(room, *, action, actor=None, include_room_id=True, extra=None):
    meta = {
        "room_action": action,
        "room_name": room.name,
        "room_type": room.room_type,
        "church_id": str(room.church_id),
    }
    if include_room_id:
        meta["room_id"] = str(room.id)
    if actor is not None:
        meta["actor_id"] = str(actor.id)
        meta["actor_name"] = actor.name
    if extra:
        meta.update(extra)
    return meta


def _create_chat_notifications(users, *, title, message, meta, exclude_user_id=None):
    recipients = build_in_app_notifications(
        users,
        title=title,
        message=message,
        notif_type="INFO",
        category="chat",
        meta=meta,
        exclude_user_id=exclude_user_id,
    )
    if recipients:
        Notification.objects.bulk_create(recipients)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticatedUser])
def list_create_chat_rooms(request, church_id):
    """List all chat rooms for a church or create a new one"""
    user = request.user
    
    # Check user has access to this church
    church = get_object_or_404(Church, id=church_id)
    
    if request.method == 'GET':
        # Members can list rooms they are allowed to access.
        # Keep payload light for mobile: no full messages list here.
        room_qs = ChatRoom.objects.filter(church=church).select_related(
            "church", "commission", "created_by"
        ).annotate(
            last_message=Subquery(
                ChatMessage.objects.filter(room_id=OuterRef("pk"))
                .order_by("-created_at")
                .values("message")[:1]
            )
        )

        has_church_scope = (
            user.current_church_id == church.id
            or ChurchAdmin.objects.filter(user=user, church=church).exists()
        )
        if user.role != 'SADMIN' and not has_church_scope:
            return Response(
                {"error": "You don't have access to this church"},
                status=status.HTTP_403_FORBIDDEN
            )

        rooms = [room for room in room_qs if room.user_has_access(user) or user.role == 'SADMIN']
        serializer = ChatRoomListSerializer(rooms, many=True, context={"request": request})
        return Response(serializer.data)
    
    elif request.method == 'POST':
        has_church_scope = (
            user.current_church_id == church.id
            or ChurchAdmin.objects.filter(user=user, church=church).exists()
            or user.role == 'SADMIN'
        )
        if not has_church_scope:
            return Response(
                {"error": "You don't have access to this church"},
                status=status.HTTP_403_FORBIDDEN
            )

        room_type = request.data.get("room_type")

        # Church-wide scoped rooms remain admin-only.
        is_admin = ChurchAdmin.objects.filter(
            user=user,
            church=church,
            role__in=['OWNER', 'ADMIN']
        ).exists() or user.role == 'SADMIN'
        if room_type != 'CUSTOM' and not is_admin:
            return Response(
                {"error": "Only admins can create this type of room"},
                status=status.HTTP_403_FORBIDDEN
            )

        data = request.data.copy()
        data['church'] = church_id
        data['created_by'] = user.id
        
        serializer = ChatRoomCreateUpdateSerializer(data=data)
        if serializer.is_valid():
            room = serializer.save(created_by=user)
            if room.room_type == "CUSTOM":
                room.members.add(user)
                invited_members = room.members.exclude(id=user.id)
                _create_chat_notifications(
                    invited_members,
                    title=f"Ajout au groupe: {room.name}",
                    message=f"{user.name} vous a ajoute au groupe {room.name}.",
                    meta=_build_chat_notification_meta(
                        room,
                        action="ROOM_ADDED",
                        actor=user,
                    ),
                    exclude_user_id=user.id,
                )
            return Response(ChatRoomSerializer(room, context={"request": request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticatedUser])
def room_detail(request, room_id):
    """Get, update or delete a chat room"""
    user = request.user
    room = get_object_or_404(ChatRoom, id=room_id)
    
    # Check if user has access
    if not room.user_has_access(user) and user.role != 'SADMIN':
        return Response(
            {"error": "You don't have access to this room"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Only admins can update/delete unless it is a custom room managed by its creator.
    is_admin = ChurchAdmin.objects.filter(
        user=user,
        church=room.church,
        role__in=['OWNER', 'ADMIN']
    ).exists() or user.role == 'SADMIN'
    can_manage_custom_room = room.room_type == 'CUSTOM' and room.created_by_id == user.id
    can_manage_room = is_admin or can_manage_custom_room
    
    if request.method == 'GET':
        serializer = ChatRoomSerializer(room, context={"request": request})
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        if not can_manage_room:
            return Response(
                {"error": "Only admins or the custom room creator can update rooms"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ChatRoomCreateUpdateSerializer(room, data=request.data, partial=True)
        if serializer.is_valid():
            updated_room = serializer.save()
            return Response(ChatRoomSerializer(updated_room, context={"request": request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        if not can_manage_room:
            return Response(
                {"error": "Only admins or the custom room creator can delete rooms"},
                status=status.HTTP_403_FORBIDDEN
            )
        room.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticatedUser])
def list_create_messages(request, room_id):
    """List all messages in a room or post a new message"""
    user = request.user
    room = get_object_or_404(ChatRoom, id=room_id)
    
    # Check if user has access
    if not room.user_has_access(user):
        return Response(
            {"error": "You don't have access to this room"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    if request.method == 'GET':
        # Load latest N messages and return in chronological order.
        messages = room.messages.order_by('-created_at')
        
        # Optional: limit to last N messages
        limit = request.GET.get('limit', 50)
        try:
            limit = int(limit)
            limit = max(1, min(limit, 200))
            messages = list(messages[:limit])[::-1]
        except ValueError:
            messages = list(messages[:50])[::-1]
        
        serializer = ChatMessageSerializer(messages, many=True, context={"request": request})
        return Response(serializer.data)
    
    elif request.method == 'POST':
        if room.only_admins_can_send and not room.user_can_send_message(user):
            return Response(
                {"error": "Only admins can send messages in this room"},
                status=status.HTTP_403_FORBIDDEN
            )
        data = request.data.copy()
        data['room'] = room_id
        data['user'] = user.id

        uploaded_file = request.FILES.get("file")
        if uploaded_file is not None:
            file_name = default_storage.save(
                f"chat_uploads/{uploaded_file.name}",
                uploaded_file,
            )
            file_url = request.build_absolute_uri(default_storage.url(file_name))
            content_type = getattr(uploaded_file, "content_type", "") or ""
            if content_type.startswith("image/"):
                data["image_url"] = file_url
            elif content_type.startswith("audio/"):
                data["audio_url"] = file_url
        reply_to_id = request.data.get("reply_to")
        if reply_to_id:
            reply_to = get_object_or_404(ChatMessage, id=reply_to_id, room=room)
            data["reply_to"] = reply_to.id

        serializer = ChatMessageSerializer(data=data)
        if serializer.is_valid():
            message = serializer.save(room=room, user=user)
            room_members = room.get_members_queryset().exclude(id=user.id)
            preview = (message.message or "").strip()
            if not preview:
                if message.image_url:
                    preview = "a partage une image"
                elif message.audio_url:
                    preview = "a partage un audio"
            else:
                preview = preview[:90]
            _create_chat_notifications(
                room_members,
                title=f"Nouveau message dans {room.name}",
                message=f"{user.name}: {preview}",
                meta=_build_chat_notification_meta(
                    room,
                    action="NEW_MESSAGE",
                    actor=user,
                    extra={"message_id": str(message.id)},
                ),
                exclude_user_id=user.id,
            )

            # Broadcast to websocket group so API fallback still updates in real-time
            channel_layer = get_channel_layer()
            if channel_layer is not None:
                async_to_sync(channel_layer.group_send)(
                    f"chat_{room.id}",
                    {
                        "type": "chat_message",
                        "message_id": str(message.id),
                        "user_id": str(user.id),
                        "user_name": user.name,
                        "message": message.message,
                        "reply_to": str(message.reply_to_id) if message.reply_to_id else None,
                        "reply_to_preview": ChatMessageSerializer(message, context={"request": request}).data.get("reply_to_preview"),
                        "image_url": message.image_url,
                        "audio_url": message.audio_url,
                        "created_at": message.created_at.isoformat(),
                        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
                    },
                )
            return Response(ChatMessageSerializer(message, context={"request": request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticatedUser])
def message_detail(request, room_id, message_id):
    """Get, update or delete a message"""
    user = request.user
    
    room = get_object_or_404(ChatRoom, id=room_id)
    message = get_object_or_404(ChatMessage, id=message_id, room=room)
    
    # Check if user has access to room
    if not room.user_has_access(user):
        return Response(
            {"error": "You don't have access to this room"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    if request.method == 'GET':
        serializer = ChatMessageSerializer(message, context={"request": request})
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        # Only message author can update
        if message.user_id != user.id and user.role != 'SADMIN':
            return Response(
                {"error": "You can only edit your own messages"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ChatMessageSerializer(message, data=request.data, partial=True)
        if serializer.is_valid():
            updated = serializer.save(edited_at=timezone.now())
            return Response(ChatMessageSerializer(updated, context={"request": request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        # Only message author or admins can delete
        is_owner = message.user_id == user.id
        is_admin = ChurchAdmin.objects.filter(
            user=user,
            church=room.church,
            role__in=['OWNER', 'ADMIN']
        ).exists() or user.role == 'SADMIN'
        
        if not (is_owner or is_admin):
            return Response(
                {"error": "You can only delete your own messages"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def mark_room_messages_read(request, room_id):
    user = request.user
    room = get_object_or_404(ChatRoom, id=room_id)

    if not room.user_has_access(user):
        return Response(
            {"error": "You don't have access to this room"},
            status=status.HTTP_403_FORBIDDEN
        )

    unread_messages = room.messages.exclude(user=user)
    created = 0
    for message in unread_messages:
        _, was_created = ChatMessageRead.objects.get_or_create(
            message=message,
            user=user,
        )
        if was_created:
            created += 1

    return Response({"marked": created}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def add_member_to_custom_room(request, room_id):
    """Add members to a custom chat room"""
    user = request.user
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if room.room_type != 'CUSTOM':
        return Response(
            {"error": "Only CUSTOM rooms support adding members"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if user is admin
    is_admin = ChurchAdmin.objects.filter(
        user=user,
        church=room.church,
        role__in=['OWNER', 'ADMIN']
    ).exists() or user.role == 'SADMIN'
    
    can_manage_room = is_admin or room.created_by_id == user.id

    if not can_manage_room:
        return Response(
            {"error": "Only admins or the room creator can add members"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    user_ids = request.data.get('user_ids', [])
    if not user_ids:
        return Response(
            {"error": "user_ids is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    users_to_add = User.objects.filter(id__in=user_ids).distinct()
    room.members.add(*users_to_add)
    _create_chat_notifications(
        users_to_add,
        title=f"Ajout au groupe: {room.name}",
        message=f"{user.name} vous a ajoute au groupe {room.name}.",
        meta=_build_chat_notification_meta(
            room,
            action="ROOM_ADDED",
            actor=user,
        ),
        exclude_user_id=user.id,
    )
    
    return Response(
        {"message": f"Added {len(user_ids)} members"},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def remove_member_from_custom_room(request, room_id):
    """Remove members from a custom chat room"""
    user = request.user
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if room.room_type != 'CUSTOM':
        return Response(
            {"error": "Only CUSTOM rooms support removing members"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if user is admin
    is_admin = ChurchAdmin.objects.filter(
        user=user,
        church=room.church,
        role__in=['OWNER', 'ADMIN']
    ).exists() or user.role == 'SADMIN'
    
    can_manage_room = is_admin or room.created_by_id == user.id

    if not can_manage_room:
        return Response(
            {"error": "Only admins or the room creator can remove members"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    user_ids = request.data.get('user_ids', [])
    if not user_ids:
        return Response(
            {"error": "user_ids is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    users_to_remove = User.objects.filter(id__in=user_ids).distinct()
    _create_chat_notifications(
        users_to_remove,
        title=f"Retire du groupe: {room.name}",
        message=f"{user.name} vous a retire du groupe {room.name}.",
        meta=_build_chat_notification_meta(
            room,
            action="ROOM_REMOVED",
            actor=user,
            include_room_id=False,
        ),
        exclude_user_id=user.id,
    )
    room.members.remove(*users_to_remove)
    
    return Response(
        {"message": f"Removed {len(user_ids)} members"},
        status=status.HTTP_200_OK
    )


# =====================================================
# Programme Chat Endpoints
# =====================================================

@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def create_programme_chat(request, church_id, programme_id):
    """
    Créer un chat pour un programme
    Body: {
        "name": "string (optionnel)"
    }
    """
    from api.models import Programme
    from api.permissions import is_church_admin
    
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Église non trouvée"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        programme = Programme.objects.get(id=programme_id, church=church)
    except Programme.DoesNotExist:
        return Response(
            {"error": "Programme non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier les permissions
    if not is_church_admin(request.user, church) and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous devez être administrateur de cette église"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Vérifier qu'un chat n'existe pas déjà pour ce programme
    existing = ChatRoom.objects.filter(programme=programme, room_type='PROGRAMME').first()
    if existing:
        return Response(
            {"error": "Un chat existe déjà pour ce programme"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    name = request.data.get('name') or f"Chat - {programme.title}"
    
    chat_room = ChatRoom.objects.create(
        church=church,
        programme=programme,
        room_type='PROGRAMME',
        name=name,
        created_by=request.user
    )
    
    serializer = ChatRoomSerializer(chat_room)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def get_programme_chat(request, church_id, programme_id):
    """
    Récupérer le chat d'un programme
    """
    from api.models import Programme
    
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Église non trouvée"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        programme = Programme.objects.get(id=programme_id, church=church)
    except Programme.DoesNotExist:
        return Response(
            {"error": "Programme non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que l'utilisateur est membre
    if request.user.current_church_id != church.id and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous devez être membre de cette église"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    chat_room = ChatRoom.objects.filter(
        programme=programme,
        room_type='PROGRAMME'
    ).first()
    
    if not chat_room:
        return Response(
            {"error": "Aucun chat pour ce programme"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = ChatRoomSerializer(chat_room)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def send_programme_message(request, church_id, programme_id):
    """
    Envoyer un message dans le chat du programme
    Body: {
        "content": "string"
    }
    """
    from api.models import Programme
    
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Église non trouvée"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        programme = Programme.objects.get(id=programme_id, church=church)
    except Programme.DoesNotExist:
        return Response(
            {"error": "Programme non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que l'utilisateur est membre
    if request.user.current_church_id != church.id and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous devez être membre de cette église"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    chat_room = ChatRoom.objects.filter(
        programme=programme,
        room_type='PROGRAMME'
    ).first()
    
    if not chat_room:
        return Response(
            {"error": "Aucun chat pour ce programme"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    content = request.data.get('content')
    if not content:
        return Response(
            {"error": "content requis"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    message = ChatMessage.objects.create(
        room=chat_room,
        user=request.user,
        content=content
    )
    
    serializer = ChatMessageSerializer(message)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def get_programme_messages(request, church_id, programme_id):
    """
    Récupérer les messages du chat d'un programme
    Query params: limit, offset
    """
    from api.models import Programme
    
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Église non trouvée"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        programme = Programme.objects.get(id=programme_id, church=church)
    except Programme.DoesNotExist:
        return Response(
            {"error": "Programme non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que l'utilisateur est membre
    if request.user.current_church_id != church.id and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous devez être membre de cette église"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    chat_room = ChatRoom.objects.filter(
        programme=programme,
        room_type='PROGRAMME'
    ).first()
    
    if not chat_room:
        return Response(
            {"error": "Aucun chat pour ce programme"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    messages = ChatMessage.objects.filter(room=chat_room).select_related(
        'user'
    ).order_by('-created_at')
    
    # Pagination
    try:
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
    except ValueError:
        limit = 20
        offset = 0
    
    limit = min(limit, 100)
    total_count = messages.count()
    paginated_messages = messages[offset:offset + limit]
    
    serializer = ChatMessageSerializer(paginated_messages, many=True)
    
    return Response({
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total_count else None,
        "results": serializer.data
    })

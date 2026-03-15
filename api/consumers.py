import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatMessage, ChatRoom, Notification
from .serializers import ChatMessageSerializer
from api.services.notification_preferences import build_in_app_notifications


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time chat"""

    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = self.scope['user']

        # Verify user has access to this room
        has_access = await self.check_room_access()
        if not has_access:
            await self.close()
            return

        # Add to group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Remove from group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Receive message from WebSocket"""
        try:
            data = json.loads(text_data)
            message_text = data.get('message', '').strip()
            image_url = data.get('image_url')
            audio_url = data.get('audio_url')
            reply_to_id = data.get('reply_to')

            room = await self.get_room()
            if room is None or not await self.can_send_message(room):
                return

            if not message_text and not image_url and not audio_url:
                return

            # Save message to database
            message_obj = await self.save_message(
                message_text,
                image_url=image_url,
                audio_url=audio_url,
                reply_to_id=reply_to_id,
            )

            # Broadcast to group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': str(message_obj.id),
                    'user_id': str(self.user.id),
                    'user_name': self.user.name,
                    'message': message_text,
                    'reply_to': str(message_obj.reply_to_id) if message_obj.reply_to_id else None,
                    'reply_to_preview': await self.get_reply_preview(message_obj),
                    'image_url': message_obj.image_url,
                    'audio_url': message_obj.audio_url,
                    'created_at': message_obj.created_at.isoformat(),
                    'edited_at': message_obj.edited_at.isoformat() if message_obj.edited_at else None,
                }
            )
        except json.JSONDecodeError:
            pass

    async def chat_message(self, event):
        """Handle chat message event"""
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['message_id'],
            'user_id': event['user_id'],
            'user_name': event['user_name'],
            'message': event['message'],
            'reply_to': event.get('reply_to'),
            'reply_to_preview': event.get('reply_to_preview'),
            'image_url': event.get('image_url'),
            'audio_url': event.get('audio_url'),
            'created_at': event['created_at'],
            'edited_at': event.get('edited_at'),
        }))

    @database_sync_to_async
    def save_message(self, message_text, image_url=None, audio_url=None, reply_to_id=None):
        """Save message to database"""
        room = ChatRoom.objects.get(id=self.room_id)
        reply_to = None
        if reply_to_id:
            reply_to = ChatMessage.objects.filter(id=reply_to_id, room=room).first()
        message = ChatMessage.objects.create(
            room=room,
            user=self.user,
            message=message_text,
            reply_to=reply_to,
            image_url=image_url,
            audio_url=audio_url,
        )
        preview = (message.message or "").strip()
        if not preview:
            if image_url:
                preview = "a partage une image"
            elif audio_url:
                preview = "a partage un audio"
        else:
            preview = preview[:90]

        recipients = room.get_members_queryset().exclude(id=self.user.id)
        notifications = build_in_app_notifications(
            recipients,
            title=f"Nouveau message dans {room.name}",
            message=f"{self.user.name}: {preview}",
            notif_type="INFO",
            category="chat",
            meta={
                "room_id": str(room.id),
                "room_name": room.name,
                "room_type": room.room_type,
                "room_action": "NEW_MESSAGE",
                "church_id": str(room.church_id),
                "actor_id": str(self.user.id),
                "actor_name": self.user.name,
                "message_id": str(message.id),
            },
        )
        if notifications:
            Notification.objects.bulk_create(notifications)
        return message

    @database_sync_to_async
    def get_reply_preview(self, message_obj):
        if message_obj.reply_to is None:
            return None
        parent = message_obj.reply_to
        return {
            'id': str(parent.id),
            'user_name': parent.user.name,
            'message': parent.message,
            'image_url': parent.image_url,
            'audio_url': parent.audio_url,
        }

    @database_sync_to_async
    def get_room(self):
        try:
            return ChatRoom.objects.get(id=self.room_id)
        except ChatRoom.DoesNotExist:
            return None

    @database_sync_to_async
    def can_send_message(self, room):
        return room.user_can_send_message(self.user)

    @database_sync_to_async
    def check_room_access(self):
        """Check if user has access to this room based on room_type"""
        if not self.user.is_authenticated:
            return False

        try:
            room = ChatRoom.objects.get(id=self.room_id)
            return room.user_has_access(self.user)
        except ChatRoom.DoesNotExist:
            return False

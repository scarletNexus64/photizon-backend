from rest_framework import serializers
from api.models import BookOrder, Comment, Content, Donation, DonationCategory,Tag, ContentLike, ContentView, Playlist, PlaylistItem, User,Church, Subscription, SubscriptionPlan, ChurchAdmin,Commission,ChurchCommission,Category, TicketType, Ticket, TicketReservation, Receipt, ChatMessage, ChatRoom, ChatMessageRead, Testimony, ChurchCollaboration, TestimonyLike, Programme, ProgrammeMember, ContentNotification, Notification, ProgrammeContentNotification
from django.utils.text import slugify
from api.services.notification_preferences import normalize_notification_preferences

class StrictFieldsSerializerMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        incoming_keys = set(getattr(self, "initial_data", {}).keys())
        allowed_keys = set(self.fields.keys())
        unknown_keys = incoming_keys - allowed_keys
        if unknown_keys:
            raise serializers.ValidationError(
                {
                    key: "This field is not allowed."
                    for key in sorted(unknown_keys)
                }
            )
        return attrs


class UserSerializer(serializers.ModelSerializer):
    current_church = serializers.PrimaryKeyRelatedField(read_only=True)
    notification_preferences = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "phone_number",
            "picture_url",
            "role",
            "email",
            "city",
            "country",
            "address",
            "longitude",
            "latitude",
            "current_church",
            "notification_preferences",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_notification_preferences(self, obj):
        return normalize_notification_preferences(obj.notification_preferences)


class UserSelfUpdateSerializer(StrictFieldsSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "name",
            "picture_url",
            "email",
            "city",
            "country",
            "address",
            "longitude",
            "latitude",
        ]


class NotificationPreferencesSerializer(
    StrictFieldsSerializerMixin,
    serializers.Serializer,
):
    general = serializers.BooleanField(required=False)
    content = serializers.BooleanField(required=False)
    social = serializers.BooleanField(required=False)
    chat = serializers.BooleanField(required=False)
    donation = serializers.BooleanField(required=False)

    def to_representation(self, instance):
        return normalize_notification_preferences(instance)

class ChurchSerializer(serializers.ModelSerializer):
    sub_churches = serializers.SerializerMethodField()
    phone_number = serializers.CharField(read_only=True)
    
    class Meta:
        model = Church
        fields = "__all__"
        read_only_fields = ["status", "code", "slug", "is_verified", "created_at"]

    def get_sub_churches(self, obj):
        # Utiliser values() pour une requête groupée efficace si possible, 
        # ou limiter les champs retournés
        return obj.sub_churches.all().values(
            "id", "title", "slug", "status", "code", "logo_url", "is_verified"
        )


class ChurchUpdateSerializer(StrictFieldsSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Church
        fields = [
            "title",
            "description",
            "logo_url",
            "primary_color",
            "secondary_color",
            "email",
            "phone_number_1",
            "phone_number_2",
            "phone_number_3",
            "phone_number_4",
            "website",
            "whatsapp_phone",
            "doc_url",
            "tiktok_url",
            "instagram_url",
            "youtube_url",
            "facebook_url",
            "city",
            "country",
            "longitude",
            "latitude",
            "seats",
            "is_public",
            "lang",
        ]



class ChurchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Church
        fields = [
            "title", "logo_url",
            "description",
            "primary_color", "secondary_color",
            "phone_number_1", "phone_number_2", "phone_number_3", "phone_number_4",
            "city", "country","lang",
            "longitude", "latitude",
            "seats", "is_public"
        ]

class SubChurchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Church
        fields = [
            "title", "logo_url", "parent",
            "description",
            "primary_color", "secondary_color",
            "phone_number_1", "phone_number_2", "phone_number_3", "phone_number_4",
            "city", "country", "lang",
            "longitude", "latitude",
            "seats", "is_public",
        ]
        
class ChurchAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChurchAdmin
        fields = "__all__"

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]

class ChurchRoleSerializer(serializers.ModelSerializer):
    church = serializers.SerializerMethodField()

    class Meta:
        model = ChurchAdmin
        fields = ["church", "role", "created_at"]

    def get_church(self, obj):
        return {
            "id": obj.church.id,
            "title": obj.church.title,
            "code": obj.church.code,
            "city": obj.church.city,
            "country": obj.church.country,
            "status": obj.church.status,
        }

class ChurchMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Church
        fields = ["id", "title", "code", "city", "country", "status"]

class UserMeSerializer(serializers.ModelSerializer):
    current_church = ChurchMiniSerializer(read_only=True)
    church_roles = ChurchRoleSerializer(many=True, read_only=True)
    notification_preferences = serializers.SerializerMethodField()

    is_sadmin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "phone_number",
            "email",
            "city",
            "country",
            "address",
            "longitude",
            "latitude",
            "picture_url",
            "role",
            "is_sadmin",
            "current_church",
            "church_roles",
            "notification_preferences",
            "created_at",
            "updated_at",
        ]

    def get_is_sadmin(self, obj):
        return obj.role == "SADMIN"

    def get_notification_preferences(self, obj):
        return normalize_notification_preferences(obj.notification_preferences)

class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "phone_number", "picture_url", "created_at"]

class CommissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commission
        fields = ["id", "name","eng_name","logo","description"]

class ChurchCommissionSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()

    class Meta:
        model = ChurchCommission
        fields = [
            "id",
            "church",
            "commission",
            "user",
            "role",
          
        ]

    def get_user(self, obj):
        return {
            "id": obj.user.id,
            "name": obj.user.name,
            "phone_number": obj.user.phone_number,
            "picture_url": obj.user.picture_url,
        }

    def get_commission(self, obj):
        return {
            "id": obj.commission.id,
            "name": obj.commission.name,
            "eng_name": obj.commission.eng_name,
            "logo": obj.commission.logo,
        }

class AddMemberToCommissionSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role = serializers.CharField(required=False, default="MEMBER")

class ChurchCommissionSummarySerializer(serializers.Serializer):
    commission_id = serializers.IntegerField()
    commission_name = serializers.CharField()
    members_count = serializers.IntegerField()

class CommissionMemberSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="user.id")
    name = serializers.CharField(source="user.name")
    phone_number = serializers.CharField(source="user.phone_number")
    picture_url = serializers.CharField(source="user.picture_url")

    class Meta:
        model = ChurchCommission
        fields = [
            "id",
            "role",
            "name",
            "phone_number",
            "picture_url",
        ]

class ChurchCommissionMemberSerializer(serializers.ModelSerializer):
    user = UserMeSerializer()

    class Meta:
        model = ChurchCommission
        fields = ["id", "user", "role", "joined_at"]


class CommissionWithMembersSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()

    class Meta:
        model = Commission
        fields = ["id", "name", "logo", "description", "members"]

    def get_members(self, obj):
        church_id = self.context.get("church_id")
        qs = ChurchCommission.objects.filter(church_id=church_id, commission=obj)
        # Return flattened user objects with role (id, name, phone_number, picture_url, role, created_at)
        return CommissionMemberSerializer(qs, many=True).data

class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = ["id", "name", "slug"]

    def validate_name(self, value):
        if Category.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("This category already exists.")
        return value

    def create(self, validated_data):
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            instance.slug = slugify(validated_data["name"])
        return super().update(instance, validated_data)

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]

class ContentListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = serializers.SerializerMethodField()
    church = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    views_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            "id","church","type","title","slug","description","cover_image_url",
            "audio_url","video_url","file",
            "is_paid","price","currency","category","tags","created_at","published",
            "capacity","tickets_sold","allow_ticket_sales","created_by",
            "likes_count","comments_count","views_count","is_liked","start_at",
            "planned_release_date","location"
        ]

    def get_tags(self, obj):
        # On suppose que contenttag_set__tag est pré-chargé via prefetch_related
        # Si c'est le cas, on itère en mémoire au lieu de refaire une requête DB
        if hasattr(obj, 'contenttag_set'):
            return [
                {"tag__id": ct.tag.id, "tag__name": ct.tag.name, "tag__slug": ct.tag.slug}
                for ct in obj.contenttag_set.all()
            ]
        return []

    def get_church(self, obj):
        return {
            "id": obj.church.id,
            "title": obj.church.title,
            "code": obj.church.code,
            "logo_url": obj.church.logo_url,
        }

    def get_created_by(self, obj):
        if not obj.created_by:
            return None
        return {
            "id": obj.created_by.id,
            "name": obj.created_by.name,
            "picture_url": obj.created_by.picture_url,
            "phone_number": obj.created_by.phone_number,
        }

    def get_likes_count(self, obj):
        return int(getattr(obj, "likes_count", 0) or 0)

    def get_comments_count(self, obj):
        return int(getattr(obj, "comments_count", 0) or 0)

    def get_views_count(self, obj):
        return int(getattr(obj, "views_count", 0) or 0)

    def get_is_liked(self, obj):
        return bool(getattr(obj, "is_liked", False))

class ContentDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = serializers.SerializerMethodField()
    church = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = "__all__"

    def get_tags(self, obj):
        # Utiliser les données préchargées en mémoire si possible
        if hasattr(obj, 'contenttag_set'):
             return [{"id": ct.tag.id, "name": ct.tag.name, "slug": ct.tag.slug} for ct in obj.contenttag_set.all()]
        return []

    def get_church(self, obj):
        return {"id": obj.church.id, "title": obj.church.title, "code": obj.church.code}

    def get_created_by(self, obj):
        if obj.created_by:
            return {"id": obj.created_by.id, "name": obj.created_by.name, "phone_number": obj.created_by.phone_number}
        return None

class ContentCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        exclude = ["created_at", "updated_at"]

    def validate(self, data):
        # If capacity is provided in payload or already on instance, ensure tier sums fit
        capacity = data.get("capacity")
        # When updating, instance may have existing capacity
        instance = getattr(self, "instance", None)
        if capacity is None and instance is not None:
            capacity = instance.capacity

        has_tiers = data.get("has_ticket_tiers", None)
        # If not provided, fall back to instance
        if has_tiers is None and instance is not None:
            has_tiers = instance.has_ticket_tiers

        if has_tiers and capacity is not None:
            # compute sum of provided/new tier quantities, falling back to instance values
            def val(field):
                return data.get(field, getattr(instance, field, None) if instance is not None else None) or 0

            total = int(val("classic_quantity")) + int(val("vip_quantity")) + int(val("premium_quantity"))
            if total > int(capacity):
                raise serializers.ValidationError("Sum of tier quantities exceeds capacity")

        return data

class CommentSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    class Meta:
        model = Comment
        fields = ["id","user","content","text","created_at"]

    def get_user(self, obj):
        return {"id": obj.user.id, "name": obj.user.name, "phone": obj.user.phone_number}
    def get_content(self, obj):
        return {"id": obj.content.id, "title": obj.content.title, "slug": obj.content.slug}
class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentLike
        fields = ["id","user","content","liked_at"]
class ContentNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "slug", "type", "cover_image_url"]

class ViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentView
        fields = ["id","user","content","viewed_at"]
class PlaylistItemNestedSerializer(serializers.ModelSerializer):
    content = ContentNestedSerializer()  # inclut les infos du content

    class Meta:
        model = PlaylistItem
        fields = ["id", "content", "position"]
class PlaylistSerializer(serializers.ModelSerializer):
    items = PlaylistItemNestedSerializer(source="playlistitem_set", many=True, read_only=True)
    church = serializers.SerializerMethodField()
    class Meta:
        model = Playlist
        fields = ["id", "church", "title", "description", "cover_image_url", "items"]
    def get_church(self, obj):
        return {
            "id": obj.church.id,
            "title": obj.church.title,
            "code": obj.church.code
        }
class ContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "slug", "type", "cover_image_url"] 

class PlaylistItemSerializer(serializers.ModelSerializer):
    content = ContentSerializer(read_only=True)
    playlist = PlaylistSerializer(read_only=True)

    class Meta:
        model = PlaylistItem
        fields = ["id", "playlist", "content", "position"]

class SubscriptionSerializer(serializers.ModelSerializer):
    church = serializers.SerializerMethodField()
    subscription_plan_details = SubscriptionPlanSerializer(source='subscription_plan', read_only=True)
    plan_name = serializers.SerializerMethodField()
    plan_price = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id", "church", "plan", "subscription_plan", "subscription_plan_details",
            "plan_name", "plan_price", "started_at", "expires_at",
            "is_active", "gateway", "gateway_subscription_id"
        ]

    def get_church(self, obj):
        return {
            "id": obj.church.id,
            "title": obj.church.title,
            "code": obj.church.code
        }

    def get_plan_name(self, obj):
        return obj.get_plan_name()

    def get_plan_price(self, obj):
        return obj.get_plan_price()

class PlaylistItemSContenterializer(serializers.ModelSerializer):
    content = ContentDetailSerializer()

    class Meta:
        model = PlaylistItem
        fields = ["id", "position", "content"]



class OwnerSerializer(serializers.ModelSerializer):
    churches = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "phone_number", "churches"]

    def get_churches(self, user):
        # Toutes les églises où ce user est OWNER
        admin_entries = ChurchAdmin.objects.filter(user=user, role="OWNER")
        churches = [entry.church for entry in admin_entries]

        return ChurchSerializer(churches, many=True).data

class DonationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DonationCategory
        fields = ["id", "name", "description"]

class DonationSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    church = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()

    class Meta:
        model = Donation
        fields = [
            "id", "user", "church", "category",
            "amount", "currency", "gateway", "gateway_transaction_id",
             "message", "metadata","withdrawed", "created_at"
            
        ]

    def get_user(self, obj):
        return {
            "id": obj.user.id,
            "phone_number": obj.user.phone_number,
            "name": obj.user.name
        }

    def get_church(self, obj):
        return {
            "id": obj.church.id,
            "title": obj.church.title,
            "code": obj.church.code
        }

    def get_category(self, obj):
        if obj.category:
            return {
                "id": obj.category.id,
                "name": obj.category.name
            }
        return None
    
class BookOrderSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    tickets = serializers.SerializerMethodField()

    class Meta:
        model = BookOrder
        fields = [
            "id", "user", "content", "delivery_type", "quantity", 
            "total_price", "payment_gateway", "payment_transaction_id", 
            "shipped", "delivered_at", "created_at","withdrawed",
            "is_ticket", "ticket_type", "ticket_tier", "tickets",
            "delivery_recipient_name", "delivery_address_line1", "delivery_address_line2",
            "delivery_city", "delivery_postal_code", "delivery_country", "delivery_phone",
            "shipping_method", "shipping_cost",
        ]
    
    def get_user(self, obj):
        return {
            "id": obj.user.id,
            "phone_number": obj.user.phone_number,
            "name": obj.user.name
        }

    def get_content(self, obj):
        return {
            "id": obj.content.id,
            "title": obj.content.title,
            "type": obj.content.type,
            "price": obj.content.price,
            "has_ticket_tiers": obj.content.has_ticket_tiers,
            "classic_price": obj.content.classic_price,
            "classic_quantity": obj.content.classic_quantity,
            "vip_price": obj.content.vip_price,
            "vip_quantity": obj.content.vip_quantity,
            "premium_price": obj.content.premium_price,
            "premium_quantity": obj.content.premium_quantity,
            "church_id": obj.content.church.id,
            "church_title": obj.content.church.title
        }

    def get_tickets(self, obj):
        qs = obj.tickets.all() if hasattr(obj, "tickets") else []
        return TicketSerializer(qs, many=True).data


class TicketTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketType
        fields = ["id", "content", "name", "price", "quantity", "created_at"]


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["id", "content", "order", "ticket_type", "user", "seat", "price", "status", "issued_at"]


class TicketReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketReservation
        fields = ["id", "user", "content", "ticket_type", "quantity", "reserved_at", "expires_at"]


class ReceiptSerializer(serializers.ModelSerializer):
    church_title = serializers.CharField(source="church.title", read_only=True, allow_null=True)
    content_title = serializers.CharField(source="content.title", read_only=True, allow_null=True)
    
    class Meta:
        model = Receipt
        fields = [
            "id", "church", "church_title", "content", "content_title",
            "amount", "description", "issued_at", "created_at"
        ]
        read_only_fields = ["id", "issued_at", "created_at", "church"]


# =====================================================
# Chat Serializers
# =====================================================
class ChatMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_id = serializers.CharField(source="user.id", read_only=True)
    reply_to_preview = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = [
            "id", "user", "user_name", "user_id", "message",
            "reply_to", "reply_to_preview",
            "image_url", "audio_url", "created_at", "edited_at",
            "is_read", "read_count",
        ]
        read_only_fields = ["id", "created_at", "user"]

    def get_reply_to_preview(self, obj):
        parent = obj.reply_to
        if parent is None:
            return None
        return {
            "id": parent.id,
            "user_name": parent.user.name,
            "message": parent.message,
            "image_url": parent.image_url,
            "audio_url": parent.audio_url,
        }

    def get_is_read(self, obj):
        request = self.context.get("request")
        if request is None or not getattr(request, "user", None):
            return False
        return obj.reads.filter(user=request.user).exists()

    def get_read_count(self, obj):
        return obj.reads.count()


class ChatRoomSerializer(serializers.ModelSerializer):
    church_title = serializers.CharField(source="church.title", read_only=True)
    room_type_display = serializers.CharField(source="get_room_type_display", read_only=True)
    messages = ChatMessageSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source="created_by.name", read_only=True)
    commission_name = serializers.CharField(source="commission.name", read_only=True, allow_null=True)
    members_count = serializers.SerializerMethodField()
    members_list = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id", "church", "church_title", "room_type", "room_type_display", 
            "name", "description", "avatar_url", "only_admins_can_send",
            "commission", "commission_name", "members_count", "members_list",
            "created_at", "updated_at", "created_by", "created_by_name", "messages"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by"]
    
    def get_members_count(self, obj):
        """Get count of members in this room"""
        return obj.get_members_queryset().count()
    
    def get_members_list(self, obj):
        """Get detailed list of all members in this room"""
        members = obj.get_members_queryset()
        return [
            {
                "id": member.id,
                "name": member.name,
                "phone_number": member.phone_number,
                "email": member.email,
                "picture_url": member.picture_url,
            }
            for member in members
        ]


class ChatRoomListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for rooms list to avoid returning the full messages
    payload for every room.
    """
    church_title = serializers.CharField(source="church.title", read_only=True)
    room_type_display = serializers.CharField(source="get_room_type_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.name", read_only=True)
    commission_name = serializers.CharField(source="commission.name", read_only=True, allow_null=True)
    members_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id", "church", "church_title", "room_type", "room_type_display",
            "name", "description", "avatar_url", "only_admins_can_send",
            "commission", "commission_name", "members_count",
            "created_at", "updated_at", "created_by", "created_by_name",
            "last_message",
        ]

    def get_members_count(self, obj):
        return obj.get_members_queryset().count()

    def get_last_message(self, obj):
        annotated = getattr(obj, "last_message", None)
        if annotated is not None:
            return annotated
        return obj.messages.order_by("-created_at").values_list("message", flat=True).first()


class ChatRoomCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating chat rooms"""
    
    class Meta:
        model = ChatRoom
        fields = [
            "church", "room_type", "name", "description", "avatar_url",
            "only_admins_can_send", "commission", "members"
        ]
    
    def validate(self, data):
        """Validate room_type specific requirements"""
        room_type = data.get('room_type')
        
        if room_type == 'COMMISSION' and not data.get('commission'):
            raise serializers.ValidationError("Commission is required for COMMISSION type rooms")
        
        if room_type == 'CUSTOM' and not data.get('members'):
            raise serializers.ValidationError("Members are required for CUSTOM type rooms")
        
        return data


# =====================================================
# Testimony Serializers
# =====================================================

class TestimonySerializer(serializers.ModelSerializer):
    """Serializer for displaying testimonies"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    church_title = serializers.CharField(source='church.title', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.name', read_only=True, allow_null=True)
    likes_count = serializers.SerializerMethodField()
    user_liked = serializers.SerializerMethodField()
    
    class Meta:
        model = Testimony
        fields = [
            "id", "church", "church_title", "user", "user_name",
            "type", "title", "text_content", "audio_url", "duration",
            "status", "is_public", "views_count", "likes_count", "user_liked",
            "created_at", "updated_at", "approved_at", "approved_by", "approved_by_name",
            "rejection_reason"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "views_count"]

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_user_liked(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False


class TestimonyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating testimonies"""
    
    class Meta:
        model = Testimony
        fields = ["type", "title", "text_content", "audio_url", "duration", "is_public"]
    
    def validate(self, data):
        """Validate testimony data"""
        testimony_type = data.get('type')
        
        # Validate TEXT type
        if testimony_type == 'TEXT':
            if not data.get('text_content'):
                raise serializers.ValidationError("Le contenu texte est requis pour un témoignage texte")
        
        # Validate AUDIO type
        elif testimony_type == 'AUDIO':
            if not data.get('audio_url'):
                raise serializers.ValidationError("L'URL audio est requise pour un témoignage audio")
        
        return data



class TestimonyUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating testimonies"""
    
    class Meta:
        model = Testimony
        fields = ["title", "text_content", "audio_url", "duration", "is_public"]
    
    def validate(self, data):
        """Validate testimony data"""
        instance = self.instance
        testimony_type = instance.type
        
        # Validate TEXT type updates
        if testimony_type == 'TEXT':
            text_content = data.get('text_content', instance.text_content)
            if not text_content:
                raise serializers.ValidationError("Le contenu texte ne peut pas être vide")
        
        # Validate AUDIO type updates
        elif testimony_type == 'AUDIO':
            audio_url = data.get('audio_url', instance.audio_url)
            if not audio_url:
                raise serializers.ValidationError("L'URL audio ne peut pas être vide")
        
        return data


class TestimonyListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing testimonies"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_picture = serializers.CharField(source='user.picture_url', read_only=True)
    likes_count = serializers.SerializerMethodField()
    user_liked = serializers.SerializerMethodField()
    
    class Meta:
        model = Testimony
        fields = [
            "id", "user", "user_name", "user_picture",
            "type", "title", "text_content", "audio_url", "duration",
            "status", "views_count", "likes_count", "user_liked", "created_at"
        ]
        read_only_fields = fields

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_user_liked(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False


class TestimonyApprovalSerializer(serializers.ModelSerializer):
    """Serializer for approving/rejecting testimonies"""
    
    class Meta:
        model = Testimony
        fields = ["status", "rejection_reason"]
    
    def validate(self, data):
        """Validate approval data"""
        if data.get('status') == 'REJECTED' and not data.get('rejection_reason'):
            raise serializers.ValidationError("Une raison de rejet est requise")
        return data

# =====================================================
# Church Collaboration Serializers
# =====================================================

class ChurchCollaborationSerializer(serializers.ModelSerializer):
    """Full serializer for church collaborations"""
    initiator_church = ChurchSerializer(read_only=True)
    target_church = ChurchSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    accepted_by = UserSerializer(read_only=True)
    
    class Meta:
        model = ChurchCollaboration
        fields = [
            "id", "initiator_church", "target_church", "created_by",
            "collaboration_type", "status", "start_date",
            "created_at", "updated_at", "accepted_at",
            "rejected_at", "accepted_by"
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "accepted_at", "rejected_at",
            "accepted_by", "created_by"
        ]

class ChurchCollaborationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating collaborations"""
    target_church_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = ChurchCollaboration
        fields = [
            "target_church_id", "collaboration_type", "start_date"
        ]

class ChurchCollaborationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating collaborations"""
    
    class Meta:
        model = ChurchCollaboration
        fields = [
            "collaboration_type", "start_date"
        ]

class ChurchCollaborationListSerializer(serializers.ModelSerializer):
    """Serializer for listing collaborations"""
    initiator_church = serializers.SerializerMethodField()
    target_church = serializers.SerializerMethodField()
    
    class Meta:
        model = ChurchCollaboration
        fields = [
            "id", "initiator_church", "target_church",
            "collaboration_type", "status", "start_date",
            "created_at"
        ]
    
    def get_initiator_church(self, obj):
        return {
            "id": obj.initiator_church.id,
            "title": obj.initiator_church.title,
            "logo_url": obj.initiator_church.logo_url
        }
    
    def get_target_church(self, obj):
        return {
            "id": obj.target_church.id,
            "title": obj.target_church.title,
            "logo_url": obj.target_church.logo_url
        }

class ChurchCollaborationApprovalSerializer(serializers.ModelSerializer):
    """Serializer for approving/rejecting collaborations"""
    
    class Meta:
        model = ChurchCollaboration
        fields = ["status"]

# =====================================================
# Testimony Like Serializers
# =====================================================

class TestimonyLikeSerializer(serializers.ModelSerializer):
    """Serializer for testimony likes"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = TestimonyLike
        fields = ["id", "user", "created_at"]
        read_only_fields = ["id", "created_at"]


# =====================================================
# Programme Serializers
# =====================================================

class ProgrammeSerializer(serializers.ModelSerializer):
    """Serializer complet pour les programmes"""
    church = ChurchSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    event_count = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = Programme
        fields = [
            "id", "church", "title", "description", "cover_image_url",
            "start_date", "end_date", "status", "is_public",
            "duration_in_days", "event_count", "is_active",
            "created_by", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "duration_in_days", "created_by", "created_at", "updated_at"
        ]
    
    def get_event_count(self, obj):
        return obj.get_event_count()
    
    def get_is_active(self, obj):
        return obj.is_active()


class ProgrammeCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un programme"""
    
    class Meta:
        model = Programme
        fields = [
            "title", "description", "cover_image_url",
            "start_date", "end_date", "is_public"
        ]
    
    def validate(self, data):
        """Valider que end_date > start_date"""
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] >= data['end_date']:
                raise serializers.ValidationError(
                    "La date de fin doit être après la date de début"
                )
        return data


class ProgrammeUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour mettre à jour un programme"""
    
    class Meta:
        model = Programme
        fields = [
            "title", "description", "cover_image_url",
            "start_date", "end_date", "status", "is_public"
        ]
    
    def validate(self, data):
        """Valider que end_date > start_date"""
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] >= data['end_date']:
                raise serializers.ValidationError(
                    "La date de fin doit être après la date de début"
                )
        return data


class ProgrammeListSerializer(serializers.ModelSerializer):
    """Serializer simplifié pour lister les programmes"""
    church = serializers.SerializerMethodField()
    event_count = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = Programme
        fields = [
            "id", "church", "title", "cover_image_url",
            "start_date", "end_date", "status", "is_public",
            "duration_in_days", "event_count", "is_active", "created_at"
        ]
    
    def get_church(self, obj):
        return {
            "id": obj.church.id,
            "title": obj.church.title,
            "logo_url": obj.church.logo_url
        }
    
    def get_event_count(self, obj):
        return obj.get_event_count()
    
    def get_is_active(self, obj):
        return obj.is_active()


class ProgrammeContentSerializer(serializers.ModelSerializer):
    """Serializer pour gérer les contenus d'un programme"""
    content_items = ContentListSerializer(many=True, read_only=True)
    event_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Programme
        fields = [
            "id", "title", "description", "start_date", "end_date",
            "status", "is_public", "content_items", "event_count", "created_at"
        ]
    
    def get_event_count(self, obj):
        return obj.get_event_count()


# =====================================================
# Programme Member Serializers
# =====================================================

class ProgrammeMemberSerializer(serializers.ModelSerializer):
    """Serializer pour les membres d'un programme"""
    user = UserSerializer(read_only=True)
    programme_title = serializers.CharField(source='programme.title', read_only=True)
    
    class Meta:
        model = ProgrammeMember
        fields = ["id", "user", "programme_title", "joined_at"]
        read_only_fields = ["id", "joined_at"]


class ProgrammeWithMembersSerializer(serializers.ModelSerializer):
    """Serializer pour afficher un programme avec ses membres"""
    church = ChurchSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    event_count = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    user_is_member = serializers.SerializerMethodField()
    
    class Meta:
        model = Programme
        fields = [
            "id", "church", "title", "description", "cover_image_url",
            "start_date", "end_date", "status", "is_public",
            "duration_in_days", "event_count", "is_active", "member_count",
            "members", "user_is_member", "created_by", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "duration_in_days", "created_by", "created_at", "updated_at"
        ]
    
    def get_event_count(self, obj):
        return obj.get_event_count()
    
    def get_is_active(self, obj):
        return obj.is_active()
    
    def get_member_count(self, obj):
        return obj.get_member_count()
    
    def get_members(self, obj):
        members = obj.members.select_related('user')
        return [{
            "id": m.user.id,
            "name": m.user.name,
            "email": m.user.email,
            "joined_at": m.joined_at
        } for m in members]
    
    def get_user_is_member(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.members.filter(user=request.user).exists()
        return False


# =====================================================
# Content Notification Serializers
# =====================================================

class ContentNotificationSerializer(serializers.ModelSerializer):
    """Serializer pour les notifications de contenu Coming Soon"""
    user = UserSerializer(read_only=True)
    content_title = serializers.CharField(source='content.title', read_only=True)
    content_type = serializers.CharField(source='content.type', read_only=True)
    planned_release_date = serializers.DateTimeField(source='content.planned_release_date', read_only=True)
    
    class Meta:
        model = ContentNotification
        fields = [
            "id", "content", "user", "content_title", "content_type",
            "planned_release_date", "is_notified", "subscribed_at", "notified_at"
        ]
        read_only_fields = [
            "id", "user", "subscribed_at", "notified_at", "is_notified"
        ]


class ContentComingSoonSerializer(serializers.ModelSerializer):
    """Serializer pour les contenus Coming Soon"""
    status = serializers.SerializerMethodField()
    is_coming_soon = serializers.SerializerMethodField()
    user_subscribed = serializers.SerializerMethodField()
    subscriber_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Content
        fields = [
            "id", "title", "description", "cover_image_url",
            "type", "planned_release_date", "created_at",
            "status", "is_coming_soon", "user_subscribed", "subscriber_count"
        ]
    
    def get_status(self, obj):
        return obj.get_status()
    
    def get_is_coming_soon(self, obj):
        return obj.is_coming_soon()
    
    def get_user_subscribed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.notifications.filter(user=request.user).exists()
        return False
    
    def get_subscriber_count(self, obj):
        return obj.notifications.filter(is_notified=False).count()


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "eng_title",
            "eng_message",
            "type",
            "channel",
            "is_read",
            "sent",
            "created_at",
            "sent_at",
            "meta",
        ]
        read_only_fields = fields


# =====================================================
# Programme Content Notification Serializers
# =====================================================

class ProgrammeContentNotificationSerializer(serializers.ModelSerializer):
    """Notification complète avec infos du contenu"""
    content = ContentListSerializer(read_only=True)
    programme_title = serializers.CharField(source='programme.title', read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    
    class Meta:
        model = ProgrammeContentNotification
        fields = [
            'id', 'programme_title', 'content', 'is_notified', 'is_read',
            'created_at', 'notified_at', 'read_at'
        ]
        read_only_fields = fields


class ProgrammeContentNotificationListSerializer(serializers.ModelSerializer):
    """Version allégée pour les listes"""
    content_title = serializers.CharField(source='content.title', read_only=True)
    content_type = serializers.CharField(source='content.type', read_only=True)
    programme_id = serializers.CharField(source='programme.id', read_only=True)
    
    class Meta:
        model = ProgrammeContentNotification
        fields = [
            'id', 'programme_id', 'content_title', 'content_type',
            'is_notified', 'is_read', 'created_at'
        ]
        read_only_fields = fields

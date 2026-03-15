from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, F, Count, Exists, OuterRef, Value
from django.utils.text import slugify
from api.permissions import IsAuthenticatedUser, IsSuperAdmin, user_is_church_admin
from api.serializers import CategorySerializer, CommentSerializer, ContentCreateUpdateSerializer, ContentDetailSerializer, ContentListSerializer, PlaylistItemSerializer, PlaylistSerializer, TagSerializer, ContentNotificationSerializer, ContentComingSoonSerializer
# imports communs pour serializers + views
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db import models
import random
# tes modèles (adaptés à ton projet)
from api.models import (
    ChurchAdmin, Content, Category, Tag, ContentTag, Playlist, PlaylistItem,
    ContentView, ContentLike, Comment, Church, User, ContentNotification, Notification
)
from api.models import TicketType
from api.serializers import TicketTypeSerializer
# permissions existantes
from api.permissions import IsAuthenticatedUser
# utilitaires si besoin
from django.utils import timezone
from datetime import timedelta
from itertools import zip_longest
from api.services.notification_preferences import (
    build_in_app_notifications,
    create_in_app_notification,
)


def exclude_coming_soon(queryset):
    """
    Exclure les contenus 'Coming Soon' d'une queryset
    Un contenu est 'coming soon' s'il est publié et sa date prévue > maintenant
    """
    return queryset.exclude(
        published=True,
        planned_release_date__isnull=False,
        planned_release_date__gt=timezone.now()
    )


def annotate_content_metrics(queryset, user=None):
    """
    Annoter les contenus avec des métriques légères pour le feed
    (likes, commentaires, vues, et is_liked pour l'utilisateur courant).
    """
    qs = queryset.annotate(
        likes_count=Count("contentlike", distinct=True),
        comments_count=Count("comment", distinct=True),
        views_count=Count("contentview", distinct=True),
    )

    if user is not None and getattr(user, "is_authenticated", False):
        qs = qs.annotate(
            is_liked=Exists(
                ContentLike.objects.filter(content_id=OuterRef("pk"), user=user)
            )
        )
    else:
        qs = qs.annotate(is_liked=Value(False, output_field=models.BooleanField()))

    return qs


def _user_can_view_church_scope(user, church):
    if getattr(user, "role", None) == "SADMIN":
        return True
    if getattr(user, "current_church_id", None) == church.id:
        return True
    return ChurchAdmin.objects.filter(user=user, church=church).exists()


def _user_can_manage_church_library(user, church):
    if getattr(user, "role", None) == "SADMIN":
        return True
    return ChurchAdmin.objects.filter(
        user=user,
        church=church,
        role__in=["OWNER", "ADMIN"],
    ).exists()


def _build_content_notification_meta(content, *, action, actor=None, extra=None):
    meta = {
        "content_id": str(content.id),
        "content_type": content.type,
        "content_title": content.title,
        "church_id": str(content.church_id),
        "interaction_type": action,
    }
    if actor is not None:
        meta["actor_id"] = str(actor.id)
        meta["actor_name"] = actor.name
    if extra:
        meta.update(extra)
    return meta


def _notify_content_owner(content, *, actor, title, message, action, extra=None):
    owner = content.created_by
    if owner is None or owner.id == actor.id:
        return

    create_in_app_notification(
        user=owner,
        title=title,
        message=message,
        notif_type="INFO",
        category="social",
        meta=_build_content_notification_meta(
            content,
            action=action,
            actor=actor,
            extra=extra,
        ),
    )


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def create_category(request):
    data = request.data.copy()
    if "name" in data:
        data["slug"] = slugify(data["name"])

    serializer = CategorySerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
def list_categories(request):
    categories = Category.objects.all().order_by("name")
    serializer = CategorySerializer(categories, many=True)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def get_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    serializer = CategorySerializer(category)
    return Response(serializer.data)

@api_view(["PUT", "PATCH"])
@permission_classes([IsSuperAdmin])
def update_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)

    data = request.data.copy()
    if "name" in data:
        data["slug"] = slugify(data["name"])

    serializer = CategorySerializer(category, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["DELETE"])
@permission_classes([IsSuperAdmin])
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.delete()
    return Response({"detail": "Category deleted successfully"})

class DefaultPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

# List all content (global or by church) with filters, search, ordering
@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_content(request):
    """
    Query params:
      - church_id
      - type (ARTICLE,AUDIO,EVENT,VIDEO,POST,BOOK)
      - category_id
      - tag (name)
      - search (title/description)
      - ordering (created_at, likes, views) prefixed with - for desc
      - published (true/false)
    """
    qs = Content.objects.all()

    church_id = request.GET.get("church_id")
    ctype = request.GET.get("type")
    category_id = request.GET.get("category_id")
    tag = request.GET.get("tag")
    search = request.GET.get("search")
    published = request.GET.get("published")

    if church_id:
        qs = qs.filter(church_id=church_id)

    if ctype:
        qs = qs.filter(type=ctype)

    if category_id:
        qs = qs.filter(category_id=category_id)

    if tag:
        qs = qs.filter(contenttag__tag__name__icontains=tag)

    if published is not None:
        if published.lower() in ["true","1","yes"]:
            qs = qs.filter(published=True)
        else:
            qs = qs.filter(published=False)

    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

    # Exclure les contenus coming soon
    qs = exclude_coming_soon(qs)

    qs = qs.select_related("church", "created_by", "category").prefetch_related(
        "contenttag_set__tag"
    )
    qs = annotate_content_metrics(qs, request.user)

    ordering = request.GET.get("ordering")
    if ordering:
        prefix = "-" if ordering.startswith("-") else ""
        normalized = ordering.lstrip("-")
        if normalized == "likes":
            ordering = f"{prefix}likes_count"
        elif normalized == "views":
            ordering = f"{prefix}views_count"
        elif normalized == "comments":
            ordering = f"{prefix}comments_count"
        qs = qs.order_by(ordering)
    else:
        qs = qs.order_by("-created_at")

    paginator = DefaultPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ContentListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def retrieve_content(request, content_id):
    obj = get_object_or_404(Content, id=content_id)
    
    # Vérifier si c'est un contenu coming soon
    if obj.is_coming_soon():
        # Seuls les admins de l'église peuvent voir les coming soon
        from api.permissions import user_is_church_admin
        if not user_is_church_admin(request.user, obj.church) and request.user.role != "SADMIN":
            return Response(
                {"error": "Ce contenu n'est pas encore disponible"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    serializer = ContentDetailSerializer(obj)
    return Response(serializer.data)


from django.core.files.storage import default_storage

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def create_content(request,church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    requested_type = request.data.get("type")
    is_member_story = (
        requested_type == "STORY" and request.user.current_church_id == church.id
    )
    if not user_is_church_admin(request.user, church) and not is_member_story:
        return Response({"detail":"Forbidden"}, status=403)
    data = request.data.copy()
    # created_by set to request.user
    data["created_by"] = request.user.id
    data["church"] = church.id
    category_value = request.data.get("category")
    if category_value:
        category = get_object_or_404(Category, id=category_value)
        data["category"] = category.id
    if not data.get("slug"):
        data["slug"] = slugify(data.get("title", ""))

    if "file" in request.FILES:
        uploaded_file = request.FILES["file"]
        file_name = default_storage.save(f"uploads/{uploaded_file.name}", uploaded_file)
        file_url = request.build_absolute_uri(default_storage.url(file_name))
        data["file"] = file_url
        content_type = getattr(uploaded_file, "content_type", "") or ""
        if content_type.startswith("audio/") and not data.get("audio_url"):
            data["audio_url"] = file_url
        elif content_type.startswith("video/") and not data.get("video_url"):
            data["video_url"] = file_url
        if (
            content_type.startswith("image/")
            and not data.get("cover_image_url")
        ):
            data["cover_image_url"] = file_url
        
    serializer = ContentCreateUpdateSerializer(data=data)
    if serializer.is_valid():
        content = serializer.save()
        # handle tags if provided as comma separated or list
        tags = request.data.get("tags")
        if tags:
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            for t in tags:
                tag_obj, _ = Tag.objects.get_or_create(name=t, defaults={"slug": t.lower().replace(" ","-")})
                ContentTag.objects.get_or_create(content=content, tag=tag_obj)
        should_notify_members = (
            getattr(content, "published", False)
            and content.type in {"EVENT", "POST", "ARTICLE", "VIDEO", "AUDIO", "BOOK"}
        )
        if should_notify_members:
            recipients = User.objects.filter(current_church=church).exclude(id=request.user.id)
            if content.type == "EVENT":
                notif_title = f"Nouvel evenement: {content.title}"
                notif_message = (
                    f"{church.title} a publie un nouvel evenement"
                    + (f" a {content.location}" if content.location else "")
                    + "."
                )
            else:
                notif_title = f"Nouveau contenu: {content.title}"
                notif_message = f"{church.title} a publie un nouveau contenu."

            notifications = build_in_app_notifications(
                recipients,
                title=notif_title,
                message=notif_message,
                notif_type="SUCCESS",
                category="content",
                meta={
                    "content_id": str(content.id),
                    "content_type": content.type,
                    "church_id": str(church.id),
                    "is_public": bool(content.is_public),
                },
            )
            if notifications:
                Notification.objects.bulk_create(notifications)
        return Response(ContentDetailSerializer(content).data, status=201)
    return Response(serializer.errors, status=400)


@api_view(["PUT","PATCH"])
@permission_classes([IsAuthenticatedUser])
def update_content(request, content_id):
    obj = get_object_or_404(Content, id=content_id)
    # check permission: creator or church admin or SADMIN (you can implement strict check)
    if request.user != obj.created_by and request.user.role != "SADMIN":
        # also allow church owner/admin check
        if not ChurchAdmin.objects.filter(church=obj.church, user=request.user).exists():
            return Response({"detail":"Forbidden"}, status=403)
    serializer = ContentCreateUpdateSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        content = serializer.save()
        return Response(ContentDetailSerializer(content).data)
    return Response(serializer.errors, status=400)


@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_content(request, content_id):
    obj = get_object_or_404(Content, id=content_id)
    if request.user != obj.created_by and request.user.role != "SADMIN":
        if not ChurchAdmin.objects.filter(church=obj.church, user=request.user).exists():
            return Response({"detail":"Forbidden"}, status=403)
    obj.delete()
    return Response({"detail":"deleted"})

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def toggle_like_content(request, content_id):
    content = get_object_or_404(Content, id=content_id)
    like = ContentLike.objects.filter(user=request.user, content=content).first()
    if like:
        like.delete()
        liked = False
    else:
        ContentLike.objects.create(user=request.user, content=content)
        liked = True
        _notify_content_owner(
            content,
            actor=request.user,
            title=f"Nouveau like sur {content.title}",
            message=f"{request.user.name} a aime votre contenu.",
            action="LIKE",
        )

    return Response({
        "liked": liked,
        "likes_count": ContentLike.objects.filter(content=content).count(),
    })

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def report_content(request, content_id):
    # Dummy implementation for reporting
    content = get_object_or_404(Content, id=content_id)
    reason = request.data.get("reason", "Pas de raison")
    return Response(
        {
            "reported": True,
            "content_id": str(content.id),
            "reason": reason,
        }
    )

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def view_content(request, content_id):
    content = get_object_or_404(Content, id=content_id)
    # Create a new view record on each call so a user can view multiple times (YouTube-like)
    ContentView.objects.create(user=request.user, content=content)
    source = request.data.get("source")
    if source == "SHARE":
        _notify_content_owner(
            content,
            actor=request.user,
            title=f"Contenu partage: {content.title}",
            message=f"{request.user.name} a partage votre contenu.",
            action="SHARE",
            extra={"source": source},
        )
    elif source == "STORY_SHARE":
        _notify_content_owner(
            content,
            actor=request.user,
            title=f"Partage en story: {content.title}",
            message=f"{request.user.name} a partage votre contenu en story.",
            action="STORY_SHARE",
            extra={"source": source},
        )
    return Response({"viewed": True})

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_comments(request, content_id):
    qs = Comment.objects.filter(content_id=content_id).order_by("-created_at")
    paginator = DefaultPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = CommentSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def add_comment(request, content_id):
    text = request.data.get("text")
    if not text:
        return Response({"error":"text required"}, status=400)
    content = get_object_or_404(Content, id=content_id)
    c = Comment.objects.create(user=request.user, content=content, text=text)
    _notify_content_owner(
        content,
        actor=request.user,
        title=f"Nouveau commentaire sur {content.title}",
        message=f"{request.user.name} a commente votre contenu.",
        action="COMMENT",
        extra={"comment_id": str(c.id)},
    )
    return Response(CommentSerializer(c).data, status=201)

@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_comment(request, comment_id):
    c = get_object_or_404(Comment, id=comment_id)
    if c.user != request.user and request.user.role != "SADMIN":
        return Response({"error":"forbidden"}, status=403)
    c.delete()
    return Response({"deleted": True})


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_tags(request):
    qs = Tag.objects.all()
    serializer = TagSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser, IsSuperAdmin])
def create_tag(request):
    name = request.data.get("name")
    if not name:
        return Response({"error":"name required"}, status=400)
    tag, created = Tag.objects.get_or_create(name=name, defaults={"slug": name.lower().replace(" ","-")})
    return Response(TagSerializer(tag).data, status=201 if created else 200)

@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser])
def update_tag(request, tag_id):
    # Vérifie que l'utilisateur est SADMIN
    data = request.data.copy()
    if request.user.role != "SADMIN":
        return Response({"detail": "Forbidden"}, status=403)
    
    tag = get_object_or_404(Tag, id=tag_id)
    if "name" in data:
        data["slug"] = slugify(data["name"])
    serializer = TagSerializer(tag, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_tag(request, tag_id):
    if request.user.role != "SADMIN":
        return Response({"detail": "Forbidden"}, status=403)
    
    tag = get_object_or_404(Tag, id=tag_id)
    tag.delete()
    return Response({"detail": "Tag deleted"}, status=204)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def create_playlist(request):
    data = request.data.copy()
    church_id = request.data.get("church_id")
    if not church_id:
        return Response({"detail": "church_id is required"}, status=400)

    # Ensure church exists and is verified
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    if not _user_can_manage_church_library(request.user, church):
        return Response({"detail": "Forbidden"}, status=403)

    # Use serializer for validation but pass the actual Church instance on save
    serializer = PlaylistSerializer(data=data)
    if serializer.is_valid():
        pl = serializer.save(church=church)
        return Response(PlaylistSerializer(pl).data, status=201)
    return Response(serializer.errors, status=400)

@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def add_to_playlist(request, playlist_id):
    playlist = get_object_or_404(Playlist, id=playlist_id)
    if not _user_can_manage_church_library(request.user, playlist.church):
        return Response({"detail": "Forbidden"}, status=403)
    content_id = request.data.get("content_id")
    pos = request.data.get("position", 0)

    if not content_id:
        return Response({"detail": "content_id is required"}, status=400)

    content = get_object_or_404(Content, id=content_id)
    if content.church_id != playlist.church_id:
        return Response(
            {"detail": "Content must belong to the same church as the playlist"},
            status=400,
        )

    # Vérifie si le contenu est déjà dans la playlist
    item, created = PlaylistItem.objects.get_or_create(
        playlist=playlist,
        content=content,
        defaults={"position": pos}
    )

    if not created:
        return Response({"detail": "This content is already in the playlist"}, status=400)

    return Response(PlaylistItemSerializer(item).data, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def reorder_playlist_item(request, item_id):
    # Récupère l'item
    item = get_object_or_404(PlaylistItem, id=item_id)
    playlist = item.playlist
    if not _user_can_manage_church_library(request.user, playlist.church):
        return Response({"detail": "Forbidden"}, status=403)

    # Récupère le nouveau rang demandé
    try:
        new_pos = int(request.data.get("position", item.position))
    except (TypeError, ValueError):
        return Response({"detail": "Invalid position"}, status=400)

    # Limite la position dans la plage valide
    playlist_items = list(PlaylistItem.objects.filter(playlist=playlist).order_by("position"))
    max_index = len(playlist_items) - 1
    new_pos = max(0, min(new_pos, max_index))

    # Supprime l'item de sa position actuelle
    playlist_items.remove(item)
    # Insère l'item à la nouvelle position
    playlist_items.insert(new_pos, item)

    # Réattribue les positions pour éviter les doublons
    for index, it in enumerate(playlist_items):
        if it.position != index:
            it.position = index
            it.save(update_fields=["position"])

    return Response(PlaylistItemSerializer(item).data)



@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def trending_content(request, church_id):
    qs = Content.objects.filter(church_id=church_id)
    
    # Exclure les coming soon AVANT de scorer/trier
    qs = exclude_coming_soon(qs)

    qs = annotate_content_metrics(
        qs.select_related("church", "created_by", "category").prefetch_related(
            "contenttag_set__tag"
        ),
        request.user,
    )
    qs = qs.annotate(score=F("views_count") + F("likes_count") * 2).order_by("-score")[:20]

    serializer = ContentListSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def recommend_for_user(request,church_id):
    # Récupérer les derniers contenus vus par l'utilisateur dans cette église
    last_views_qs = (
        ContentView.objects
        .filter(user=request.user, content__church_id=church_id)
        .order_by("-viewed_at")[:50]
    )
    last_content_ids = list(last_views_qs.values_list("content_id", flat=True))

    # Si pas de vues récentes, fallback sur trending/latest
    if not last_content_ids:
        qs = Content.objects.filter(church_id=church_id, published=True, is_public=True)
        qs = exclude_coming_soon(qs)
        qs = annotate_content_metrics(
            qs.select_related("church", "created_by", "category").prefetch_related(
                "contenttag_set__tag"
            ),
            request.user,
        )
        qs = qs.order_by("-views_count", "-likes_count")[:20]
        serializer = ContentListSerializer(qs, many=True)
        return Response(serializer.data)

    # Récupérer les tags les plus fréquents dans ces contenus
    tag_counts = (
        ContentTag.objects.filter(content_id__in=last_content_ids)
        .values("tag_id")
        .annotate(freq=Count("id"))
        .order_by("-freq")
    )
    tag_ids = [t["tag_id"] for t in tag_counts]

    # Construire une requête candidate: contenus de la même église, publiés et publics,
    # avec au moins un tag en commun, et que l'utilisateur n'a pas déjà vus
    candidates = Content.objects.filter(
        church_id=church_id,
        published=True,
        is_public=True,
        contenttag__tag_id__in=tag_ids
    ).exclude(id__in=last_content_ids)
    
    # Exclure les coming soon AVANT d'annoter
    candidates = exclude_coming_soon(candidates)
    
    candidates = annotate_content_metrics(
        candidates.select_related("church", "created_by", "category").prefetch_related(
            "contenttag_set__tag"
        ),
        request.user,
    ).annotate(
        tag_matches=Count("contenttag", filter=Q(contenttag__tag_id__in=tag_ids))
    ).distinct()

    # Score simple: prefer contenus avec plus de matching tags, puis vues, puis likes
    qs = candidates.order_by("-tag_matches", "-views_count", "-likes_count")[:20]
    serializer = ContentListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def feed_for_church(request, church_id):
    # Feed PUBLIC - Pas besoin d'authentification
    # Respecter uniquement les contenus publiés et publics (et pas coming soon)
    base_qs = Content.objects.filter(church_id=church_id, published=True, is_public=True)
    base_qs = exclude_coming_soon(base_qs)
    base_qs = annotate_content_metrics(
        base_qs.select_related("church", "created_by", "category").prefetch_related(
            "contenttag_set__tag"
        ),
        request.user,
    )

    # Derniers contenus (récent)
    latest = list(base_qs.order_by("-created_at")[:30])

    used_ids = {c.id for c in latest}

    # Trending : vues sur les 7 derniers jours
    threshold = timezone.now() - timedelta(days=7)
    trending = list(
        base_qs
        .exclude(id__in=used_ids)
        .annotate(views_7d=Count("contentview", filter=Q(contentview__viewed_at__gte=threshold)))
        .order_by("-views_7d")[:20]
    )

    # Interleave latest and trending for diversity (keep latest first)
    items = []
    for a, b in zip_longest(latest, trending):
        if a is not None:
            items.append(a)
        if b is not None:
            items.append(b)

    # Paginate the combined list
    paginator = DefaultPagination()
    page = paginator.paginate_queryset(items, request)
    serializer = ContentListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def content_stats_global(request):
    qs = exclude_coming_soon(Content.objects.all())
    total = qs.count()
    by_type = qs.values("type").annotate(total=Count("id")).order_by("-total")
    by_month = qs.annotate(month=TruncMonth("created_at")).values("month").annotate(count=Count("id")).order_by("month")
    top_liked = qs.annotate(likes=Count("contentlike")).order_by("-likes")[:10].values("id","title","likes")
    return Response({
        "total": total,
        "by_type": list(by_type),
        "by_month": list(by_month),
        "top_liked": list(top_liked)
    })


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def content_stats_for_church(request, church_id):
    church = get_object_or_404(Church, id=church_id)
    if not getattr(church, "is_verified", False):
        return Response({"detail": "Church not verified"}, status=403)
    
    qs = exclude_coming_soon(Content.objects.filter(church=church))
    total = qs.count()
    by_type = qs.values("type").annotate(total=Count("id")).order_by("-total")
    top_liked = qs.annotate(likes=Count("contentlike")).order_by("-likes")[:10].values("id","title","likes")
    views = ContentView.objects.filter(content__church=church, content__in=qs).count()
    return Response({
        "total": total,
        "by_type": list(by_type),
        "top_liked": list(top_liked),
        "views": views
    })

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_all_playlists(request):
    qs = (
        Playlist.objects
        .select_related("church")
        .prefetch_related(
            "playlistitem_set",
            "playlistitem_set__content",
        )
        .order_by("-created_at")
    )
    church_id = request.GET.get("church_id")
    if church_id:
       church = get_object_or_404(Church, id=church_id)
       if not _user_can_view_church_scope(request.user, church):
           return Response({"detail": "Forbidden"}, status=403)
       qs = qs.filter(church_id=church_id)
    elif request.user.role != "SADMIN":
       visible_church_ids = {request.user.current_church_id} if request.user.current_church_id else set()
       visible_church_ids.update(
           ChurchAdmin.objects.filter(user=request.user).values_list("church_id", flat=True)
       )
       qs = qs.filter(church_id__in=visible_church_ids)

    serializer = PlaylistSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def get_playlist_with_items(request, playlist_id):
    playlist = get_object_or_404(Playlist, id=playlist_id)
    if not _user_can_view_church_scope(request.user, playlist.church):
        return Response({"detail": "Forbidden"}, status=403)
    serializer = PlaylistSerializer(playlist)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticatedUser])
def list_ticket_types(request, content_id):
    content = get_object_or_404(Content, id=content_id)
    qs = TicketType.objects.filter(content=content).order_by("name")
    serializer = TicketTypeSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticatedUser])
def create_ticket_type(request, content_id):
    content = get_object_or_404(Content, id=content_id)
    # only content creator, church admin/owner or SADMIN can create ticket types
    if request.user != content.created_by and request.user.role != "SADMIN":
        if not ChurchAdmin.objects.filter(church=content.church, user=request.user).exists():
            return Response({"detail": "Forbidden"}, status=403)

    data = request.data.copy()
    data["content"] = content.id
    serializer = TicketTypeSerializer(data=data)
    if serializer.is_valid():
        tt = serializer.save()
        return Response(TicketTypeSerializer(tt).data, status=201)
    return Response(serializer.errors, status=400)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticatedUser])
def update_ticket_type(request, ticket_type_id):
    tt = get_object_or_404(TicketType, id=ticket_type_id)
    # permission: same as create
    if request.user != tt.content.created_by and request.user.role != "SADMIN":
        if not ChurchAdmin.objects.filter(church=tt.content.church, user=request.user).exists():
            return Response({"detail": "Forbidden"}, status=403)

    serializer = TicketTypeSerializer(tt, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(TicketTypeSerializer(tt).data)
    return Response(serializer.errors, status=400)


@api_view(["DELETE"])
@permission_classes([IsAuthenticatedUser])
def delete_ticket_type(request, ticket_type_id):
    tt = get_object_or_404(TicketType, id=ticket_type_id)
    if request.user != tt.content.created_by and request.user.role != "SADMIN":
        if not ChurchAdmin.objects.filter(church=tt.content.church, user=request.user).exists():
            return Response({"detail": "Forbidden"}, status=403)
    tt.delete()
    return Response({"detail": "deleted"}, status=204)


# =====================================================
# Church Feed (Fil d'actualité)
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def church_feed(request, church_id):
    """
    Fil d'actualité de l'église (style Facebook - pagination infinie)
    Contient :
    - Tous les contenus publiés de l'église (peu importe is_public)
    - Tous les contenus publiés des sous-églises (peu importe is_public)
    - Tous les contenus publiés des églises parentes (peu importe is_public)
    - Seulement les contenus publics ET publiés des églises collaboratrices
    
    Query params:
    - limit: nombre de contenus par requête (défaut 10)
    - offset: position de départ (défaut 0)
    
    Utilisation : GET /api/church/<id>/feed/?limit=10&offset=0
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Église non trouvée"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que l'utilisateur est membre de l'église
    if request.user.current_church_id != church.id and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous devez être membre de cette église pour accéder au fil d'actualité"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    from api.models import ChurchCollaboration
    from django.db.models import Q
    
    # Récupérer les IDs des églises : courante, sous-églises, et parents
    church_ids_internal = [church.id]
    
    # Ajouter les sous-églises
    sub_churches = church.sub_churches.all().values_list('id', flat=True)
    church_ids_internal.extend(sub_churches)
    
    # Ajouter les églises parentes (remonter l'arborescence)
    parent = church.parent
    while parent:
        church_ids_internal.append(parent.id)
        parent = parent.parent
    
    # Récupérer les IDs des églises collaboratrices
    collaborations = ChurchCollaboration.objects.filter(
        Q(initiator_church=church, status="ACCEPTED") |
        Q(target_church=church, status="ACCEPTED")
    )
    
    church_ids_collaborators = []
    for collab in collaborations:
        if collab.initiator_church.id == church.id:
            church_ids_collaborators.append(collab.target_church.id)
        else:
            church_ids_collaborators.append(collab.initiator_church.id)
    
    # Requête pour les iglises internes (pas besoin d'is_public)
    internal_contents = Content.objects.filter(
        church_id__in=church_ids_internal,
        published=True
    )
    
    # Requête pour les églises collaboratrices (besoin d'is_public)
    collaborator_contents = Content.objects.filter(
        church_id__in=church_ids_collaborators,
        is_public=True,
        published=True
    )
    
    # Combiner les deux requêtes
    from django.db.models import Q as DjangoQ
    all_contents = Content.objects.filter(
        DjangoQ(
            church_id__in=church_ids_internal,
            published=True
        ) |
        DjangoQ(
            church_id__in=church_ids_collaborators,
            is_public=True,
            published=True
        )
    ).select_related(
        'church', 'category', 'created_by'
    ).prefetch_related(
        'contenttag_set__tag'
    ).order_by('-created_at').distinct()
    
    # Exclure les contenus coming soon
    all_contents = exclude_coming_soon(all_contents)

    # Filtrer par type de contenu si demandé (ex: POST, ARTICLE, EVENT, AUDIO...)
    content_type = request.query_params.get("type")
    if content_type:
        all_contents = all_contents.filter(type=content_type)
    else:
        # If no type specified, exclude stories from the main feed
        all_contents = all_contents.exclude(type="STORY")

    all_contents = annotate_content_metrics(all_contents, request.user)
    
    # Pagination infinie (offset/limit)
    try:
        limit = int(request.query_params.get('limit', 10))
        offset = int(request.query_params.get('offset', 0))
    except ValueError:
        limit = 10
        offset = 0
    
    # Limiter le limit à 100 pour éviter les abus
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    
    total_count = all_contents.count()
    paginated_contents = all_contents[offset:offset + limit]
    
    serializer = ContentListSerializer(paginated_contents, many=True)
    
    return Response({
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total_count else None,
        "results": serializer.data
    }, status=status.HTTP_200_OK)


# =====================================================
# Content Coming Soon Endpoints
# =====================================================

@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def list_coming_soon(request, church_id):
    """
    Lister tous les contenus 'Coming Soon' d'une église
    Query params: limit, offset, type
    """
    try:
        church = Church.objects.get(id=church_id)
    except Church.DoesNotExist:
        return Response(
            {"error": "Église non trouvée"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que l'utilisateur est membre
    if request.user.current_church_id != church.id and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous devez être membre de cette église"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Récupérer les contenus coming soon
    coming_soon = Content.objects.filter(
        church=church,
        published=True,
        planned_release_date__isnull=False,
        planned_release_date__gt=timezone.now()
    ).select_related('church', 'category', 'created_by').order_by('planned_release_date')
    coming_soon = annotate_content_metrics(coming_soon, request.user)
    
    # Filtrer par type
    content_type = request.query_params.get('type')
    if content_type:
        coming_soon = coming_soon.filter(type=content_type)
    
    # Pagination
    try:
        limit = int(request.query_params.get('limit', 10))
        offset = int(request.query_params.get('offset', 0))
    except ValueError:
        limit = 10
        offset = 0
    
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    total_count = coming_soon.count()
    paginated_contents = coming_soon[offset:offset + limit]
    
    serializer = ContentComingSoonSerializer(
        paginated_contents,
        many=True,
        context={'request': request}
    )
    
    return Response({
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total_count else None,
        "results": serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def subscribe_to_content(request, content_id):
    """
    S'abonner aux notifications pour un contenu Coming Soon
    """
    try:
        content = Content.objects.get(id=content_id)
    except Content.DoesNotExist:
        return Response(
            {"error": "Contenu non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que c'est du coming soon
    if not content.is_coming_soon():
        return Response(
            {"error": "Ce contenu n'est pas Coming Soon"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Vérifier que l'utilisateur n'est pas déjà abonné
    notification, created = ContentNotification.objects.get_or_create(
        content=content,
        user=request.user
    )
    
    if not created:
        return Response(
            {"message": "Vous êtes déjà abonné à ce contenu"},
            status=status.HTTP_200_OK
        )
    
    serializer = ContentNotificationSerializer(notification)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticatedUser])
def unsubscribe_from_content(request, content_id):
    """
    Se désabonner des notifications d'un contenu
    """
    try:
        content = Content.objects.get(id=content_id)
    except Content.DoesNotExist:
        return Response(
            {"error": "Contenu non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        notification = ContentNotification.objects.get(
            content=content,
            user=request.user
        )
    except ContentNotification.DoesNotExist:
        return Response(
            {"error": "Vous n'êtes pas abonné à ce contenu"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    notification.delete()
    
    return Response(
        {"message": "Vous avez été désabonné"},
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def get_my_subscriptions(request):
    """
    Récupérer les contenus auxquels l'utilisateur est abonné
    Query params: limit, offset
    """
    subscriptions = ContentNotification.objects.filter(
        user=request.user,
        is_notified=False
    ).select_related('content').order_by('-subscribed_at')
    
    # Pagination
    try:
        limit = int(request.query_params.get('limit', 10))
        offset = int(request.query_params.get('offset', 0))
    except ValueError:
        limit = 10
        offset = 0
    
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    total_count = subscriptions.count()
    paginated_subs = subscriptions[offset:offset + limit]
    
    serializer = ContentNotificationSerializer(paginated_subs, many=True)
    
    return Response({
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total_count else None,
        "results": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticatedUser])
def get_content_subscribers(request, content_id):
    """
    Récupérer les abonnés d'un contenu (ADMIN ONLY)
    Seuls les admins de l'église peuvent voir qui est abonné à leurs contenus
    
    Query params: limit, offset
    """
    try:
        content = Content.objects.get(id=content_id)
    except Content.DoesNotExist:
        return Response(
            {"error": "Contenu non trouvé"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Vérifier que l'utilisateur est admin de l'église ou SADMIN
    from api.permissions import user_is_church_admin
    if not user_is_church_admin(request.user, content.church) and request.user.role != "SADMIN":
        return Response(
            {"error": "Vous n'avez pas la permission de voir les abonnés de ce contenu"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Récupérer les abonnés
    subscribers = ContentNotification.objects.filter(
        content=content
    ).select_related('user').order_by('-subscribed_at')
    
    # Pagination
    try:
        limit = int(request.query_params.get('limit', 10))
        offset = int(request.query_params.get('offset', 0))
    except ValueError:
        limit = 10
        offset = 0
    
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    total_count = subscribers.count()
    paginated_subscribers = subscribers[offset:offset + limit]
    
    # Créer un serializer custom pour les abonnés avec infos utilisateur
    data = []
    for notification in paginated_subscribers:
        data.append({
            "user_id": notification.user.id,
            "user_name": notification.user.name,
            "user_email": notification.user.email,
            "subscribed_at": notification.subscribed_at,
            "is_notified": notification.is_notified,
            "notified_at": notification.notified_at
        })
    
    return Response({
        "content_id": content_id,
        "content_title": content.title,
        "total_subscribers": total_count,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total_count else None,
        "subscribers": data
    })

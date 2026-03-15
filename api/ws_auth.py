from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken


@database_sync_to_async
def _get_user_from_token(token: str):
    try:
        validated_token = UntypedToken(token)
    except (InvalidToken, TokenError):
        return AnonymousUser()

    user_id_claim = settings.SIMPLE_JWT.get("USER_ID_CLAIM", "user_id")
    user_id = validated_token.get(user_id_claim)
    if not user_id:
        return AnonymousUser()

    User = get_user_model()
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Authentifie un utilisateur Channels via JWT passé en query param:
    ws://host/ws/chat/<room_id>/?token=<access_token>
    """

    async def __call__(self, scope, receive, send):
        user = scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            return await super().__call__(scope, receive, send)

        query_string = scope.get("query_string", b"").decode("utf-8")
        query = parse_qs(query_string)
        token = query.get("token", [None])[0]

        if token:
            scope["user"] = await _get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))

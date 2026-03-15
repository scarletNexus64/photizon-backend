"""
ASGI config for christlumen project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'christlumen.settings')

django_asgi_app = get_asgi_application()

# Import consumers after Django setup
from api.consumers import ChatConsumer
from api.ws_auth import JWTAuthMiddlewareStack

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': JWTAuthMiddlewareStack(
        URLRouter([
            path('ws/chat/<str:room_id>/', ChatConsumer.as_asgi()),
        ])
    ),
})

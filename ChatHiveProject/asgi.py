import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path
from ChatHiveApp.consumers import ChatConsumer
from accounts.auth.ws_jwt import JWTAuthMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ChatHiveProject.settings")

django_asgi_app = get_asgi_application()

websocket_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})

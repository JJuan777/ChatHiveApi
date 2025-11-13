# ChatHiveProject/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ChatHiveProject.settings")

django_asgi_app = get_asgi_application()

# ── WebSocket routing
from ChatHiveApp.routing import websocket_urlpatterns

# Si YA tienes tu JWTAuthMiddleware real, úsalo:
try:
    from accounts.auth.ws_jwt import JWTAuthMiddleware
except Exception:
    from ChatHiveApp.ws_jwt import JWTAuthMiddleware  # fallback de ejemplo

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})

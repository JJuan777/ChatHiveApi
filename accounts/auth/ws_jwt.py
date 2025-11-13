# accounts/auth/ws_jwt.py
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs

User = get_user_model()

class JWTAuthMiddleware:
    """
    Middleware ASGI que extrae el access_token:
      1) De cookies (access_token)
      2) O del subprotocol 'jwt' (fallback)
      3) O querystring ?token=... (último recurso)
    Decodifica el JWT (HS256 por defecto / o RS256 con JWKS si usas claves públicas).
    Inyecta scope['user'].
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            return await self.app(scope, receive, send)

        token = None

        # 1) Cookies
        headers = dict(scope.get("headers", []))
        cookies_raw = headers.get(b"cookie")
        if cookies_raw:
            try:
                cookies = {
                    k.strip(): v for k, v in
                    (c.decode().split("=", 1) for c in cookies_raw.split(b";"))
                }
                token = cookies.get("access_token")
            except Exception:
                pass

        # 2) Subprotocol 'jwt'
        if not token:
            subprotocols = scope.get("subprotocols") or []

            if len(subprotocols) >= 2 and subprotocols[0] == "jwt":
                token = subprotocols[1]

        # 3) Querystring
        if not token:
            qs = parse_qs(scope.get("query_string", b"").decode())
            token = (qs.get("token") or [None])[0]

        scope["user"] = None
        if token:
            try:
                payload = jwt.decode(
                    token,
                    settings.SIMPLE_JWT.get("SIGNING_KEY", settings.SECRET_KEY),
                    algorithms=[settings.SIMPLE_JWT.get("ALGORITHM", "HS256")],
                    options={"verify_aud": False},
                )
                user_id = payload.get("user_id") or payload.get("sub")
                if user_id:
                    try:
                        user = await database_get_user(user_id)
                        scope["user"] = user
                    except Exception:
                        scope["user"] = None
            except Exception:
                scope["user"] = None

        return await self.app(scope, receive, send)

# usuario sin bloquear el loop
from asgiref.sync import sync_to_async

@sync_to_async
def database_get_user(user_id):
    return User.objects.get(pk=user_id)

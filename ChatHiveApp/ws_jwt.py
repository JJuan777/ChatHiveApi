# ChatHiveApp/ws_jwt.py  (o en tu accounts.auth.ws_jwt)
import urllib.parse
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from jwt import decode as jwt_decode, InvalidTokenError
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()

async def get_user_from_token(token: str):
    if not token:
        return AnonymousUser()
    try:
        payload = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except InvalidTokenError:
        return AnonymousUser()
    user_id = payload.get("user_id") or payload.get("id") or payload.get("sub")
    if not user_id:
        return AnonymousUser()
    try:
        return await sync_to_async(User.objects.get)(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers") or [])
        token = None

        # 1) Cookie 'access_token'
        if b"cookie" in headers:
            cookie_str = headers[b"cookie"].decode()
            for part in cookie_str.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    if k == "access_token":
                        token = v
                        break

        # 2) Querystring ?token=
        if not token:
            raw_qs = scope.get("query_string", b"").decode()
            qs = urllib.parse.parse_qs(raw_qs)
            token = (qs.get("token") or [None])[0]

        # 3) Subprotocols: "jwt, <token>"  ó  "<token>"
        if not token and b"sec-websocket-protocol" in headers:
            sp = [x.strip() for x in headers[b"sec-websocket-protocol"].decode().split(",")]
            if len(sp) >= 2 and sp[0].lower() == "jwt":
                token = sp[1]
            elif len(sp) >= 1:
                token = sp[0]

        user = await get_user_from_token(token)
        scope["user"] = user if getattr(user, "is_authenticated", False) else AnonymousUser()
        return await self.app(scope, receive, send)

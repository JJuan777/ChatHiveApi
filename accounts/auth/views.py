from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer, MeSerializer, ChangePasswordSerializer

# ------------ Utilidades para cookies httpOnly ------------
ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 días
COOKIE_FLAGS = {
    "httponly": True,
    "secure": False,               # False = hhtp, True = https
    "samesite": "Lax",
}

def set_auth_cookies(response, access, refresh=None):
    response.set_cookie("access_token", access, max_age=15*60, **COOKIE_FLAGS)
    if refresh:
        response.set_cookie("refresh_token", refresh, max_age=COOKIE_MAX_AGE, **COOKIE_FLAGS)

def clear_auth_cookies(response):
    response.delete_cookie(ACCESS_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME)

# ------------------- Login -------------------
class LoginView(generics.GenericAPIView):
    """
    Login: tokens- cookies httpOnly
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tokens = serializer.validated_data
        access = tokens["access"]
        refresh = tokens["refresh"]
        user_data = tokens["user"]

        # last_seen
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_data["id"])
        user.last_seen = timezone.now()
        user.save(update_fields=["last_seen"])

        resp = Response({"user": user_data}, status=status.HTTP_200_OK)
        set_auth_cookies(resp, access, refresh)

        # incluir tokens en JSON (Bearer):
        # resp.data["access"] = access
        # resp.data["refresh"] = refresh

        return resp


# ------------------- Refresh -------------------
class RefreshCookieView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response({"detail": "No refresh token"}, status=401)
        try:
            refresh = RefreshToken(refresh_token)
            access = str(refresh.access_token)

            new_refresh = str(refresh)
            resp = Response(status=200)
            set_auth_cookies(resp, access, new_refresh)
            return resp
        except Exception:
            return Response({"detail": "Invalid refresh"}, status=401)


class RefreshBearerView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]


# ------------------- Logout (blacklist) -------------------
class LogoutView(APIView):
    """
    Invalida el refresh (blacklist) y limpia cookies.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        # cookies:
        refresh_token = refresh_token or request.COOKIES.get(REFRESH_COOKIE_NAME)
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        resp = Response(status=204)
        clear_auth_cookies(resp)
        return resp


# ------------------- /me (datos del usuario) -------------------
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# ------------------- Cambiar contraseña -------------------
class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Contraseña actualizada."}, status=200)

# accounts/auth/cookie_jwt.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings

ACCESS_COOKIE_NAME = "access_token"

class CookieJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        #  Fallback: cookie
        raw_token = request.COOKIES.get(ACCESS_COOKIE_NAME)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token

from django.urls import path
from .views import (
    LoginView, RefreshCookieView, RefreshBearerView,
    LogoutView, MeView, ChangePasswordView
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth_login"),

    path("refresh/", RefreshCookieView.as_view(), name="auth_refresh_cookie"),
    # path("refresh/", RefreshBearerView.as_view(), name="auth_refresh_bearer"),

    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("me/", MeView.as_view(), name="auth_me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth_change_password"),
]

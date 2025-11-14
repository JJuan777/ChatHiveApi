# ChatHiveProject/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.auth.urls")),
    path("api/", include("ChatHiveApp.urls")),
    path("api/", include("accounts.users.urls")), 
]

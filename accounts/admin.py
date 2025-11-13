# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # ---------- Campos principales ----------
    list_display = (
        "email",
        "display_name",
        "full_name",
        "is_staff",
        "is_active",
        "last_seen",
        "joined_display",
    )
    list_filter = ("is_staff", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name", "display_name")
    ordering = ("-date_joined",)
    date_hierarchy = "date_joined"

    # ---------- Campos para edición ----------
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Información personal", {
            "fields": ("first_name", "last_name", "display_name", "avatar", "status_message"),
        }),
        ("Permisos", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ),
        }),
        ("Tiempos y actividad", {
            "fields": ("date_joined", "last_seen"),
        }),
    )

    # ---------- Campos en formulario de creación ----------
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "first_name", "last_name"),
        }),
    )

    readonly_fields = ("date_joined", "last_seen")

    # ---------- Personalizaciones visuales ----------
    def avatar_preview(self, obj):
        """Miniatura del avatar"""
        if obj.avatar:
            return format_html('<img src="{}" width="40" height="40" style="border-radius:50%;" />', obj.avatar)
        return "—"
    avatar_preview.short_description = "Avatar"

    @admin.display(description="Registrado")
    def joined_display(self, obj):
        return obj.date_joined.strftime("%Y-%m-%d %H:%M") if obj.date_joined else "—"


# Nota: No olvides configurar en settings.py
# AUTH_USER_MODEL = "users.User"

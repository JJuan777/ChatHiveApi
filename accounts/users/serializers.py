# accounts/users/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

class UserListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "avatar",
            "full_name",
            "initials",
            "last_seen",
            "status_message",
        ]

    def get_full_name(self, obj):
        fn = (obj.first_name or "").strip()
        ln = (obj.last_name or "").strip()
        full = f"{fn} {ln}".strip()
        return full or (obj.display_name or "").strip() or obj.email

    def get_initials(self, obj):
        name = self.get_full_name(obj)
        parts = [p for p in name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class UserSuggestSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "title", "subtitle", "avatar", "initials", "last_seen", "status_message"]

    def get_title(self, obj):
        fn = (obj.first_name or "").strip()
        ln = (obj.last_name or "").strip()
        full = f"{fn} {ln}".strip()
        return full or (obj.display_name or "").strip() or obj.email

    def get_subtitle(self, obj):
        return obj.email

    def get_initials(self, obj):
        name = self.get_title(obj)
        parts = [p for p in name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

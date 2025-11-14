# ChatHiveApp/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers
from ChatHiveApp.models import Thread, ThreadMember, Message, MessageType

User = get_user_model()

class UserMiniSerializer(serializers.ModelSerializer):
    display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "display")

    def get_display(self, obj):
        # Ajusta si tu User tiene display_name
        name = getattr(obj, "display_name", None)
        if name:
            return name
        parts = [obj.first_name or "", obj.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or obj.email

class ThreadListSerializer(serializers.ModelSerializer):
    members_count = serializers.IntegerField(read_only=True)
    last_message = serializers.SerializerMethodField()
    peer = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Thread
        fields = (
            "id",
            "kind",
            "title",
            "is_archived",
            "last_message_at",
            "members_count",
            "unread_count",
            "last_message",
            "peer",
        )

    def get_last_message(self, obj: Thread):
        # Usa anotaciones hechas en la view: last_text, last_sender_id, last_created_at
        last_text = getattr(obj, "last_text", None)
        last_sender_id = getattr(obj, "last_sender_id", None)
        last_created_at = getattr(obj, "last_created_at", None)
        if last_text is None and obj.last_message_id is None:
            return None
        return {
            "id": str(obj.last_message_id) if obj.last_message_id else None,
            "text": last_text,
            "sender_id": str(last_sender_id) if last_sender_id else None,
            "created_at": last_created_at,
        }

    def get_peer(self, obj: Thread):
        # Para DIRECT: devuelve el "otro" usuario
        if obj.kind != "DIRECT":
            return None
        request = self.context.get("request")
        me_id = getattr(request.user, "id", None) if request else None
        # Prefetch esperado: members__user
        for m in getattr(obj, "members_all", []):
            if m.user_id != me_id and m.is_active:
                return UserMiniSerializer(m.user).data
        # Si no se prefetchó, intenta básico (último recurso)
        other = obj.members.exclude(user_id=me_id).filter(is_active=True).select_related("user").first()
        return UserMiniSerializer(other.user).data if other else None

class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "thread",
            "sender_id",
            "type",
            "text",
            "meta",
            "reply_to",
            "client_id",
            "created_at",
            "edited_at",
            "deleted_at",
        )
        read_only_fields = ("id", "thread", "sender_id", "created_at", "edited_at", "deleted_at")

    def get_sender_id(self, obj):
        return str(obj.sender_id) if obj.sender_id else None

    def create(self, validated_data):
        # thread viene de la view (URL), sender del request
        request = self.context["request"]
        validated_data["sender"] = request.user
        # type por defecto TEXT si no viene
        validated_data.setdefault("type", MessageType.TEXT)
        return super().create(validated_data)
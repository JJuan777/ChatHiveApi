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


class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.SerializerMethodField()
    sender = UserMiniSerializer(read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "thread",
            "sender_id",
            "sender",
            "type",
            "text",
            "meta",
            "reply_to",
            "client_id",
            "created_at",
            "edited_at",
            "deleted_at",
        )
        read_only_fields = (
            "id",
            "thread",
            "sender_id",
            "sender",
            "created_at",
            "edited_at",
            "deleted_at",
        )

    def get_sender_id(self, obj):
        return str(obj.sender_id) if obj.sender_id else None

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["sender"] = request.user
        validated_data.setdefault("type", MessageType.TEXT)
        return super().create(validated_data)


class ThreadListSerializer(serializers.ModelSerializer):
    """
    Serializer compacto para listar hilos en la sidebar.
    Usa anotaciones hechas en el queryset: last_text, last_sender_id,
    last_created_at, unread_count, etc.
    """

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
            "unread_count",
            "last_message",
            "peer",
            "created_at",
            "updated_at",
        )

    # ── Último mensaje ────────────────────────────────────────────
    def get_last_message(self, obj: Thread):
        # Usa las anotaciones hechas en la view: last_text, last_sender_id, last_created_at
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

    # ── Peer para hilos DIRECT ────────────────────────────────────
    def get_peer(self, obj: Thread):
        """
        Para hilos DIRECT devuelve el "otro" usuario.
        Supone que el Thread tiene:
          - kind = "DIRECT" o "GROUP"
          - related_name="members" en ThreadMember
          - opcionalmente un atributo prefetch 'members_all'
        """
        if getattr(obj, "kind", None) != "DIRECT":
            return None

        request = self.context.get("request")
        me_id = getattr(request.user, "id", None) if request and hasattr(request, "user") else None

        # Si la vista hizo prefetch como:
        #   .prefetch_related(Prefetch("members", queryset=ThreadMember.objects.select_related("user"), to_attr="members_all"))
        members_all = getattr(obj, "members_all", None)
        if members_all is not None:
            for m in members_all:
                if m.user_id != me_id and m.is_active:
                    return UserMiniSerializer(m.user, context=self.context).data

        # Fallback sin prefetch
        other = (
            obj.members.exclude(user_id=me_id)
            .filter(is_active=True)
            .select_related("user")
            .first()
        )
        return (
            UserMiniSerializer(other.user, context=self.context).data
            if other and other.user
            else None
        )

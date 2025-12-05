# ChatHiveApp/api/messages.py
from __future__ import annotations

from django.utils.dateparse import parse_datetime
from django.utils import timezone

from rest_framework import viewsets, permissions
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied
from rest_framework.pagination import PageNumberPagination

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ChatHiveApp.models import (
    Thread,
    Message,
    MessageAudit,
    AuditEvent,
)
from ChatHiveApp.serializers import MessageSerializer
from ChatHiveApp.permissions import IsThreadMember
from ChatHiveApp.consumers import thread_group_name


class ChatMessagePagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 200


class MessageViewSet(viewsets.ModelViewSet):
    """
    GET    /api/chat/threads/<thread_id>/messages/
    POST   /api/chat/threads/<thread_id>/messages/
    PATCH  /api/chat/threads/<thread_id>/messages/<id>/
    DELETE /api/chat/threads/<thread_id>/messages/<id>/
    """

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsThreadMember]
    pagination_class = ChatMessagePagination

    # ── Helpers de hilo ────────────────────────────────────────────
    def get_thread(self) -> Thread:
        thread_id = self.kwargs.get("thread_id")
        try:
            return Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread no encontrado")

    # ── Queryset base para list / retrieve ─────────────────────────
    def get_queryset(self):
        thread = self.get_thread()

        # 👇 NO filtramos por deleted_at; queremos ver también los eliminados
        qs = (
            Message.objects.filter(thread=thread)
            .select_related("sender")
            .order_by("-created_at", "-id")
        )

        before = self.request.query_params.get("before")
        after = self.request.query_params.get("after")

        if before:
            dt = parse_datetime(before)
            if not dt:
                raise ValidationError({"before": "Fecha/hora inválida"})
            qs = qs.filter(created_at__lt=dt)

        if after:
            dt = parse_datetime(after)
            if not dt:
                raise ValidationError({"after": "Fecha/hora inválida"})
            qs = qs.filter(created_at__gt=dt)

        return qs

    # ── Crear mensaje (REST) + broadcast WS ────────────────────────
    def perform_create(self, serializer):
        thread = self.get_thread()

        client_id = self.request.data.get("client_id")

        # Idempotencia por client_id
        if client_id:
            existing = Message.objects.filter(thread=thread, client_id=client_id).first()
            if existing:
                self.instance = existing
                message = existing
            else:
                message: Message = serializer.save(thread=thread)
                self.instance = message
        else:
            message: Message = serializer.save(thread=thread)
            self.instance = message

        # Actualizar último mensaje del hilo
        Thread.objects.filter(id=thread.id).update(
            last_message_id=message.id,
            last_message_at=message.created_at,
        )

        # Broadcast WS
        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        group = thread_group_name(str(thread.id))

        ws_message = {
            "id": str(message.id),
            "thread_id": str(thread.id),
            "sender_id": str(message.sender_id) if message.sender_id else None,
            "text": message.text,
            "type": message.type,
            "created_at": message.created_at.isoformat(),
            "edited_at": message.edited_at.isoformat() if message.edited_at else None,
            "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
        }

        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "thread.event",
                "data": {"type": "message.created", "payload": {"message": ws_message}},
            },
        )

    # ── Editar mensaje (PATCH) ─────────────────────────────────────
    def perform_update(self, serializer):
        message: Message = self.get_object()
        user = self.request.user

        if message.sender_id != user.id:
            raise PermissionDenied("Solo puedes editar tus propios mensajes.")

        old_text = message.text or ""

        message = serializer.save(edited_at=timezone.now())

        new_text = message.text or ""

        if old_text != new_text:
            MessageAudit.objects.create(
                message=message,
                actor=user,
                event=AuditEvent.EDIT,
                old_text=old_text,
                new_text=new_text,
            )

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        group = thread_group_name(str(message.thread_id))

        ws_message = {
            "id": str(message.id),
            "thread_id": str(message.thread_id),
            "sender_id": str(message.sender_id) if message.sender_id else None,
            "text": message.text,
            "type": message.type,
            "created_at": message.created_at.isoformat(),
            "edited_at": message.edited_at.isoformat() if message.edited_at else None,
            "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
        }

        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "thread.event",
                "data": {"type": "message.updated", "payload": {"message": ws_message}},
            },
        )

    # ── Eliminar mensaje (soft delete + audit) ─────────────────────
    def perform_destroy(self, instance: Message):
        user = self.request.user

        if instance.sender_id != user.id:
            raise PermissionDenied("Solo puedes eliminar tus propios mensajes.")

        # Audit
        MessageAudit.objects.create(
            message=instance,
            actor=user,
            event=AuditEvent.DELETE,
            old_text=instance.text or "",
            new_text="",
        )

        # Soft delete
        instance.text = ""
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["text", "deleted_at", "updated_at"])

        thread = instance.thread

        # Recalcular last_message_* solo entre NO eliminados
        try:
            last = (
                Message.objects.filter(thread=thread, deleted_at__isnull=True)
                .order_by("-created_at", "-id")
                .first()
            )
        except Exception:
            last = None

        if last:
            Thread.objects.filter(id=thread.id).update(
                last_message_id=last.id,
                last_message_at=last.created_at,
            )
        else:
            Thread.objects.filter(id=thread.id).update(
                last_message_id=None,
                last_message_at=None,
            )

        # Broadcast de eliminación
        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        group = thread_group_name(str(thread.id))

        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "thread.event",
                "data": {
                    "type": "message.deleted",
                    "payload": {
                        "id": str(instance.id),
                        "thread_id": str(thread.id),
                        "deleted_at": instance.deleted_at.isoformat()
                        if instance.deleted_at
                        else None,
                    },
                },
            },
        )

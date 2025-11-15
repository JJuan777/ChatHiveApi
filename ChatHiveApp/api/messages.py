# ChatHiveApp/api/messages.py
from __future__ import annotations

from django.utils.dateparse import parse_datetime

from rest_framework import viewsets, permissions
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ChatHiveApp.models import Thread, Message
from ChatHiveApp.serializers import MessageSerializer
from ChatHiveApp.permissions import IsThreadMember
from ChatHiveApp.consumers import thread_group_name


class ChatMessagePagination(PageNumberPagination):
  page_size = 50
  page_size_query_param = "page_size"
  max_page_size = 200


class MessageViewSet(viewsets.ModelViewSet):
  """
  GET  /api/chat/threads/<thread_id>/messages/
  POST /api/chat/threads/<thread_id>/messages/
  """

  http_method_names = ["get", "post", "head", "options"]
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

  # ── Queryset base para list ────────────────────────────────────
  def get_queryset(self):
    thread = self.get_thread()

    qs = (
      Message.objects.filter(thread=thread, deleted_at__isnull=True)
      .select_related("sender")
      .order_by("created_at")
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

    # Idempotencia simple por client_id
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

    # ── Broadcast al grupo WebSocket ─────────────────────────────
    channel_layer = get_channel_layer()
    if not channel_layer:
      return  # por si no está configurado channels (tests, etc.)

    group = thread_group_name(str(thread.id))

    # Payload 100% serializable (sin UUID puros)
    ws_message = {
      "id": str(message.id),
      "thread_id": str(thread.id),
      "sender_id": str(message.sender_id) if message.sender_id else None,
      "text": message.text,
      "type": message.type,  # si usas choices Enum/str, sigue siendo serializable
      "created_at": message.created_at.isoformat(),
    }

    async_to_sync(channel_layer.group_send)(
      group,
      {
        "type": "thread.event",  # llama a ChatConsumer.thread_event
        "data": {
          "type": "message.created",
          "payload": {"message": ws_message},
        },
      },
    )

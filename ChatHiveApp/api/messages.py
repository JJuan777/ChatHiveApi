# ChatHiveApp/api/messages.py
from __future__ import annotations

from django.utils.dateparse import parse_datetime

from rest_framework import viewsets, permissions
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination

from ChatHiveApp.models import Thread, Message
from ChatHiveApp.serializers import MessageSerializer
from ChatHiveApp.permissions import IsThreadMember


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

    def get_thread(self):
        thread_id = self.kwargs.get("thread_id")
        try:
            return Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise NotFound("Thread no encontrado")

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

    def perform_create(self, serializer):
        thread = self.get_thread()

        client_id = self.request.data.get("client_id")
        if client_id:
            existing = Message.objects.filter(thread=thread, client_id=client_id).first()
            if existing:
                self.instance = existing
                return

        self.instance = serializer.save(thread=thread)

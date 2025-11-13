from django.db.models import Count, Q, OuterRef, Subquery, F, DateTimeField
from rest_framework import viewsets, permissions
from ChatHiveApp.models import Thread, ThreadMember, Message
from .serializers import ThreadListSerializer
from django.db import models

from django.utils.dateparse import parse_datetime
from django.db.models import Q
from rest_framework import viewsets, permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound, ValidationError

from ChatHiveApp.models import Message, Thread, ThreadMember
from .serializers import MessageSerializer
from .permissions import IsThreadMember

class ThreadViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/chat/threads/           -> lista hilos del usuario
    GET /api/chat/threads?q=texto    -> filtro por título
    GET /api/chat/threads?archived=1 -> incluye archivados
    Ordena por last_message_at desc (con NULLS LAST en la práctica)
    """
    serializer_class = ThreadListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Subquery: last_read_message_id del miembro actual en este thread
        member_sub = ThreadMember.objects.filter(
            thread=OuterRef("pk"), user=user
        ).values("last_read_message_id")[:1]

        # Subquery: created_at del last_read_message
        last_read_at_sub = Message.objects.filter(
            id=Subquery(member_sub)
        ).values("created_at")[:1]

        # Subqueries para último mensaje (a partir de last_message_id)
        last_text_sub = Message.objects.filter(
            id=OuterRef("last_message_id")
        ).values("text")[:1]

        last_sender_id_sub = Message.objects.filter(
            id=OuterRef("last_message_id")
        ).values("sender_id")[:1]

        last_created_at_sub = Message.objects.filter(
            id=OuterRef("last_message_id")
        ).values("created_at")[:1]

        qs = (
            Thread.objects.filter(
                members__user=user,
                members__is_active=True,
            )
            .annotate(
                # miembros activos en el hilo
                members_count=Count("members", filter=Q(members__is_active=True), distinct=True),
                # últimos datos del mensaje
                last_text=Subquery(last_text_sub),
                last_sender_id=Subquery(last_sender_id_sub),
                last_created_at=Subquery(last_created_at_sub),
                # última lectura de ESTE usuario en este thread
                last_read_at=Subquery(last_read_at_sub, output_field=DateTimeField()),
            )
            # unread_count: mensajes posteriores a last_read_at (si null, cuenta todos)
            .annotate(
                unread_count=Count(
                    "messages",
                    filter=Q(messages__created_at__gt=F("last_read_at")) | Q(last_read_at__isnull=True),
                    distinct=True,
                )
            )
            .select_related("created_by")
            .prefetch_related(
                # Para poder calcular el "peer" en serializer sin consultas extra
                models.Prefetch(
                    "members",
                    queryset=ThreadMember.objects.select_related("user").only(
                        "id", "thread_id", "user_id", "is_active", "role",
                        "user__id", "user__email", "user__first_name", "user__last_name"
                    ),
                    to_attr="members_all",
                )
            )
            .order_by("-last_message_at", "-created_at")  # fallback por si no hay mensajes
        )

        # Filtros opcionales
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(created_by__email__icontains=q))

        archived = self.request.query_params.get("archived")
        if archived not in ("1", "true", "True"):
            qs = qs.filter(is_archived=False)

        return qs

class ChatMessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

class MessageViewSet(viewsets.ModelViewSet):
    """
    GET  /api/chat/threads/<thread_id>/messages/
    POST /api/chat/threads/<thread_id>/messages/
    Query params soportados:
      - before=ISO8601   -> mensajes con created_at < before
      - after=ISO8601    -> mensajes con created_at > after
      - page, page_size  -> paginación
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
            Message.objects
            .filter(thread=thread, deleted_at__isnull=True)
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

        # Idempotencia por client_id (si viene)
        client_id = self.request.data.get("client_id")
        if client_id:
            existing = Message.objects.filter(thread=thread, client_id=client_id).first()
            if existing:
                # Devolver el existente como si lo acabáramos de crear
                self.instance = existing
                return

        self.instance = serializer.save(thread=thread)
# ChatHiveApp/api/threads.py
from __future__ import annotations

from django.db import models
from django.db.models import Count, Q, OuterRef, Subquery, F, DateTimeField

from rest_framework import viewsets, permissions

from accounts.models import User
from ChatHiveApp.models import Thread, ThreadMember, Message
from ChatHiveApp.serializers import ThreadListSerializer


# ─────────────────────────────────────────────────────────
# Helpers compartidos
# ─────────────────────────────────────────────────────────
def annotated_queryset_for(user: User):
    """
    Devuelve un queryset de Thread con las mismas anotaciones utilizadas en el listado,
    listo para serializar con ThreadListSerializer.
    """
    member_sub = ThreadMember.objects.filter(
        thread=OuterRef("pk"), user=user
    ).values("last_read_message_id")[:1]

    last_read_at_sub = Message.objects.filter(
        id=Subquery(member_sub)
    ).values("created_at")[:1]

    last_text_sub = Message.objects.filter(
        id=OuterRef("last_message_id")
    ).values("text")[:1]

    last_sender_id_sub = Message.objects.filter(
        id=OuterRef("last_message_id")
    ).values("sender_id")[:1]

    last_created_at_sub = Message.objects.filter(
        id=OuterRef("last_message_id")
    ).values("created_at")[:1]

    return (
        Thread.objects.filter(
            members__user=user,
            members__is_active=True,
        )
        .annotate(
            members_count=Count("members", filter=Q(members__is_active=True), distinct=True),
            last_text=Subquery(last_text_sub),
            last_sender_id=Subquery(last_sender_id_sub),
            last_created_at=Subquery(last_created_at_sub),
            last_read_at=Subquery(last_read_at_sub, output_field=DateTimeField()),
        )
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__created_at__gt=F("last_read_at")) | Q(last_read_at__isnull=True),
                distinct=True,
            )
        )
        .select_related("created_by")
        .prefetch_related(
            models.Prefetch(
                "members",
                queryset=ThreadMember.objects.select_related("user").only(
                    "id",
                    "thread_id",
                    "user_id",
                    "is_active",
                    "role",
                    "user__id",
                    "user__email",
                    "user__first_name",
                    "user__last_name",
                ),
                to_attr="members_all",
            )
        )
    )


class ThreadViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/chat/threads/           -> lista hilos del usuario
    GET /api/chat/threads?q=texto    -> filtro por título
    GET /api/chat/threads?archived=1 -> incluye archivados
    """

    serializer_class = ThreadListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        member_sub = ThreadMember.objects.filter(
            thread=OuterRef("pk"), user=user
        ).values("last_read_message_id")[:1]

        last_read_at_sub = Message.objects.filter(
            id=Subquery(member_sub)
        ).values("created_at")[:1]

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
                members_count=Count("members", filter=Q(members__is_active=True), distinct=True),
                last_text=Subquery(last_text_sub),
                last_sender_id=Subquery(last_sender_id_sub),
                last_created_at=Subquery(last_created_at_sub),
                last_read_at=Subquery(last_read_at_sub, output_field=DateTimeField()),
            )
            .annotate(
                unread_count=Count(
                    "messages",
                    filter=Q(messages__created_at__gt=F("last_read_at")) | Q(last_read_at__isnull=True),
                    distinct=True,
                )
            )
            .select_related("created_by")
            .prefetch_related(
                models.Prefetch(
                    "members",
                    queryset=ThreadMember.objects.select_related("user").only(
                        "id",
                        "thread_id",
                        "user__id",
                        "user__email",
                        "user__first_name",
                        "user__last_name",
                        "is_active",
                        "role",
                    ),
                    to_attr="members_all",
                )
            )
            .order_by("-last_message_at", "-created_at")
        )

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(created_by__email__icontains=q))

        archived = self.request.query_params.get("archived")
        if archived not in ("1", "true", "True"):
            qs = qs.filter(is_archived=False)

        return qs

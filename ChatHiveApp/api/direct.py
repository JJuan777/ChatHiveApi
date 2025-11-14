# ChatHiveApp/api/direct.py
from __future__ import annotations

from django.db import transaction

from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from ChatHiveApp.models import Thread, ThreadMember, Message, MessageType
from ChatHiveApp.serializers import ThreadListSerializer, MessageSerializer
from ChatHiveApp.api.threads import annotated_queryset_for


def ensure_direct_thread(me: User, target: User) -> Thread:
    """
    Busca un hilo DIRECT entre 'me' y 'target'. Si no existe, lo crea.
    Usa direct_key = "minId:maxId" para garantizar unicidad.
    Debe llamarse dentro de transaction.atomic().
    """
    u1, u2 = sorted([str(me.id), str(target.id)])
    direct_key = f"{u1}:{u2}"

    thread = (
        Thread.objects.select_for_update()
        .filter(kind="DIRECT", direct_key=direct_key)
        .first()
    )

    if thread:
        changed = False

        if thread.is_archived:
            thread.is_archived = False
            changed = True

        for user in (me, target):
            tm, created = ThreadMember.objects.select_for_update().get_or_create(
                thread=thread,
                user=user,
                defaults={"is_active": True},
            )
            if not created and not tm.is_active:
                tm.is_active = True
                tm.save(update_fields=["is_active"])
                changed = True

        if changed:
            thread.save(update_fields=["is_archived"])

        return thread

    thread = Thread.objects.create(
        kind="DIRECT",
        created_by=me,
        title="",
        direct_key=direct_key,
    )

    ThreadMember.objects.create(thread=thread, user=me, is_active=True, role="OWNER")
    ThreadMember.objects.create(thread=thread, user=target, is_active=True, role="MEMBER")

    return thread


class DirectThreadResolveView(APIView):
    """
    GET /api/chat/threads/direct/resolve/?user_id=<uuid>
    Devuelve el hilo DIRECT existente entre request.user y user_id (si existe).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        me = request.user
        target_id = request.query_params.get("user_id")
        if not target_id:
            return Response({"user_id": ["Este campo es requerido."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            User.objects.get(id=target_id, is_active=True)
        except User.DoesNotExist:
            return Response({"user_id": ["Usuario no encontrado o inactivo."]}, status=status.HTTP_400_BAD_REQUEST)

        thread = (
            Thread.objects.filter(kind="DIRECT", members__user=me, members__is_active=True)
            .filter(members__user_id=target_id)
            .distinct()
            .first()
        )
        if not thread:
            return Response({"detail": "No existe conversación directa."}, status=status.HTTP_404_NOT_FOUND)

        annotated = annotated_queryset_for(me).filter(id=thread.id).first()
        data = ThreadListSerializer(annotated, context={"request": request}).data
        return Response(data, status=status.HTTP_200_OK)


class DirectSendFirstMessageView(APIView):
    """
    POST /api/chat/threads/direct/send/
    Body: { "user_id": "<uuid>", "text": "hola", "client_id": "<opcional>" }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        me = request.user
        target_id = request.data.get("user_id")
        text = (request.data.get("text") or "").strip()
        client_id = request.data.get("client_id")

        if not target_id:
            return Response({"user_id": ["Este campo es requerido."]}, status=status.HTTP_400_BAD_REQUEST)
        if not text:
            return Response({"text": ["No puede estar vacío."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target = User.objects.get(id=target_id, is_active=True)
        except User.DoesNotExist:
            return Response({"user_id": ["Usuario no encontrado o inactivo."]}, status=status.HTTP_400_BAD_REQUEST)

        if str(target.id) == str(me.id):
            return Response({"user_id": ["No puedes chatear contigo mismo."]}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            thread = ensure_direct_thread(me, target)

            if client_id:
                exists = Message.objects.filter(thread=thread, client_id=client_id).first()
                if exists:
                    annotated = annotated_queryset_for(me).filter(id=thread.id).first()
                    return Response(
                        {
                            "thread": ThreadListSerializer(annotated, context={"request": request}).data,
                            "message": MessageSerializer(exists, context={"request": request}).data,
                        },
                        status=status.HTTP_200_OK,
                    )

            msg = Message.objects.create(
                thread=thread,
                sender=me,
                text=text,
                client_id=client_id or None,
                type=MessageType.TEXT,
            )
            Thread.objects.filter(id=thread.id).update(
                last_message_id=msg.id,
                last_message_at=msg.created_at,
            )

        annotated = annotated_queryset_for(me).filter(id=thread.id).first()
        return Response(
            {
                "thread": ThreadListSerializer(annotated, context={"request": request}).data,
                "message": MessageSerializer(msg, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )

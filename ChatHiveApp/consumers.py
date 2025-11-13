# ChatHiveApp/consumers.py
from __future__ import annotations

from typing import Dict, Set
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from ChatHiveApp.models import (
    Thread,
    ThreadMember,
    Message,
    MessageType,
)

# ─────────────────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────────────────
def thread_group_name(thread_id: str) -> str:
    return f"thread_{thread_id}"


# ─────────────────────────────────────────────────────────
# Consumer
# ─────────────────────────────────────────────────────────
class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Protocolo de mensajes (JSON):
      -> Cliente → Servidor
        { "type": "thread.join",  "payload": { "thread_id": "<uuid>" } }
        { "type": "thread.leave", "payload": { "thread_id": "<uuid>" } }
        { "type": "message.send", "payload": { "thread_id": "<uuid>", "text": "...", "client_id": "<uuid-opcional>" } }
        { "type": "typing.start", "payload": { "thread_id": "<uuid>" } }
        { "type": "typing.stop",  "payload": { "thread_id": "<uuid>" } }

      <- Servidor → Cliente
        { "type": "ready", "payload": { "user_id": "<id>" } }
        { "type": "thread.joined", "payload": { "thread_id": "<uuid>" } }
        { "type": "thread.left", "payload": { "thread_id": "<uuid>" } }
        { "type": "error", "payload": { "code": "FORBIDDEN|BAD_REQUEST|...", "detail": "..." } }
        { "type": "message.ack", "payload": { "client_id": "<uuid|None>", "id": "<uuid>", "thread_id": "<uuid>" } }
        { "type": "message.created", "payload": { "message": { ... } } }
        { "type": "typing", "payload": { "thread_id": "<uuid>", "user_id": "<id>", "status": "start|stop" } }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self._joined_groups: Set[str] = set()  # Siempre existe, aunque falle connect

    async def connect(self):
        user = self.scope.get("user")
        print("🔍 CONNECT attempt, user =", getattr(user, "username", None))

        if not user or isinstance(user, AnonymousUser):
            print("❌ WS: usuario anónimo, cerrando conexión")
            await self.close(code=4401)  # Unauthorized
            return

        self.user = user
        print(f"✅ WS: usuario autenticado {self.user}")

        await self.accept()
        await self.send_json({"type": "ready", "payload": {"user_id": str(self.user.id)}})

    async def disconnect(self, code):
        # Salir de todos los grupos suscritos en esta conexión
        for g in list(self._joined_groups):
            try:
                await self.channel_layer.group_discard(g, self.channel_name)
            except Exception:
                pass
        self._joined_groups.clear()

    # ── Entrada cliente
    async def receive_json(self, data, **kwargs):
        t = data.get("type")
        p = data.get("payload") or {}

        try:
            if t == "thread.join":
                await self._handle_thread_join(p)

            elif t == "thread.leave":
                await self._handle_thread_leave(p)

            elif t == "message.send":
                await self._handle_message_send(p)

            elif t == "typing.start":
                await self._handle_typing(p, status="start")

            elif t == "typing.stop":
                await self._handle_typing(p, status="stop")

            else:
                await self._send_error("BAD_REQUEST", f"Unknown type: {t}")

        except Exception as e:
            # En producción conviene no exponer detalles internos
            await self._send_error("SERVER_ERROR", str(e))

    # ── Handlers
    async def _handle_thread_join(self, payload: Dict):
        thread_id = payload.get("thread_id")
        if not thread_id:
            await self._send_error("BAD_REQUEST", "thread_id es requerido")
            return

        # Validar UUID format
        try:
            UUID(str(thread_id))
        except Exception:
            await self._send_error("BAD_REQUEST", "thread_id inválido")
            return

        # Validar membresía
        if not await self._user_in_thread(self.user.id, thread_id):
            await self._send_error("FORBIDDEN", "No eres miembro de este hilo")
            return

        group = thread_group_name(thread_id)
        if group not in self._joined_groups:
            await self.channel_layer.group_add(group, self.channel_name)
            self._joined_groups.add(group)

        await self.send_json({"type": "thread.joined", "payload": {"thread_id": thread_id}})

    async def _handle_thread_leave(self, payload: Dict):
        thread_id = payload.get("thread_id")
        if not thread_id:
            await self._send_error("BAD_REQUEST", "thread_id es requerido")
            return

        group = thread_group_name(thread_id)
        if group in self._joined_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
            self._joined_groups.discard(group)

        await self.send_json({"type": "thread.left", "payload": {"thread_id": thread_id}})

    async def _handle_message_send(self, payload: Dict):
        thread_id = payload.get("thread_id")
        text = (payload.get("text") or "").strip()
        client_id = payload.get("client_id")

        if not thread_id:
            await self._send_error("BAD_REQUEST", "thread_id es requerido")
            return
        if not text:
            await self._send_error("BAD_REQUEST", "text no puede estar vacío")
            return

        # Validar membresía
        if not await self._user_in_thread(self.user.id, thread_id):
            await self._send_error("FORBIDDEN", "No eres miembro de este hilo")
            return

        # Persistir (con idempotencia por client_id)
        msg = await self._create_or_get_message(thread_id, self.user.id, text, client_id)

        # ACK inmediato al emisor (reconciliar client_id → id)
        await self.send_json({
            "type": "message.ack",
            "payload": {"client_id": client_id, "id": str(msg.id), "thread_id": thread_id},
        })

        # Broadcast al grupo
        group = thread_group_name(thread_id)
        event = {
            "type": "thread.event",
            "data": {
                "type": "message.created",
                "payload": {
                    "message": {
                        "id": str(msg.id),
                        "thread_id": thread_id,
                        "sender_id": str(msg.sender_id) if msg.sender_id else None,
                        "text": msg.text,
                        "type": msg.type,
                        "created_at": msg.created_at.isoformat(),
                    }
                },
            },
        }
        await self.channel_layer.group_send(group, event)

    async def _handle_typing(self, payload: Dict, status: str):
        thread_id = payload.get("thread_id")
        if not thread_id:
            await self._send_error("BAD_REQUEST", "thread_id es requerido")
            return

        if not await self._user_in_thread(self.user.id, thread_id):
            await self._send_error("FORBIDDEN", "No eres miembro de este hilo")
            return

        # Notificar al grupo (sin persistencia)
        group = thread_group_name(thread_id)
        await self.channel_layer.group_send(
            group,
            {
                "type": "thread.event",
                "data": {
                    "type": "typing",
                    "payload": {"thread_id": thread_id, "user_id": str(self.user.id), "status": status},
                },
            },
        )

    # ── Fan-out handler (desde group_send)
    async def thread_event(self, event):
        # Reenvía tal cual el payload
        await self.send_json(event["data"])

    # ── Helpers de envío de errores
    async def _send_error(self, code: str, detail: str):
        await self.send_json({"type": "error", "payload": {"code": code, "detail": detail}})

    # ── Helpers DB (async)
    @database_sync_to_async
    def _user_in_thread(self, user_id, thread_id) -> bool:
        return ThreadMember.objects.filter(
            user_id=user_id, thread_id=thread_id, is_active=True
        ).exists()

    @database_sync_to_async
    def _create_or_get_message(self, thread_id, user_id, text, client_id=None) -> Message:
        """
        Idempotencia:
          - Si llega client_id y ya existe (UniqueConstraint en (thread, client_id)), regresa el existente.
          - Si no, crea el mensaje y actualiza last_message_* del Thread.
        """
        if client_id:
            existing = Message.objects.filter(thread_id=thread_id, client_id=client_id).first()
            if existing:
                return existing

        with transaction.atomic():
            try:
                msg = Message.objects.create(
                    thread_id=thread_id,
                    sender_id=user_id,
                    type=MessageType.TEXT,
                    text=text,
                    client_id=client_id,
                )
            except IntegrityError:
                # colisión por client_id concurrente (otro proceso lo creó primero)
                msg = Message.objects.get(thread_id=thread_id, client_id=client_id)

            Thread.objects.filter(id=thread_id).update(
                last_message_at=timezone.now(),
                last_message_id=msg.id,
            )
            return msg

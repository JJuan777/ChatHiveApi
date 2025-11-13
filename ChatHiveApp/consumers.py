from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from asgiref.sync import sync_to_async

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser):
            await self.close(code=4401)  # Unauthorized
            return
        self.user = user
        await self.accept()
        await self.send_json({"type": "ready", "payload": {"user_id": str(self.user.id)}})

    async def receive_json(self, data, **kwargs):
        t = data.get("type")
        p = data.get("payload") or {}

        if t == "thread.join":
            thread_id = p.get("thread_id")
            if not await user_in_thread(self.user.id, thread_id):
                return
            self.thread_group = f"thread_{thread_id}"
            await self.channel_layer.group_add(self.thread_group, self.channel_name)
            await self.send_json({"type":"thread.joined","payload":{"thread_id":thread_id}})

        elif t == "message.send":
            # aquí validar permisos/persistir mensaje en DB
            msg = {
                "id": p.get("client_id"),
                "thread_id": p["thread_id"],
                "sender_id": str(self.user.id),
                "text": p.get("text",""),
            }
            await self.channel_layer.group_send(
                f"thread_{p['thread_id']}",
                {"type": "thread.event", "data": {"type": "message.created", "payload": {"message": msg}}}
            )

    async def thread_event(self, event):
        await self.send_json(event["data"])

    async def disconnect(self, code):
        if hasattr(self, "thread_group"):
            await self.channel_layer.group_discard(self.thread_group, self.channel_name)

# Simulación de permiso (reemplaza con query real)
@sync_to_async
def user_in_thread(user_id, thread_id):
    from ChatHiveApp.models import ThreadMember
    return ThreadMember.objects.filter(user_id=user_id, thread_id=thread_id, is_active=True).exists()

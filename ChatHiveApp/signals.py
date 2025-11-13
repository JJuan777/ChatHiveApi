# ChatHiveApp/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone
from .models import Message, Thread

def thread_group_name(thread_id):
    return f"thread_{thread_id}"

@receiver(post_save, sender=Message)
def fanout_message(sender, instance: Message, created, **kwargs):
    if not created:
        return
    # Optimizar hilo
    Thread.objects.filter(id=instance.thread_id).update(
        last_message_at=timezone.now(),
        last_message_id=instance.id,
    )
    layer = get_channel_layer()
    payload = {
        "type": "chat.message",
        "message": {
            "id": str(instance.id),
            "thread_id": str(instance.thread_id),
            "sender_id": instance.sender_id,
            "text": instance.text,
            "type": instance.type,
            "created_at": instance.created_at.isoformat(),
        },
    }
    async_to_sync(layer.group_send)(thread_group_name(instance.thread_id), payload)

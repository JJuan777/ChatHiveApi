# ChatHiveApp/models.py
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db.models import Q, UniqueConstraint


# --------------------------------------------
# Base
# --------------------------------------------
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --------------------------------------------
# Thread (conversación)
# --------------------------------------------
class ThreadKind(models.TextChoices):
    DIRECT = "DIRECT", "Direct"
    GROUP = "GROUP", "Group"


class Thread(TimeStampedModel):
    """
    - kind: DIRECT (1 a 1) o GROUP (varios)
    - direct_key: para DIRECT, clave determinística "minUserId:maxUserId" -> permite unicidad.
    - last_message_*: optimiza listados (Inbox).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=12, choices=ThreadKind.choices, db_index=True)
    title = models.CharField(max_length=120, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="threads_created"
    )
    is_archived = models.BooleanField(default=False, db_index=True)

    # Para DIRECT: "u1:u2" con ids ordenados; único cuando no es null
    direct_key = models.CharField(
        max_length=128,          # <── antes seguro tenías 64
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Clave determinística para hilos DIRECT (p.ej. '<user1>:<user2>').",
    )

    # Optimizaciones para Inbox
    last_message_at = models.DateTimeField(blank=True, null=True, db_index=True)
    last_message_id = models.UUIDField(blank=True, null=True, editable=False)

    class Meta:
        indexes = [
            models.Index(fields=["kind", "is_archived"]),
            models.Index(fields=["-last_message_at"]),
        ]

    def __str__(self):
        return f"{self.kind} • {self.title or self.id}"


# --------------------------------------------
# Membresía de hilo
# --------------------------------------------
class ThreadMemberRole(models.TextChoices):
    OWNER = "OWNER", "Owner"
    ADMIN = "ADMIN", "Admin"
    MEMBER = "MEMBER", "Member"


class ThreadMember(TimeStampedModel):
    """
    - last_read_message_id: para calcular mensajes no leídos rápidamente
    - is_active: si el usuario salió del grupo, pero se conserva la historia
    """
    id = models.BigAutoField(primary_key=True)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="thread_memberships")
    role = models.CharField(max_length=10, choices=ThreadMemberRole.choices, default=ThreadMemberRole.MEMBER)
    is_active = models.BooleanField(default=True, db_index=True)

    # Notificaciones
    mute_until = models.DateTimeField(blank=True, null=True)

    # Lecturas
    last_read_message_id = models.UUIDField(blank=True, null=True)

    class Meta:
        unique_together = (("thread", "user"),)
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["thread", "role"]),
        ]

    def __str__(self):
        return f"{self.user_id} in {self.thread_id} ({self.role})"


# --------------------------------------------
# Mensajes
# --------------------------------------------
class MessageType(models.TextChoices):
    TEXT = "TEXT", "Text"
    FILE = "FILE", "File"
    SYSTEM = "SYSTEM", "System"


class Message(TimeStampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages_sent"
    )
    type = models.CharField(max_length=10, choices=MessageType.choices, default=MessageType.TEXT, db_index=True)

    text = models.TextField(blank=True, default="")
    meta = models.JSONField(blank=True, default=dict)

    reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies")

    client_id = models.CharField(max_length=64, blank=True, null=True, help_text="Idempotency key from client")

    edited_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["type"]),
        ]
        constraints = [

            UniqueConstraint(
                fields=["thread", "client_id"],
                condition=Q(client_id__isnull=False),
                name="uniq_message_thread_client_id_not_null",
            ),
        ]

    def __str__(self):
        base = f"{self.type} in {self.thread_id}"
        return f"{base} by {self.sender_id or 'system'}"


# --------------------------------------------
# Adjuntos
# --------------------------------------------
def attachment_upload_to(instance, filename: str) -> str:
    # Estructura: attachments/<thread>/<message>/<filename>
    return f"attachments/{instance.message.thread_id}/{instance.message_id}/{filename}"


class Attachment(TimeStampedModel):

    id = models.BigAutoField(primary_key=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")

    file = models.FileField(upload_to=attachment_upload_to, blank=True, null=True)

    storage_key = models.CharField(max_length=300, blank=True, default="")
    file_name = models.CharField(max_length=255, blank=True, default="")
    mime = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)

    # media
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["message"]),
            models.Index(fields=["mime"]),
        ]

    def __str__(self):
        return f"att {self.id} of msg {self.message_id}"


# --------------------------------------------
# Reacciones
# --------------------------------------------
class Reaction(TimeStampedModel):
    """
    - Un usuario puede reaccionar con 1 emoji por mensaje.
    """
    id = models.BigAutoField(primary_key=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=32)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["message", "user", "emoji"], name="uniq_reaction_per_user_per_emoji"),
        ]
        indexes = [
            models.Index(fields=["message"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user_id} {self.emoji} {self.message_id}"


# --------------------------------------------
# Recibos de entrega/lectura
# --------------------------------------------
class ReceiptStatus(models.TextChoices):
    DELIVERED = "DELIVERED", "Delivered"
    READ = "READ", "Read"


class Receipt(TimeStampedModel):

    id = models.BigAutoField(primary_key=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="receipts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="receipts")

    status = models.CharField(max_length=12, choices=ReceiptStatus.choices, db_index=True, default=ReceiptStatus.DELIVERED)
    delivered_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = (("message", "user"),)
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["message", "status"]),
        ]

    def __str__(self):
        return f"rcpt {self.user_id} {self.status} {self.message_id}"


# --------------------------------------------
# Auditoría simple de ediciones/borrados 
# --------------------------------------------
class AuditEvent(models.TextChoices):
    EDIT = "EDIT", "Edit"
    DELETE = "DELETE", "Delete"


class MessageAudit(TimeStampedModel):
    id = models.BigAutoField(primary_key=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.CharField(max_length=10, choices=AuditEvent.choices)
    old_text = models.TextField(blank=True, default="")
    new_text = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["message", "event"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"audit {self.event} msg {self.message_id}"

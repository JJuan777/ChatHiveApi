# chat/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Thread, ThreadMember,
    Message, Attachment, Reaction, Receipt, MessageAudit,
    ThreadKind, ThreadMemberRole, MessageType, ReceiptStatus, AuditEvent
)


# =========================
# Helpers
# =========================
def _fmt_bytes(n: int) -> str:
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} PB"


# =========================
# Inlines
# =========================
class ThreadMemberInline(admin.TabularInline):
    model = ThreadMember
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "role", "is_active", "mute_until", "last_read_message_id", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = (
        "file", "file_name", "mime", "size_hum", "width", "height",
        "storage_key", "sha256", "created_at",
    )
    readonly_fields = ("size_hum", "created_at")

    @admin.display(description="Tamaño")
    def size_hum(self, obj):
        return _fmt_bytes(obj.size)


class ReactionInline(admin.TabularInline):
    model = Reaction
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "emoji", "created_at")
    readonly_fields = ("created_at",)


class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 0
    raw_id_fields = ("user",)
    fields = ("user", "status", "delivered_at", "read_at", "created_at")
    readonly_fields = ("created_at",)


class MessageAuditInline(admin.TabularInline):
    model = MessageAudit
    extra = 0
    raw_id_fields = ("actor",)
    fields = ("actor", "event", "old_text", "new_text", "created_at")
    readonly_fields = ("created_at",)


# =========================
# Thread Admin
# =========================
@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = (
        "id", "kind", "title", "created_by",
        "is_archived", "members_count", "last_message_at",
    )
    list_filter = ("kind", "is_archived")
    search_fields = ("id", "title", "direct_key", "created_by__email", "created_by__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("created_by",)
    inlines = (ThreadMemberInline,)
    actions = ("archive_threads", "unarchive_threads")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("created_by").prefetch_related("members")

    @admin.display(description="Miembros")
    def members_count(self, obj: Thread):
        # evita un .count() adicional si ya está prefetch
        return getattr(obj, "_prefetched_objects_cache", {}).get("members", obj.members.all()).__len__()

    @admin.action(description="Archivar hilos seleccionados")
    def archive_threads(self, request, queryset):
        updated = queryset.update(is_archived=True)
        self.message_user(request, f"{updated} hilo(s) archivado(s).")

    @admin.action(description="Desarchivar hilos seleccionados")
    def unarchive_threads(self, request, queryset):
        updated = queryset.update(is_archived=False)
        self.message_user(request, f"{updated} hilo(s) desarchivado(s).")


# =========================
# Message Admin
# =========================
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id", "thread", "sender", "type",
        "short_text", "created_at", "edited_at", "deleted_at",
    )
    list_filter = ("type", ("deleted_at", admin.EmptyFieldListFilter))
    search_fields = ("id", "text", "client_id", "thread__title", "sender__email", "sender__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("thread", "sender", "reply_to")
    inlines = (AttachmentInline, ReactionInline, ReceiptInline, MessageAuditInline)
    actions = ("soft_delete", "restore_messages")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("thread", "sender")

    @admin.display(description="Texto", ordering="text")
    def short_text(self, obj: Message):
        t = (obj.text or "").strip()
        return (t[:80] + "…") if len(t) > 80 else t or "—"

    @admin.action(description="Borrado lógico (marcar deleted_at=ahora)")
    def soft_delete(self, request, queryset):
        now = timezone.now()
        updated = queryset.filter(deleted_at__isnull=True).update(deleted_at=now)
        self.message_user(request, f"{updated} mensaje(s) marcados como borrados.")

    @admin.action(description="Restaurar mensajes (deleted_at=NULL)")
    def restore_messages(self, request, queryset):
        updated = queryset.filter(deleted_at__isnull=False).update(deleted_at=None)
        self.message_user(request, f"{updated} mensaje(s) restaurados.")


# =========================
# ThreadMember Admin
# =========================
@admin.register(ThreadMember)
class ThreadMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "user", "role", "is_active", "mute_until", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("id", "thread__title", "thread__id", "user__email", "user__username")
    raw_id_fields = ("thread", "user")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("thread", "user")


# =========================
# Attachment Admin
# =========================
@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "file_name", "mime", "size_hum", "image_dims", "created_at")
    list_filter = ("mime",)
    search_fields = ("id", "file_name", "mime", "storage_key", "sha256", "message__id", "message__thread__title")
    raw_id_fields = ("message",)
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("message", "message__thread")

    @admin.display(description="Tamaño")
    def size_hum(self, obj):
        return _fmt_bytes(obj.size)

    @admin.display(description="Dimensiones")
    def image_dims(self, obj):
        if obj.width and obj.height:
            return f"{obj.width}×{obj.height}"
        return "—"


# =========================
# Reaction Admin
# =========================
@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "user", "emoji", "created_at")
    list_filter = ("emoji",)
    search_fields = ("id", "emoji", "message__id", "message__thread__title", "user__email", "user__username")
    raw_id_fields = ("message", "user")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("message", "message__thread", "user")


# =========================
# Receipt Admin
# =========================
@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "user", "status", "delivered_at", "read_at", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "message__id", "message__thread__title", "user__email", "user__username")
    raw_id_fields = ("message", "user")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("message", "message__thread", "user")


# =========================
# MessageAudit Admin
# =========================
@admin.register(MessageAudit)
class MessageAuditAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "actor", "event", "created_at", "old_short", "new_short")
    list_filter = ("event",)
    search_fields = ("id", "message__id", "actor__email", "actor__username", "old_text", "new_text")
    raw_id_fields = ("message", "actor")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("message", "message__thread", "actor")

    @admin.display(description="Antes")
    def old_short(self, obj):
        t = (obj.old_text or "").strip()
        return (t[:60] + "…") if len(t) > 60 else t or "—"

    @admin.display(description="Después")
    def new_short(self, obj):
        t = (obj.new_text or "").strip()
        return (t[:60] + "…") if len(t) > 60 else t or "—"

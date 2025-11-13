from rest_framework.permissions import BasePermission
from ChatHiveApp.models import ThreadMember

class IsThreadMember(BasePermission):
    """
    Permite acceso solo si el request.user es miembro activo del thread.
    Requiere 'thread_id' en kwargs.
    """
    def has_permission(self, request, view):
        thread_id = view.kwargs.get("thread_id")
        if not thread_id or not request.user or not request.user.is_authenticated:
            return False
        return ThreadMember.objects.filter(
            thread_id=thread_id, user=request.user, is_active=True
        ).exists()

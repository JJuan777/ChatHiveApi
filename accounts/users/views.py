# accounts/users/views.py
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ReadOnlyModelViewSet

from .serializers import UserListSerializer, UserSuggestSerializer

User = get_user_model()

class UserPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

class UserViewSet(ReadOnlyModelViewSet):
    """
    GET /api/users/                -> lista paginada
    GET /api/users/?q=texto        -> búsqueda
    GET /api/users/?exclude_me=1   -> excluye a request.user
    GET /api/users/suggest/?q=ju   -> sugerencias (sin paginar)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserListSerializer
    pagination_class = UserPagination

    def get_queryset(self):
        qs = User.objects.filter(is_active=True).order_by("first_name", "last_name", "email")

        # excluirme
        if self.request.query_params.get("exclude_me", "").lower() in ("1", "true", "yes"):
            qs = qs.exclude(id=self.request.user.id)

        # búsqueda
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(display_name__icontains=q)
            )
        return qs

    @action(detail=False, methods=["GET"], url_path="suggest")
    def suggest(self, request):
        limit = int(request.query_params.get("limit") or 10)
        q = (request.query_params.get("q") or "").strip()
        exclude_me = request.query_params.get("exclude_me", "").lower() in ("1", "true", "yes")

        qs = User.objects.filter(is_active=True)
        if exclude_me and request.user.is_authenticated:
            qs = qs.exclude(id=request.user.id)
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(display_name__icontains=q)
            )

        qs = qs.order_by("-last_seen", "first_name", "last_name")[: max(1, min(limit, 50))]
        data = UserSuggestSerializer(qs, many=True).data
        return Response(data)

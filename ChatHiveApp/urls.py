from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ThreadViewSet, MessageViewSet

# Router principal para los threads
router = DefaultRouter()
router.register(r"chat/threads", ThreadViewSet, basename="chat-threads")

urlpatterns = [
    # Rutas para los mensajes dentro de un thread específico
    path(
        "chat/threads/<uuid:thread_id>/messages/",
        MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="chat-thread-messages",
    ),
]

# Incluye las rutas del router de threads
urlpatterns += router.urls

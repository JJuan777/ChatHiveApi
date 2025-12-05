# ChatHiveApp/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter

from ChatHiveApp.api.threads import ThreadViewSet
from ChatHiveApp.api.messages import MessageViewSet
from ChatHiveApp.api.direct import DirectThreadResolveView, DirectSendFirstMessageView

router = DefaultRouter()
router.register(r"chat/threads", ThreadViewSet, basename="chat-threads")

urlpatterns = [
    # Mensajes de un hilo (lista y creación)
    path(
        # 🔁 CAMBIO: uuid -> str
        "chat/threads/<str:thread_id>/messages/",
        MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="chat-thread-messages",
    ),

    # 🔹 Mensaje individual: editar / eliminar / ver
    path(
        # 🔁 CAMBIO: uuid -> str en ambos
        "chat/threads/<str:thread_id>/messages/<str:pk>/",
        MessageViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="chat-thread-message-detail",
    ),

    # 🔹 Directos: RESOLVE y SEND
    path(
        "chat/threads/direct/resolve/",
        DirectThreadResolveView.as_view(),
        name="chat-thread-direct-resolve",
    ),
    path(
        "chat/threads/direct/send/",
        DirectSendFirstMessageView.as_view(),
        name="chat-thread-direct-send",
    ),
]

# Rutas generadas por el router (lista/detalle de threads)
urlpatterns += router.urls

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class LoginSerializer(TokenObtainPairSerializer):
    """
    Login por email + password.
    Hereda de TokenObtainPairSerializer para generar access/refresh.
    """
    username_field = User.EMAIL_FIELD if hasattr(User, 'EMAIL_FIELD') else 'email'

    def validate(self, attrs):
        # Permite email + password
        email = attrs.get("email") or attrs.get("username")
        password = attrs.get("password")
        if not email or not password:
            raise serializers.ValidationError("Email y password son obligatorios.")

        user = authenticate(request=self.context.get('request'), email=email, password=password)
        if not user or not user.is_active:
            raise serializers.ValidationError("Credenciales inválidas o usuario inactivo.")

        # Genera tokens
        data = super().validate({"email": email, "password": password})
        # respuesta con datos del usuario
        data["user"] = {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
        }
        return data


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name", "first_name", "last_name", "avatar", "status_message", "last_seen")
        read_only_fields = ("id", "email", "last_seen")


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "No coincide."})
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user

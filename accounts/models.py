# accounts/models.py
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email es obligatorio")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser requiere is_staff=True")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser requiere is_superuser=True")
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)

    first_name = models.CharField(max_length=60, blank=True, default="")
    last_name = models.CharField(max_length=60, blank=True, default="")
    display_name = models.CharField(max_length=120, blank=True, default="")
    avatar = models.URLField(blank=True, default="") 

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # chat/presencia
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)
    status_message = models.CharField(max_length=140, blank=True, default="")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        # nombre completo
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.display_name or self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

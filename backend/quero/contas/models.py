import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.gis.db import models as gis_models
from django.db import models

class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, password, **extra_fields)

class Usuario(AbstractUser):
    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    nome = models.CharField(max_length=150)
    telefone = models.CharField(max_length=30, blank=True)
    foto = models.URLField(blank=True)
    ponto = gis_models.PointField(geography=True, srid=4326, null=True, blank=True)
    cep = models.CharField(max_length=9, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    localizacao_atualizada_em = models.DateTimeField(null=True, blank=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]
    objects = UsuarioManager()

    @property
    def reputacao(self):
        from quero.reputacao.models import Avaliacao

        media = Avaliacao.objects.filter(
            avaliado=self,
            publicada_em__isnull=False,
        ).aggregate(media=models.Avg("nota"))["media"]
        return media or 0

    def __str__(self):
        return self.email

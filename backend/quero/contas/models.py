import uuid
from django.utils import timezone
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
    reputacao = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]
    objects = UsuarioManager()

    def __str__(self):
        return self.email

class Localizacao(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="localizacao")
    ponto = gis_models.PointField(geography=True, srid=4326)
    cep = models.CharField(max_length=9, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.cidade}/{self.uf}" if self.cidade and self.uf else str(self.usuario)

class TentativaLogin(models.Model):
    email_hash = models.CharField(max_length=64, primary_key=True)
    falhas = models.PositiveSmallIntegerField(default=0)
    bloqueado_ate = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def esta_bloqueada(self):
        return self.bloqueado_ate is not None and self.bloqueado_ate > timezone.now()

class GeocodificacaoCache(models.Model):
    chave = models.CharField(max_length=64, primary_key=True)
    ponto = gis_models.PointField(geography=True, srid=4326)
    cep = models.CharField(max_length=9, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    atualizada_em = models.DateTimeField(auto_now=True)

class LimiteGeocodificador(models.Model):
    nome = models.CharField(max_length=40, primary_key=True)
    ultima_consulta_em = models.DateTimeField(null=True, blank=True)

class AlteracaoEmailPendente(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="alteracao_email_pendente")
    novo_email = models.EmailField(unique=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expira_em = models.DateTimeField()
    criada_em = models.DateTimeField(auto_now=True)

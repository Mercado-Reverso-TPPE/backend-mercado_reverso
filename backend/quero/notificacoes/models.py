import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Notificacao(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    tipo = models.CharField(max_length=40)
    titulo = models.CharField(max_length=160)
    mensagem = models.TextField(max_length=2000)
    anuncio = models.ForeignKey(
        "anuncios.Anuncio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notificacoes",
    )
    oferta = models.ForeignKey(
        "ofertas.Oferta",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notificacoes",
    )
    negociacao = models.ForeignKey(
        "negociacao.Negociacao",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notificacoes",
    )
    agrupamento = models.CharField(max_length=100, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-criada_em",)
        indexes = [
            models.Index(fields=("usuario", "lida_em", "-criada_em"), name="notificacao_usuario_leitura_idx"),
            models.Index(fields=("usuario", "agrupamento"), name="notificacao_agrupamento_idx"),
        ]


class PreferenciaNotificacao(models.Model):
    class Canal(models.TextChoices):
        APLICATIVO = "aplicativo", "Aplicativo"
        EMAIL = "email", "E-mail"

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferencias_notificacao",
    )
    tipo = models.CharField(max_length=40)
    canal = models.CharField(max_length=12, choices=Canal.choices)
    habilitada = models.BooleanField(default=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "tipo", "canal"),
                name="preferencia_notificacao_unica",
            ),
            models.CheckConstraint(
                condition=~Q(tipo="seguranca_conta") | Q(habilitada=True),
                name="avisos_seguranca_nao_desativaveis",
            ),
        ]

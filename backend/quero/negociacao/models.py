import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Palpite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anuncio = models.ForeignKey(
        "anuncios.Anuncio",
        on_delete=models.CASCADE,
        related_name="palpites",
    )
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="palpites",
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("anuncio", "vendedor"), name="um_palpite_por_vendedor_anuncio"),
            models.CheckConstraint(condition=Q(valor__gt=0), name="palpite_valor_positivo"),
        ]
        indexes = [models.Index(fields=("anuncio", "criado_em"), name="palpite_anuncio_criado_idx")]


class Negociacao(models.Model):
    class Status(models.TextChoices):
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDA = "concluida", "Concluída"
        CANCELADA = "cancelada", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    oferta = models.OneToOneField(
        "ofertas.Oferta",
        on_delete=models.PROTECT,
        related_name="negociacao",
    )
    valor_final = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    status = models.CharField(
        max_length=14,
        choices=Status.choices,
        default=Status.EM_ANDAMENTO,
    )
    conclusao_solicitada_em = models.DateTimeField(null=True, blank=True)
    confirmada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    cancelada_em = models.DateTimeField(null=True, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(valor_final__gt=0), name="negociacao_valor_final_positivo"),
        ]
        indexes = [
            models.Index(fields=("status", "atualizada_em"), name="negociacao_status_atualizada_idx"),
        ]

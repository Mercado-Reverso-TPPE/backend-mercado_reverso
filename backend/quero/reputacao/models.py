import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Avaliacao(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    negociacao = models.ForeignKey(
        "negociacao.Negociacao",
        on_delete=models.PROTECT,
        related_name="avaliacoes",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="avaliacoes_escritas",
    )
    avaliado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="avaliacoes_recebidas",
    )
    nota = models.PositiveSmallIntegerField(validators=(MinValueValidator(1), MaxValueValidator(5)))
    comentario = models.TextField(max_length=2000, blank=True)
    resposta = models.TextField(max_length=2000, blank=True)
    respondida_em = models.DateTimeField(null=True, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    publicada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("negociacao", "autor"),
                name="uma_avaliacao_por_parte_negociacao",
            ),
            models.CheckConstraint(condition=~Q(autor=models.F("avaliado")), name="avaliacao_entre_partes"),
            models.CheckConstraint(
                condition=Q(nota__gte=1) & Q(nota__lte=5),
                name="avaliacao_nota_1_a_5",
            ),
        ]
        indexes = [
            models.Index(fields=("avaliado", "publicada_em"), name="avaliacao_reputacao_idx"),
        ]

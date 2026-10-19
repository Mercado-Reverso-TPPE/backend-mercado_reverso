import uuid

from django.db import models
from django.db.models import Q


class Recomendacao(models.Model):
    class Estado(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        DESCARTADA = "descartada", "Descartada"
        CONVITE_ENVIADO = "convite_enviado", "Convite enviado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anuncio = models.ForeignKey(
        "anuncios.Anuncio",
        on_delete=models.CASCADE,
        related_name="recomendacoes",
    )
    produto = models.ForeignKey(
        "catalogo.Produto",
        on_delete=models.CASCADE,
        related_name="recomendacoes",
    )
    pontuacao = models.DecimalField(max_digits=5, decimal_places=2)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ATIVA)
    calculada_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("anuncio", "produto"), name="recomendacao_unica_anuncio_produto"),
            models.CheckConstraint(
                condition=Q(pontuacao__gte=0) & Q(pontuacao__lte=100),
                name="recomendacao_pontuacao_0_a_100",
            ),
        ]
        indexes = [
            models.Index(fields=("anuncio", "estado", "-pontuacao"), name="recomendacao_feed_idx"),
        ]

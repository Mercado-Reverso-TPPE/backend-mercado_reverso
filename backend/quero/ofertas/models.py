import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator


class Oferta(models.Model):
    class EstadoConservacao(models.TextChoices):
        NOVO = "novo", "Novo"
        SEMINOVO = "seminovo", "Seminovo"
        USADO = "usado", "Usado"

    class Status(models.TextChoices):
        ENVIADA = "enviada", "Enviada"
        ACEITA = "aceita", "Aceita"
        RECUSADA = "recusada", "Recusada"
        RETIRADA = "retirada", "Retirada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anuncio = models.ForeignKey("anuncios.Anuncio", on_delete=models.PROTECT, related_name="ofertas")
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ofertas_enviadas")
    descricao = models.TextField()
    estado_conservacao = models.CharField(max_length=12, choices=EstadoConservacao.choices)
    preco = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ENVIADA)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criada_em",)
        constraints = [
            models.UniqueConstraint(
                fields=("anuncio", "vendedor"),
                condition=Q(status__in=("enviada", "aceita")),
                name="uma_oferta_ativa_por_vendedor_anuncio",
            ),
        ]

    def __str__(self):
        return f"Oferta de {self.vendedor} para {self.anuncio}"


class HistoricoOferta(models.Model):
    oferta = models.ForeignKey(Oferta, on_delete=models.PROTECT, related_name="historico")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="alteracoes_ofertas")
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=12, choices=Oferta.Status.choices)
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("registrado_em",)

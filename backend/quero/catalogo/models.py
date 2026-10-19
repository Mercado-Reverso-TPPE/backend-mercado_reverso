import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Produto(models.Model):
    class EstadoConservacao(models.TextChoices):
        NOVO = "novo", "Novo"
        SEMINOVO = "seminovo", "Seminovo"
        USADO_BOM = "usado_bom", "Usado — bom estado"
        USADO_MARCAS = "usado_marcas", "Usado — com marcas"
        PECAS = "pecas", "Para peças"

    class Status(models.TextChoices):
        DISPONIVEL = "disponivel", "Disponível"
        RESERVADO = "reservado", "Reservado"
        VENDIDO = "vendido", "Vendido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="produtos",
    )
    categoria = models.ForeignKey(
        "anuncios.Categoria",
        on_delete=models.PROTECT,
        related_name="produtos",
    )
    nome = models.CharField(max_length=160)
    descricao = models.TextField()
    estado_conservacao = models.CharField(max_length=16, choices=EstadoConservacao.choices)
    preco = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DISPONIVEL,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        constraints = [
            models.CheckConstraint(condition=Q(preco__gt=0), name="produto_preco_positivo"),
        ]
        indexes = [
            models.Index(fields=("vendedor", "status"), name="produto_vendedor_status_idx"),
            models.Index(fields=("status", "categoria"), name="produto_status_categoria_idx"),
        ]


class FotoProduto(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="fotos")
    arquivo = models.ImageField(upload_to="produtos/%Y/%m/")
    ordem = models.PositiveSmallIntegerField()
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("ordem", "pk")
        constraints = [
            models.UniqueConstraint(fields=("produto", "ordem"), name="foto_produto_ordem_unica"),
        ]

import uuid

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GistIndex
from django.core.exceptions import ValidationError
from django.db import connection, models


class Categoria(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ("nome",)
        verbose_name_plural = "categorias"

    def __str__(self):
        return self.nome


class Anuncio(models.Model):
    class Status(models.TextChoices):
        ATIVO = "ativo", "Ativo"
        PAUSADO = "pausado", "Pausado"
        EM_NEGOCIACAO = "em_negociacao", "Em negociação"
        ENCERRADO = "encerrado", "Encerrado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comprador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="anuncios")
    titulo = models.CharField(max_length=160)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="anuncios")
    descricao = models.TextField()
    preco_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preco_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    raio_m = models.PositiveIntegerField()
    alcance = gis_models.PolygonField(geography=True, srid=4326, editable=False, null=True)
    recomendacoes_solicitadas_em = models.DateTimeField(null=True, blank=True)
    recomendacoes_processando_em = models.DateTimeField(null=True, blank=True)
    recomendacoes_calculadas_em = models.DateTimeField(null=True, blank=True)
    recomendacoes_tentar_em = models.DateTimeField(null=True, blank=True)
    recomendacoes_tentativas = models.PositiveIntegerField(default=0)
    recomendacoes_ultimo_erro = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        indexes = [
            GistIndex(fields=["alcance"], name="anuncio_alcance_gist"),
            models.Index(fields=["status", "categoria"], name="anuncio_status_categoria"),
        ]

    def clean(self):
        if self.preco_min is not None and self.preco_max is not None and self.preco_min > self.preco_max:
            raise ValidationError({"preco_max": "O preço máximo deve ser maior ou igual ao mínimo."})

    def save(self, *args, **kwargs):
        if not self.raio_m or self.raio_m > getattr(settings, "RAIO_MAXIMO_KM", 200) * 1000:
            raise ValidationError({"raio_m": "O raio informado está fora do limite permitido."})
        self.full_clean()
        super().save(*args, **kwargs)
        # The reach polygon is a spatially indexed materialization of buyer location and radius.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE anuncios_anuncio AS anuncio
                SET alcance = ST_Buffer(usuario.ponto, anuncio.raio_m)
                FROM contas_usuario AS usuario
                WHERE anuncio.comprador_id = usuario.id
                  AND anuncio.id = %s
                  AND usuario.ponto IS NOT NULL
                """,
                [str(self.pk)],
            )
        self.refresh_from_db(fields=["alcance"])

    def delete(self, *args, **kwargs):
        if self.status == self.Status.ENCERRADO:
            raise ValidationError("Anúncios encerrados permanecem no histórico.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.titulo

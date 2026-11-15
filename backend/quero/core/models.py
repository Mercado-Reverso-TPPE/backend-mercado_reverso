"""Dados de referência compartilhados, fora do modelo de domínio."""

import unicodedata

from django.contrib.gis.db import models as gis_models
from django.db import models


def normalizar_nome(nome):
    """`"São João d'Aliança"` → `"sao joao d'alianca"`: sem acento, minúsculo e com espaços simples."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.casefold().replace("-", " ").split())


class Municipio(models.Model):
    """Município do IBGE com o ponto da sede: a base local da geolocalização (dado de referência)."""

    codigo_ibge = models.PositiveIntegerField(primary_key=True)
    nome = models.CharField(max_length=80)
    nome_busca = models.CharField(max_length=80, editable=False)
    uf = models.CharField(max_length=2)
    ponto = gis_models.PointField(geography=True, srid=4326)
    capital = models.BooleanField(default=False)

    class Meta:
        ordering = ("uf", "nome")
        indexes = [models.Index(fields=("nome_busca", "uf"), name="municipio_busca_idx")]

    def save(self, *args, **kwargs):
        self.nome_busca = normalizar_nome(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome}/{self.uf}"

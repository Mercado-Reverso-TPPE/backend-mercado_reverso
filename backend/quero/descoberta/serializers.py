from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from quero.anuncios.models import Categoria
from quero.ofertas.models import BuscaSalva

from .models import Recomendacao


def validar_faixa_de_preco(attrs, instancia=None):
    minimo = attrs.get("preco_min", getattr(instancia, "preco_min", None))
    maximo = attrs.get("preco_max", getattr(instancia, "preco_max", None))
    if minimo is not None and maximo is not None and minimo > maximo:
        raise serializers.ValidationError({"preco_max": "O preço máximo deve ser maior ou igual ao mínimo."})
    return attrs


class FiltrosBuscaSerializer(serializers.Serializer):
    q = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    categoria = serializers.SlugRelatedField(
        slug_field="slug", queryset=Categoria.objects.filter(ativa=True), required=False
    )
    preco_min = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    preco_max = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    distancia_max_km = serializers.IntegerField(min_value=1, required=False)
    ordenacao = serializers.ChoiceField(choices=BuscaSalva.Ordenacao.choices, default=BuscaSalva.Ordenacao.DISTANCIA)

    def validate_distancia_max_km(self, valor):
        if valor > settings.RAIO_MAXIMO_KM:
            raise serializers.ValidationError(f"Use no máximo {settings.RAIO_MAXIMO_KM} km.")
        return valor

    def validate(self, attrs):
        return validar_faixa_de_preco(attrs)

    def filtros(self):
        dados = dict(self.validated_data)
        dados["termo"] = dados.pop("q")
        return dados


class BuscaSalvaSerializer(serializers.ModelSerializer):
    categoria = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Categoria.objects.filter(ativa=True),
        required=False,
        allow_null=True,
    )
    preco_min = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    preco_max = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    distancia_max_km = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    class Meta:
        model = BuscaSalva
        fields = (
            "id",
            "nome",
            "termo",
            "categoria",
            "preco_min",
            "preco_max",
            "distancia_max_km",
            "ordenacao",
            "criada_em",
            "atualizada_em",
        )
        read_only_fields = ("id", "criada_em", "atualizada_em")

    def validate_distancia_max_km(self, valor):
        return FiltrosBuscaSerializer().validate_distancia_max_km(valor) if valor is not None else valor

    def validate(self, attrs):
        return validar_faixa_de_preco(attrs, self.instance)


class RecomendacaoSerializer(serializers.ModelSerializer):
    produto_id = serializers.UUIDField(read_only=True)
    nome = serializers.CharField(source="produto.nome", read_only=True)
    categoria = serializers.CharField(source="produto.categoria.slug", read_only=True)
    categoria_nome = serializers.CharField(source="produto.categoria.nome", read_only=True)
    preco = serializers.DecimalField(source="produto.preco", max_digits=10, decimal_places=2, read_only=True)
    estado_conservacao = serializers.CharField(source="produto.estado_conservacao", read_only=True)
    distancia_m = serializers.FloatField(read_only=True)

    class Meta:
        model = Recomendacao
        fields = (
            "id",
            "produto_id",
            "nome",
            "categoria",
            "categoria_nome",
            "preco",
            "estado_conservacao",
            "distancia_m",
            "pontuacao",
            "explicacao",
            "estado",
            "calculada_em",
        )
        read_only_fields = fields

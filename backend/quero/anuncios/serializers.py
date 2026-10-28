from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Anuncio, Categoria
from .services import criar_anuncio


class QuilometrosField(serializers.Field):
    def to_internal_value(self, value):
        try:
            quilometros = int(value)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError("Informe o raio em quilômetros inteiros.") from exc
        if quilometros < 1 or quilometros > settings.RAIO_MAXIMO_KM:
            raise serializers.ValidationError("O raio deve ficar dentro dos limites configurados.")
        return quilometros * 1000

    def to_representation(self, value):
        return value / 1000


class AnuncioSerializer(serializers.ModelSerializer):
    raio_km = QuilometrosField(source="raio_m", required=False)
    distancia_km = serializers.SerializerMethodField()
    categoria = serializers.SlugRelatedField(slug_field="slug", queryset=Categoria.objects.filter(ativa=True))
    categoria_nome = serializers.CharField(source="categoria.nome", read_only=True)
    ofertas_recebidas = serializers.IntegerField(source="ofertas_ativas", read_only=True, default=0)
    cidade = serializers.CharField(source="comprador.cidade", read_only=True)
    uf = serializers.CharField(source="comprador.uf", read_only=True)

    class Meta:
        model = Anuncio
        fields = (
            "id",
            "comprador",
            "titulo",
            "categoria",
            "categoria_nome",
            "descricao",
            "preco_min",
            "preco_max",
            "raio_km",
            "status",
            "distancia_km",
            "ofertas_recebidas",
            "cidade",
            "uf",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = ("id", "comprador", "status", "cidade", "uf", "criado_em", "atualizado_em")

    def get_distancia_km(self, obj):
        distancia = getattr(obj, "distancia_m", None)
        return round(distancia / 1000, 2) if distancia is not None else None

    def validate(self, attrs):
        minimo = attrs.get("preco_min", getattr(self.instance, "preco_min", None))
        maximo = attrs.get("preco_max", getattr(self.instance, "preco_max", None))
        if minimo is not None and maximo is not None and minimo > maximo:
            raise serializers.ValidationError({"preco_max": "O preço máximo deve ser maior ou igual ao mínimo."})
        return attrs

    def create(self, validated_data):
        try:
            return criar_anuncio(comprador=self.context["request"].user, dados=validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ("slug", "nome")
        read_only_fields = fields


class AlteracaoStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(Anuncio.Status.ATIVO, Anuncio.Status.PAUSADO, Anuncio.Status.ENCERRADO))

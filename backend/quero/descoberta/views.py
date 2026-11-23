from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from quero.anuncios.models import Anuncio, Categoria
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


UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)  # fmt: skip

ORDENACOES_PUBLICAS = tuple(
    (valor, rotulo) for valor, rotulo in BuscaSalva.Ordenacao.choices if valor != BuscaSalva.Ordenacao.DISTANCIA
)


class FiltrosPublicosSerializer(serializers.Serializer):
    """Filtros da home pública: os do feed menos a distância, mais a UF (sem UF, o Brasil inteiro)."""

    q = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    uf = serializers.ChoiceField(choices=UFS, required=False, allow_blank=True, default="")
    categoria = serializers.SlugRelatedField(
        slug_field="slug", queryset=Categoria.objects.filter(ativa=True), required=False
    )
    preco_min = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    preco_max = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    ordenacao = serializers.ChoiceField(choices=ORDENACOES_PUBLICAS, default=BuscaSalva.Ordenacao.RECENTES)

    def to_internal_value(self, data):
        # Aceita "sp" na URL, mas guarda sempre a sigla em maiúsculas.
        if hasattr(data, "get") and data.get("uf"):
            data = data.copy()
            data["uf"] = str(data["uf"]).upper()
        return super().to_internal_value(data)

    def validate(self, attrs):
        return validar_faixa_de_preco(attrs)

    def filtros(self, *, com_ordenacao=True):
        dados = dict(self.validated_data)
        dados["termo"] = dados.pop("q")
        if not com_ordenacao:
            dados.pop("ordenacao")
        return dados


class AnuncioPublicoSerializer(serializers.ModelSerializer):
    """O que um visitante pode ver de um anúncio: só o que o card mostra.

    Lista fechada de campos. Nada do comprador, da localização exata, do raio,
    da descrição, das ofertas ou dos palpites.
    """

    categoria = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    categoria_nome = serializers.CharField(source="categoria.nome", read_only=True)

    class Meta:
        model = Anuncio
        fields = ("id", "titulo", "categoria", "categoria_nome", "preco_min", "preco_max", "cidade", "uf", "criado_em")
        read_only_fields = fields


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


class ProdutoDaVitrineSerializer(serializers.Serializer):
    """Produto à venda no feed: dados do catálogo, foto principal, distância e o vendedor."""

    id = serializers.UUIDField()
    nome = serializers.CharField()
    descricao = serializers.CharField()
    categoria = serializers.CharField(source="categoria.slug")
    categoria_nome = serializers.CharField(source="categoria.nome")
    preco = serializers.DecimalField(max_digits=10, decimal_places=2)
    estado_conservacao = serializers.CharField()
    foto = serializers.SerializerMethodField()
    cidade = serializers.CharField(source="vendedor.cidade")
    uf = serializers.CharField(source="vendedor.uf")
    distancia_km = serializers.SerializerMethodField()
    visualizacoes = serializers.SerializerMethodField()
    criado_em = serializers.DateTimeField()
    vendedor_publico = serializers.SerializerMethodField()

    def get_foto(self, obj):
        primeira = next(iter(obj.fotos.all()), None)
        if primeira is None:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(primeira.arquivo.url) if request else primeira.arquivo.url

    def get_distancia_km(self, obj):
        distancia = getattr(obj, "distancia_m", None)
        return round(distancia / 1000, 2) if distancia is not None else None

    def get_visualizacoes(self, obj):
        # O backend ainda não registra visualizações; null deixa o card sem o número.
        return None

    def get_vendedor_publico(self, obj):
        from quero.reputacao.services import resumo_publico

        return resumo_publico(obj.vendedor)


class ContagemPorCategoriaSerializer(serializers.Serializer):
    slug = serializers.CharField()
    total = serializers.IntegerField()


class FiltrosContagemSerializer(FiltrosBuscaSerializer):
    """Os filtros do feed sem categoria nem ordenação: a contagem mostra quanto há em cada categoria."""

    def filtros(self):
        dados = super().filtros()
        dados.pop("categoria", None)
        dados.pop("ordenacao", None)
        return dados


class PropostaVitrineSerializer(serializers.Serializer):
    preco = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    mensagem = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")

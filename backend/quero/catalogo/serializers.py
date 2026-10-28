from decimal import Decimal

from rest_framework import serializers

from quero.anuncios.models import Categoria

from .models import FotoProduto, Produto


class FotoProdutoSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source="arquivo", read_only=True)

    class Meta:
        model = FotoProduto
        fields = ("id", "url", "ordem", "criada_em")
        read_only_fields = fields


class ProdutoSerializer(serializers.ModelSerializer):
    categoria = serializers.SlugRelatedField(slug_field="slug", queryset=Categoria.objects.filter(ativa=True))
    categoria_nome = serializers.CharField(source="categoria.nome", read_only=True)
    preco = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    fotos = FotoProdutoSerializer(many=True, read_only=True)

    class Meta:
        model = Produto
        fields = (
            "id",
            "nome",
            "descricao",
            "categoria",
            "categoria_nome",
            "estado_conservacao",
            "preco",
            "status",
            "fotos",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = ("id", "categoria_nome", "status", "fotos", "criado_em", "atualizado_em")


class UploadFotosSerializer(serializers.Serializer):
    fotos = serializers.ListField(child=serializers.FileField(), allow_empty=False)


class AlteracaoStatusProdutoSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Produto.Status.choices)

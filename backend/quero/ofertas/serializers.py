from rest_framework import serializers

from .models import HistoricoOferta, Oferta


class HistoricoOfertaSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricoOferta
        fields = ("preco", "status", "registrado_em")
        read_only_fields = fields


class OfertaSerializer(serializers.ModelSerializer):
    anuncio_id = serializers.UUIDField(read_only=True)
    vendedor_id = serializers.UUIDField(read_only=True)
    vendedor_nome = serializers.CharField(source="vendedor.nome", read_only=True)
    historico = HistoricoOfertaSerializer(many=True, read_only=True)
    preco = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)

    class Meta:
        model = Oferta
        fields = ("id", "anuncio_id", "vendedor_id", "vendedor_nome", "descricao", "estado_conservacao", "preco", "status", "criada_em", "atualizada_em", "historico")
        read_only_fields = ("id", "anuncio_id", "vendedor_id", "vendedor_nome", "status", "criada_em", "atualizada_em", "historico")

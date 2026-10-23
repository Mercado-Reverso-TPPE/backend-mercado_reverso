from decimal import Decimal

from django.core.files.storage import default_storage
from rest_framework import serializers

from .models import EventoNegociacao, Oferta


class EventoNegociacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoNegociacao
        fields = ("preco", "status", "tipo_evento", "justificativa", "rodada", "registrado_em")
        read_only_fields = fields


class OfertaSerializer(serializers.ModelSerializer):
    anuncio_id = serializers.UUIDField(read_only=True)
    vendedor_id = serializers.UUIDField(read_only=True)
    vendedor_nome = serializers.CharField(source="vendedor.nome", read_only=True)
    historico = serializers.SerializerMethodField()
    preco = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False)
    produto_id = serializers.UUIDField(required=False)
    produto_nome = serializers.CharField(source="nome_produto_snapshot", read_only=True)
    produto_foto = serializers.SerializerMethodField()

    class Meta:
        model = Oferta
        fields = ("id", "anuncio_id", "vendedor_id", "vendedor_nome", "produto_id", "produto_nome", "produto_foto", "descricao", "estado_conservacao", "preco", "status", "criada_em", "atualizada_em", "historico")
        read_only_fields = ("id", "anuncio_id", "vendedor_id", "vendedor_nome", "produto_nome", "produto_foto", "status", "criada_em", "atualizada_em", "historico")
        extra_kwargs = {"descricao": {"required": False}, "estado_conservacao": {"required": False}}

    def get_produto_foto(self, obj):
        if not obj.foto_produto_snapshot:
            return None
        url = default_storage.url(obj.foto_produto_snapshot)
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_historico(self, obj):
        # Mensagens do chat têm endpoint próprio e não fazem parte do histórico de preços.
        eventos = [e for e in obj.eventos.all() if e.tipo_evento != EventoNegociacao.TipoEvento.MENSAGEM]
        return EventoNegociacaoSerializer(eventos, many=True).data

    def validate(self, attrs):
        if self.instance is not None and "produto_id" in attrs:
            raise serializers.ValidationError({"produto_id": "O produto de uma oferta enviada não pode ser trocado."})
        return attrs

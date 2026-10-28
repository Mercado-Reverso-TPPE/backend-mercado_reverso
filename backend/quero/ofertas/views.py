from decimal import Decimal

from django.core.files.storage import default_storage
from rest_framework import serializers

from quero.negociacao.models import Negociacao

from .models import EventoNegociacao, Oferta


class EventoNegociacaoSerializer(serializers.ModelSerializer):
    autor_id = serializers.UUIDField(read_only=True)
    justificativa = serializers.SerializerMethodField()

    class Meta:
        model = EventoNegociacao
        fields = (
            "id",
            "autor_id",
            "preco",
            "status",
            "tipo_evento",
            "justificativa",
            "texto",
            "rodada",
            "expira_em",
            "respondida_em",
            "resultado",
            "registrado_em",
        )
        read_only_fields = fields

    def get_justificativa(self, obj):
        request = self.context.get("request")
        if request is None or request.user.pk == obj.autor_id:
            return ""
        return obj.justificativa


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
        fields = (
            "id",
            "anuncio_id",
            "vendedor_id",
            "vendedor_nome",
            "produto_id",
            "produto_nome",
            "produto_foto",
            "descricao",
            "estado_conservacao",
            "preco",
            "status",
            "criada_em",
            "atualizada_em",
            "historico",
        )
        read_only_fields = (
            "id",
            "anuncio_id",
            "vendedor_id",
            "vendedor_nome",
            "produto_nome",
            "produto_foto",
            "status",
            "criada_em",
            "atualizada_em",
            "historico",
        )
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


class ContrapropostaSerializer(serializers.Serializer):
    preco = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    texto = serializers.CharField(max_length=5000, required=False, allow_blank=True)


class RecusaOfertaSerializer(serializers.Serializer):
    justificativa = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class RespostaContrapropostaSerializer(serializers.Serializer):
    acao = serializers.ChoiceField(choices=("aceitar", "recusar", "contrapropor"))
    preco = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False)
    texto = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    justificativa = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["acao"] == "contrapropor" and "preco" not in attrs:
            raise serializers.ValidationError({"preco": "Informe o preço da contraproposta."})
        return attrs


class NegociacaoSerializer(serializers.ModelSerializer):
    oferta_id = serializers.UUIDField(read_only=True)
    anuncio_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Negociacao
        fields = (
            "id",
            "oferta_id",
            "anuncio_id",
            "valor_final",
            "status",
            "cancelada_em",
            "criada_em",
            "atualizada_em",
        )
        read_only_fields = fields

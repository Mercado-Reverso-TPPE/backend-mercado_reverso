from rest_framework import serializers

from .models import Avaliacao


class AvaliacaoSerializer(serializers.ModelSerializer):
    """Serializer para leitura de uma avaliação publicada."""

    autor_id = serializers.UUIDField(read_only=True)
    avaliado_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Avaliacao
        fields = (
            "id",
            "negociacao_id",
            "autor_id",
            "avaliado_id",
            "nota",
            "comentario",
            "resposta",
            "respondida_em",
            "publicada_em",
            "criada_em",
        )
        read_only_fields = fields


class CriarAvaliacaoSerializer(serializers.Serializer):
    """Validação de entrada para criação de avaliação."""

    nota = serializers.IntegerField(min_value=1, max_value=5)
    comentario = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class ResponderAvaliacaoSerializer(serializers.Serializer):
    """Validação de entrada para resposta pública do avaliado."""

    resposta = serializers.CharField(max_length=2000, min_length=1)


class DenunciarAvaliacaoSerializer(serializers.Serializer):
    """Validação de entrada para denúncia de avaliação."""

    motivo = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")

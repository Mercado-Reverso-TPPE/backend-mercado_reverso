from rest_framework import serializers

from .models import AcaoModeracao


class BloqueioSerializer(serializers.ModelSerializer):
    usuario_id = serializers.UUIDField(source="alvo_id")
    usuario_nome = serializers.CharField(source="alvo.nome", read_only=True)

    class Meta:
        model = AcaoModeracao
        fields = ("id", "usuario_id", "usuario_nome", "motivo", "estado", "criada_em")
        read_only_fields = ("id", "usuario_nome", "estado", "criada_em")


class DenunciaConversaSerializer(serializers.ModelSerializer):
    conversa_id = serializers.UUIDField(source="oferta_id", read_only=True)
    mensagem_id = serializers.IntegerField(source="evento_id", required=False, allow_null=True)
    motivo = serializers.CharField(max_length=2000)

    class Meta:
        model = AcaoModeracao
        fields = ("id", "conversa_id", "mensagem_id", "motivo", "estado", "criada_em")
        read_only_fields = ("id", "conversa_id", "estado", "criada_em")

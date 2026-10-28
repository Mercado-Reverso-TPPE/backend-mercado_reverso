from rest_framework import serializers

from .catalogo import TipoNotificacao
from .models import Notificacao, PreferenciaNotificacao


class NotificacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacao
        fields = (
            "id",
            "tipo",
            "titulo",
            "mensagem",
            "anuncio",
            "oferta",
            "negociacao",
            "contexto",
            "criada_em",
            "lida_em",
        )
        read_only_fields = fields


class PreferenciaItemSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TipoNotificacao.choices)
    canal = serializers.ChoiceField(choices=PreferenciaNotificacao.Canal.choices)
    habilitada = serializers.BooleanField()

    def validate(self, attrs):
        if attrs["tipo"] == TipoNotificacao.SEGURANCA_CONTA and not attrs["habilitada"]:
            raise serializers.ValidationError({"habilitada": "Avisos de segurança da conta não podem ser desativados."})
        return attrs


class AtualizarPreferenciasSerializer(serializers.Serializer):
    preferencias = PreferenciaItemSerializer(many=True, allow_empty=False)

    def validate_preferencias(self, preferencias):
        chaves = [(item["tipo"], item["canal"]) for item in preferencias]
        if len(chaves) != len(set(chaves)):
            raise serializers.ValidationError("Não repita o mesmo tipo e canal.")
        return preferencias

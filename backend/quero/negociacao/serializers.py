from rest_framework import serializers

from quero.ofertas.models import EventoNegociacao

from .models import Negociacao
from .services import conversa_somente_leitura, prazo_confirmacao


def _contraparte(usuario, comprador, vendedor):
    outro = vendedor if usuario.pk == comprador.pk else comprador
    return {"id": outro.pk, "nome": outro.nome}


class MensagemSerializer(serializers.ModelSerializer):
    autor_id = serializers.UUIDField(read_only=True)
    autor_nome = serializers.CharField(source="autor.nome", read_only=True)
    minha = serializers.SerializerMethodField()
    texto = serializers.CharField(max_length=5000)

    class Meta:
        model = EventoNegociacao
        fields = ("id", "autor_id", "autor_nome", "minha", "texto", "registrado_em", "lida_em")
        read_only_fields = ("id", "autor_id", "autor_nome", "minha", "registrado_em", "lida_em")

    def get_minha(self, obj):
        return obj.autor_id == self.context["request"].user.pk


class ConversaSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    anuncio_id = serializers.UUIDField(read_only=True)
    anuncio_titulo = serializers.CharField(source="anuncio.titulo", read_only=True)
    status_oferta = serializers.CharField(source="status", read_only=True)
    papel = serializers.SerializerMethodField()
    contraparte = serializers.SerializerMethodField()
    somente_leitura = serializers.SerializerMethodField()
    mensagens_nao_lidas = serializers.IntegerField(read_only=True, default=0)
    ultima_mensagem_em = serializers.DateTimeField(read_only=True, default=None)

    def get_papel(self, obj):
        return "comprador" if obj.anuncio.comprador_id == self.context["request"].user.pk else "vendedor"

    def get_contraparte(self, obj):
        return _contraparte(self.context["request"].user, obj.anuncio.comprador, obj.vendedor)

    def get_somente_leitura(self, obj):
        return conversa_somente_leitura(obj)


class PrecoNegociadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoNegociacao
        fields = ("preco", "tipo_evento", "rodada", "registrado_em")
        read_only_fields = fields


class NegociacaoSerializer(serializers.ModelSerializer):
    oferta_id = serializers.UUIDField(read_only=True)
    anuncio = serializers.SerializerMethodField()
    papel = serializers.SerializerMethodField()
    contraparte = serializers.SerializerMethodField()
    prazo_confirmacao_em = serializers.SerializerMethodField()
    conclusao_automatica = serializers.SerializerMethodField()
    avaliacao = serializers.SerializerMethodField()

    class Meta:
        model = Negociacao
        fields = (
            "id",
            "oferta_id",
            "anuncio",
            "papel",
            "contraparte",
            "status",
            "valor_final",
            "conclusao_solicitada_em",
            "prazo_confirmacao_em",
            "confirmada_em",
            "concluida_em",
            "cancelada_em",
            "conclusao_automatica",
            "avaliacao",
            "criada_em",
        )
        read_only_fields = fields

    def _usuario(self):
        return self.context["request"].user

    def get_anuncio(self, obj):
        anuncio = obj.oferta.anuncio
        return {"id": anuncio.pk, "titulo": anuncio.titulo, "categoria": anuncio.categoria.slug}

    def get_papel(self, obj):
        return "comprador" if obj.oferta.anuncio.comprador_id == self._usuario().pk else "vendedor"

    def get_contraparte(self, obj):
        return _contraparte(self._usuario(), obj.oferta.anuncio.comprador, obj.oferta.vendedor)

    def get_prazo_confirmacao_em(self, obj):
        if obj.status != Negociacao.Status.EM_ANDAMENTO or obj.conclusao_solicitada_em is None:
            return None
        return serializers.DateTimeField().to_representation(obj.conclusao_solicitada_em + prazo_confirmacao())

    def get_conclusao_automatica(self, obj):
        return obj.status == Negociacao.Status.CONCLUIDA and obj.confirmada_em is None

    def get_avaliacao(self, obj):
        enviada = any(avaliacao.autor_id == self._usuario().pk for avaliacao in obj.avaliacoes.all())
        return {
            "disponivel": obj.status == Negociacao.Status.CONCLUIDA and not enviada,
            "enviada": enviada,
        }


class HistoricoDetalheSerializer(NegociacaoSerializer):
    preco_inicial = serializers.SerializerMethodField()
    precos = serializers.SerializerMethodField()
    mensagens = serializers.SerializerMethodField()

    class Meta(NegociacaoSerializer.Meta):
        fields = (*NegociacaoSerializer.Meta.fields, "preco_inicial", "precos", "mensagens")
        read_only_fields = fields

    def _eventos(self, obj):
        return list(obj.oferta.eventos.select_related("autor"))

    def get_preco_inicial(self, obj):
        enviada = next((e for e in self._eventos(obj) if e.tipo_evento == EventoNegociacao.TipoEvento.ENVIADA), None)
        preco = enviada.preco if enviada else obj.oferta.preco
        return serializers.DecimalField(max_digits=10, decimal_places=2).to_representation(preco)

    def get_precos(self, obj):
        eventos = [e for e in self._eventos(obj) if e.preco is not None and e.tipo_evento != EventoNegociacao.TipoEvento.MENSAGEM]
        return PrecoNegociadoSerializer(eventos, many=True).data

    def get_mensagens(self, obj):
        mensagens = [e for e in self._eventos(obj) if e.tipo_evento == EventoNegociacao.TipoEvento.MENSAGEM]
        return MensagemSerializer(mensagens, many=True, context=self.context).data


class FiltroHistoricoSerializer(serializers.Serializer):
    papel = serializers.ChoiceField(choices=("comprador", "vendedor"), required=False)
    status = serializers.ChoiceField(
        choices=(Negociacao.Status.CONCLUIDA, Negociacao.Status.CANCELADA),
        required=False,
    )

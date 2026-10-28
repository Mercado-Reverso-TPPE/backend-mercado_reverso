from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    concluir_negociacoes_expiradas,
    confirmar_conclusao,
    conversas_do_usuario,
    enviar_mensagem,
    historico_do_usuario,
    marcar_mensagens_como_lidas,
    mensagens_da_conversa,
    negociacoes_do_usuario,
    obter_conversa,
    recusar_conclusao,
    solicitar_conclusao,
    total_mensagens_nao_lidas,
)
from .views import (
    ConversaSerializer,
    FiltroHistoricoSerializer,
    HistoricoDetalheSerializer,
    MensagemSerializer,
    NegociacaoSerializer,
)


class ConversaPagination(CursorPagination):
    page_size = 20
    ordering = "-criada_em"


class MensagemPagination(CursorPagination):
    page_size = 50
    ordering = "id"


class NegociacaoPagination(CursorPagination):
    page_size = 20
    ordering = "-criada_em"


class ConversasView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ConversaSerializer
    pagination_class = ConversaPagination

    def get_queryset(self):
        return conversas_do_usuario(self.request.user)


class MensagensNaoLidasView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"total": total_mensagens_nao_lidas(request.user)})


class MensagensView(APIView):
    """Mensagens são imutáveis: a conversa aceita apenas listagem e envio."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, oferta_id):
        oferta = obter_conversa(oferta_id=oferta_id, usuario=request.user)
        mensagens = mensagens_da_conversa(oferta)
        apos = request.query_params.get("apos")
        if apos is not None:
            if not apos.isdigit():
                raise ValidationError({"apos": "Informe o id numérico da última mensagem recebida."})
            mensagens = mensagens.filter(pk__gt=int(apos))
        paginator = MensagemPagination()
        pagina = paginator.paginate_queryset(mensagens, request, view=self)
        dados = MensagemSerializer(pagina, many=True, context={"request": request}).data
        return paginator.get_paginated_response(dados)

    def post(self, request, oferta_id):
        oferta = obter_conversa(oferta_id=oferta_id, usuario=request.user)
        serializer = MensagemSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            mensagem = enviar_mensagem(oferta=oferta, autor=request.user, texto=serializer.validated_data["texto"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(MensagemSerializer(mensagem, context={"request": request}).data, status=status.HTTP_201_CREATED)


class LeituraConversaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, oferta_id):
        oferta = obter_conversa(oferta_id=oferta_id, usuario=request.user)
        return Response({"marcadas": marcar_mensagens_como_lidas(oferta=oferta, usuario=request.user)})


class NegociacaoDetailView(RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NegociacaoSerializer
    lookup_url_kwarg = "negociacao_id"

    def get_queryset(self):
        concluir_negociacoes_expiradas(usuario=self.request.user)
        return negociacoes_do_usuario(self.request.user)


class AcaoConclusaoView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    acao = None

    def post(self, request, negociacao_id):
        negociacao = get_object_or_404(negociacoes_do_usuario(request.user), pk=negociacao_id)
        try:
            negociacao = type(self).acao(negociacao=negociacao, usuario=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        negociacao = negociacoes_do_usuario(request.user).get(pk=negociacao.pk)
        return Response(NegociacaoSerializer(negociacao, context={"request": request}).data)


class SolicitarConclusaoView(AcaoConclusaoView):
    acao = solicitar_conclusao


class ConfirmarConclusaoView(AcaoConclusaoView):
    acao = confirmar_conclusao


class RecusarConclusaoView(AcaoConclusaoView):
    acao = recusar_conclusao


class HistoricoView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NegociacaoSerializer
    pagination_class = NegociacaoPagination

    def get_queryset(self):
        filtros = FiltroHistoricoSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        concluir_negociacoes_expiradas(usuario=self.request.user)
        return historico_do_usuario(self.request.user, **filtros.validated_data)


class HistoricoDetailView(RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HistoricoDetalheSerializer
    lookup_url_kwarg = "negociacao_id"

    def get_queryset(self):
        concluir_negociacoes_expiradas(usuario=self.request.user)
        return historico_do_usuario(self.request.user)

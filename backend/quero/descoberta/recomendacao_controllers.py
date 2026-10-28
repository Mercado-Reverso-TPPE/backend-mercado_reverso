from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.anuncios.models import Anuncio

from .recomendacoes import (
    convidar_vendedor,
    descartar_recomendacao,
    recomendacoes_visiveis,
    solicitar_atualizacao,
)
from .views import RecomendacaoSerializer


class RecomendacoesAnuncioView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, anuncio_id):
        anuncio = get_object_or_404(
            Anuncio.objects.select_related("comprador"),
            pk=anuncio_id,
            comprador=request.user,
        )
        anuncio = solicitar_atualizacao(anuncio)
        resultados = recomendacoes_visiveis(anuncio)[:50]
        return Response(
            {
                "atualizacao_pendente": anuncio.recomendacoes_solicitadas_em is not None,
                "calculada_em": anuncio.recomendacoes_calculadas_em,
                "resultados": RecomendacaoSerializer(resultados, many=True).data,
            }
        )


class DescartarRecomendacaoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, anuncio_id, recomendacao_id):
        anuncio = get_object_or_404(
            Anuncio.objects.select_related("comprador"),
            pk=anuncio_id,
            comprador=request.user,
        )
        try:
            recomendacao = descartar_recomendacao(anuncio=anuncio, recomendacao_id=recomendacao_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if recomendacao is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(RecomendacaoSerializer(recomendacao).data)


class ConvidarVendedorRecomendacaoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, anuncio_id, recomendacao_id):
        anuncio = get_object_or_404(
            Anuncio.objects.select_related("comprador"),
            pk=anuncio_id,
            comprador=request.user,
        )
        try:
            recomendacao = convidar_vendedor(anuncio=anuncio, recomendacao_id=recomendacao_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if recomendacao is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "recomendacao": RecomendacaoSerializer(recomendacao).data,
                "mensagem": "Convite enviado ao vendedor; nenhuma oferta ou negociação foi criada.",
            }
        )

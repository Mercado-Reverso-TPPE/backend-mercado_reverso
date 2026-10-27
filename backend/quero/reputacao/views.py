from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.moderacao.models import AcaoModeracao

from .models import Avaliacao
from .serializers import (
    AvaliacaoSerializer,
    CriarAvaliacaoSerializer,
    DenunciarAvaliacaoSerializer,
    ResponderAvaliacaoSerializer,
)
from .services import criar_avaliacao, denunciar_avaliacao, responder_avaliacao


class AvaliacaoPagination(CursorPagination):
    page_size = 20
    ordering = "-publicada_em"


class AvaliacoesDoUsuarioView(APIView):
    """
    GET /api/v1/usuarios/<uuid:avaliado_id>/avaliacoes
    Lista as avaliações publicadas de um usuário (pública, mas requer autenticação).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, avaliado_id):
        avaliacoes = (
            Avaliacao.objects.filter(avaliado_id=avaliado_id, publicada_em__isnull=False)
            .select_related("autor", "avaliado")
            .order_by("-publicada_em")
        )
        paginator = AvaliacaoPagination()
        pagina = paginator.paginate_queryset(avaliacoes, request, view=self)
        return paginator.get_paginated_response(AvaliacaoSerializer(pagina, many=True).data)


class AvaliacoesNegociacaoView(APIView):
    """
    POST /api/v1/negociacoes/<uuid:negociacao_id>/avaliacoes
    Cria uma avaliação sigilosa para uma negociação concluída.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, negociacao_id):
        serializer = CriarAvaliacaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            avaliacao = criar_avaliacao(
                autor=request.user,
                negociacao_id=negociacao_id,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(AvaliacaoSerializer(avaliacao).data, status=status.HTTP_201_CREATED)


class RespostaAvaliacaoView(APIView):
    """
    POST /api/v1/avaliacoes/<uuid:avaliacao_id>/resposta
    O avaliado adiciona uma resposta pública única e imutável.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, avaliacao_id):
        avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
        serializer = ResponderAvaliacaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            avaliacao = responder_avaliacao(
                avaliado=request.user,
                avaliacao_id=avaliacao_id,
                resposta=serializer.validated_data["resposta"],
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(AvaliacaoSerializer(avaliacao).data)


class DenunciaAvaliacaoView(APIView):
    """
    POST /api/v1/avaliacoes/<uuid:avaliacao_id>/denuncias
    Qualquer usuário autenticado pode denunciar um comentário de avaliação publicada.
    A avaliação permanece visível; a denúncia entra na fila de moderação.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, avaliacao_id):
        get_object_or_404(Avaliacao, pk=avaliacao_id, publicada_em__isnull=False)
        serializer = DenunciarAvaliacaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            denunciar_avaliacao(
                denunciante=request.user,
                avaliacao_id=avaliacao_id,
                motivo=serializer.validated_data.get("motivo", ""),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_201_CREATED)


class FilaModeracaoAvaliacaoView(APIView):
    """
    GET /api/v1/moderacao/avaliacoes
    Lista denúncias de avaliação abertas para administradores.

    PATCH /api/v1/moderacao/avaliacoes/<uuid:acao_id>
    Atualiza o estado de uma denúncia (resolvida / descartada).
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        acoes = (
            AcaoModeracao.objects.filter(
                tipo=AcaoModeracao.Tipo.DENUNCIA_AVALIACAO,
                estado=AcaoModeracao.Estado.ABERTA,
            )
            .select_related("autor", "alvo", "avaliacao")
            .order_by("-criada_em")
        )
        dados = [
            {
                "id": str(acao.pk),
                "autor_id": str(acao.autor_id),
                "alvo_id": str(acao.alvo_id),
                "avaliacao_id": str(acao.avaliacao_id),
                "motivo": acao.motivo,
                "criada_em": acao.criada_em,
            }
            for acao in acoes
        ]
        return Response(dados)


class DetalheFilaModeracaoAvaliacaoView(APIView):
    """PATCH para atualizar o estado de uma denúncia de avaliação."""

    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, acao_id):
        acao = get_object_or_404(
            AcaoModeracao,
            pk=acao_id,
            tipo=AcaoModeracao.Tipo.DENUNCIA_AVALIACAO,
        )
        novo_estado = request.data.get("estado")
        estados_permitidos = (AcaoModeracao.Estado.RESOLVIDA, AcaoModeracao.Estado.DESCARTADA)
        if novo_estado not in estados_permitidos:
            raise ValidationError({"estado": f"Informe um dos estados: {', '.join(estados_permitidos)}."})
        acao.estado = novo_estado
        acao.save(update_fields=["estado", "atualizada_em"])
        return Response({"id": str(acao.pk), "estado": acao.estado})

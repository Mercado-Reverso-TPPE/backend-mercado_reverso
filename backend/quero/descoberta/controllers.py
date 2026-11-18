from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.anuncios.views import AnuncioSerializer
from quero.ofertas.models import BuscaSalva
from quero.ofertas.services import propor_compra_produto

from .paginacao import PaginacaoPorChave
from .services import (
    buscar_anuncios,
    buscar_produtos,
    contar_por_categoria,
    estatisticas_publicas,
    filtros_da_busca_salva,
    salvar_busca,
)
from .views import (
    BuscaSalvaSerializer,
    ContagemPorCategoriaSerializer,
    FiltrosBuscaSerializer,
    FiltrosContagemSerializer,
    ProdutoDaVitrineSerializer,
    PropostaVitrineSerializer,
)


class BuscaSalvaPagination(CursorPagination):
    page_size = 20
    ordering = ("-atualizada_em", "-id")


class BuscaSalvaViewSet(viewsets.ModelViewSet):
    serializer_class = BuscaSalvaSerializer
    pagination_class = BuscaSalvaPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Buscas de outros usuários respondem 404, sem revelar que existem.
        return BuscaSalva.objects.filter(usuario=self.request.user).select_related("categoria")

    def perform_create(self, serializer):
        serializer.instance = self._salvar(serializer)

    def perform_update(self, serializer):
        serializer.instance = self._salvar(serializer, busca=serializer.instance)

    def _salvar(self, serializer, busca=None):
        try:
            return salvar_busca(usuario=self.request.user, dados=serializer.validated_data, busca=busca)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages) from exc

    @action(detail=True, methods=["get"], url_path="anuncios")
    def anuncios(self, request, pk=None):
        busca = self.get_object()
        paginador = PaginacaoPorChave()
        anuncios = buscar_anuncios(usuario=request.user, **filtros_da_busca_salva(busca))
        pagina = paginador.paginar(anuncios, request, busca.ordenacao)
        return paginador.resposta(AnuncioSerializer(pagina, many=True, context={"request": request}).data)


class VitrineView(ListAPIView):
    """GET /api/v1/vitrine — produtos à venda perto de quem busca, com os mesmos filtros do feed."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProdutoDaVitrineSerializer

    def list(self, request, *args, **kwargs):
        filtros = FiltrosBuscaSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        paginador = PaginacaoPorChave()
        pagina = paginador.paginar(
            buscar_produtos(usuario=request.user, **filtros.filtros()),
            request,
            filtros.validated_data["ordenacao"],
        )
        return paginador.resposta(self.get_serializer(pagina, many=True).data)


class PropostaVitrineView(APIView):
    """POST /api/v1/vitrine/<uuid:produto_id>/propostas.

    Propõe um valor por um produto da vitrine e inicia negociação.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, produto_id):
        serializer = PropostaVitrineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            oferta = propor_compra_produto(
                comprador=request.user,
                produto_id=produto_id,
                preco=serializer.validated_data["preco"],
                mensagem=serializer.validated_data.get("mensagem", ""),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages if hasattr(exc, "messages") else str(exc)) from exc
        return Response(
            {
                "id": str(oferta.id),
                "oferta_id": str(oferta.id),
                "anuncio_id": str(oferta.anuncio_id),
                "produto_id": str(produto_id),
                "preco_original": str(oferta.preco),
                "preco_proposto": str(serializer.validated_data["preco"]),
                "status": oferta.status,
            },
            status=status.HTTP_201_CREATED,
        )


class _ContagemPorCategoriaView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    buscar = None

    def get(self, request):
        filtros = FiltrosContagemSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        contagem = contar_por_categoria(type(self).buscar(usuario=request.user, **filtros.filtros()))
        return Response(ContagemPorCategoriaSerializer(contagem, many=True).data)


class ContagemAnunciosPorCategoriaView(_ContagemPorCategoriaView):
    """GET /api/v1/anuncios/categorias — ``[{slug, total}]`` dos anúncios visíveis com os filtros do feed."""

    buscar = staticmethod(buscar_anuncios)


class ContagemVitrinePorCategoriaView(_ContagemPorCategoriaView):
    """GET /api/v1/vitrine/categorias — ``[{slug, total}]`` dos produtos visíveis com os filtros do feed."""

    buscar = staticmethod(buscar_produtos)


class EstatisticasView(APIView):
    """GET /api/v1/estatisticas — números públicos do hero."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(estatisticas_publicas())

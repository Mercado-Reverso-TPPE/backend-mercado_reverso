from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Produto
from .serializers import AlteracaoStatusProdutoSerializer, FotoProdutoSerializer, ProdutoSerializer, UploadFotosSerializer
from .services import adicionar_fotos, alterar_status_produto_pelo_vendedor, atualizar_produto, criar_produto, excluir_produto, remover_foto


class ProdutoPagination(CursorPagination):
    page_size = 20
    ordering = "-criado_em"


class ProdutoViewSet(viewsets.ModelViewSet):
    serializer_class = ProdutoSerializer
    pagination_class = ProdutoPagination
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        # Produtos de outros vendedores ficam invisíveis: a busca responde 404, não 403.
        qs = Produto.objects.filter(vendedor=self.request.user).select_related("categoria").prefetch_related("fotos")
        status_filtro = self.request.query_params.get("status")
        if self.action == "list" and status_filtro:
            qs = qs.filter(status=status_filtro)
        return qs

    def perform_create(self, serializer):
        serializer.instance = criar_produto(vendedor=self.request.user, dados=serializer.validated_data)

    def perform_update(self, serializer):
        try:
            serializer.instance = atualizar_produto(produto=serializer.instance, dados=serializer.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

    def perform_destroy(self, instance):
        try:
            excluir_produto(produto=instance)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc

    @action(detail=True, methods=["patch"], url_path="status")
    def alterar_status(self, request, pk=None):
        produto = self.get_object()
        serializer = AlteracaoStatusProdutoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            produto = alterar_status_produto_pelo_vendedor(produto=produto, novo_status=serializer.validated_data["status"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(self.get_serializer(self.get_queryset().get(pk=produto.pk)).data)

    @action(detail=True, methods=["post"], url_path="fotos")
    def enviar_fotos(self, request, pk=None):
        produto = self.get_object()
        serializer = UploadFotosSerializer(data={"fotos": request.FILES.getlist("fotos")})
        serializer.is_valid(raise_exception=True)
        try:
            fotos = adicionar_fotos(produto=produto, arquivos=serializer.validated_data["fotos"])
        except DjangoValidationError as exc:
            raise ValidationError({"fotos": exc.messages}) from exc
        contexto = self.get_serializer_context()
        return Response(FotoProdutoSerializer(fotos, many=True, context=contexto).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"fotos/(?P<foto_id>\d+)")
    def excluir_foto(self, request, pk=None, foto_id=None):
        produto = self.get_object()
        foto = get_object_or_404(produto.fotos, pk=foto_id)
        try:
            remover_foto(foto=foto)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

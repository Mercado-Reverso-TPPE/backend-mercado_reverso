from django.contrib.gis.db.models.functions import Distance
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import permissions, status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.pagination import CursorPagination
from .models import Anuncio, Categoria
from .serializers import AnuncioSerializer, AlteracaoStatusSerializer, CategoriaSerializer
from .services import alterar_status_anuncio

class AnuncioPagination(CursorPagination):
    page_size = 20
    ordering = "-criado_em"


class CategoriaListView(ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CategoriaSerializer
    queryset = Categoria.objects.filter(ativa=True)

class AnuncioViewSet(viewsets.ModelViewSet):
    serializer_class = AnuncioSerializer
    pagination_class = AnuncioPagination

    def paginate_queryset(self, queryset):
        page = self.paginator
        if page is None:
            return None
        if self.action == "list" and self.request.query_params.get("meus") != "true":
            page.ordering = ("distancia_m", "-criado_em")
        else:
            page.ordering = "-criado_em"
        return page.paginate_queryset(queryset, self.request, view=self)

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Anuncio.objects.select_related("comprador", "categoria").annotate(
            ofertas_ativas=Count("ofertas", filter=Q(ofertas__status__in=("enviada", "aceita")), distinct=True)
        )
        if self.action == "meus":
            return qs.filter(comprador=user)
        if self.action in ("list", "retrieve"):
            if self.request.query_params.get("meus") == "true":
                return qs.filter(comprador=user)
            if user.ponto is None:
                return qs.none()
            return qs.filter(
                status=Anuncio.Status.ATIVO,
                alcance__intersects=user.ponto,
            ).annotate(
                distancia_m=Distance("comprador__ponto", user.ponto)
            ).order_by("distancia_m", "-criado_em")
        return qs.filter(comprador=user)

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        anuncio = self.get_object()
        if anuncio.comprador_id != self.request.user.id:
            raise PermissionDenied("Você só pode alterar seus próprios anúncios.")
        if anuncio.status == Anuncio.Status.ENCERRADO:
            raise ValidationError("Anúncios encerrados não podem ser alterados.")
        serializer.save()

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        anuncio = self.get_object()
        dados = request.data.copy()
        novo_status = dados.pop("status", None)
        serializer = self.get_serializer(anuncio, data=dados, partial=True)
        serializer.is_valid(raise_exception=True)
        if novo_status is not None:
            status_serializer = AlteracaoStatusSerializer(data={"status": novo_status})
            status_serializer.is_valid(raise_exception=True)
            try:
                alterar_status_anuncio(anuncio=anuncio, novo_status=status_serializer.validated_data["status"])
            except DjangoValidationError as exc:
                raise ValidationError(exc.messages) from exc
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        raise ValidationError("Use a alteração de status para encerrar ou pausar um anúncio.")

    @action(detail=False, methods=["get"], url_path="meus")
    def meus(self, request):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="status")
    def alterar_status(self, request, pk=None):
        anuncio = self.get_object()
        serializer = AlteracaoStatusSerializer(data=request.data, context={"anuncio": anuncio})
        serializer.is_valid(raise_exception=True)
        try:
            anuncio = alterar_status_anuncio(anuncio=anuncio, novo_status=serializer.validated_data["status"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(self.get_serializer(anuncio).data, status=status.HTTP_200_OK)

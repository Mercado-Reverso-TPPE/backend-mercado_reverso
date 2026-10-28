from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.anuncios.models import Anuncio

from .models import Oferta
from .serializers import OfertaSerializer
from .services import editar_oferta, enviar_oferta, retirar_oferta


class OfertaPagination(CursorPagination):
    page_size = 20
    ordering = "-criada_em"


class OfertasDoAnuncioView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, anuncio_id):
        anuncio = get_object_or_404(Anuncio, pk=anuncio_id)
        ofertas = Oferta.objects.filter(anuncio=anuncio).select_related("vendedor").prefetch_related("eventos")
        if anuncio.comprador_id == request.user.pk:
            ofertas = ofertas.filter(
                status__in=(
                    Oferta.Status.ENVIADA,
                    Oferta.Status.EM_NEGOCIACAO,
                    Oferta.Status.ACEITA,
                )
            )
        else:
            ofertas = ofertas.filter(vendedor=request.user)
        paginator = OfertaPagination()
        pagina = paginator.paginate_queryset(ofertas, request, view=self)
        return paginator.get_paginated_response(OfertaSerializer(pagina, many=True).data)

    def post(self, request, anuncio_id):
        serializer = OfertaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            oferta = enviar_oferta(
                vendedor=request.user,
                anuncio_id=anuncio_id,
                dados=serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(OfertaSerializer(oferta).data, status=status.HTTP_201_CREATED)


class OfertaDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_oferta(self, request, oferta_id):
        return get_object_or_404(Oferta, pk=oferta_id, vendedor=request.user)

    def patch(self, request, oferta_id):
        oferta = self.get_oferta(request, oferta_id)
        serializer = OfertaSerializer(oferta, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            oferta = editar_oferta(oferta=oferta, vendedor=request.user, dados=serializer.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(OfertaSerializer(oferta).data)

    def delete(self, request, oferta_id):
        oferta = self.get_oferta(request, oferta_id)
        try:
            retirar_oferta(oferta=oferta, vendedor=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class MinhasOfertasView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        ofertas = (
            Oferta.objects.filter(vendedor=request.user)
            .select_related("anuncio", "anuncio__categoria")
            .prefetch_related("eventos")
        )
        paginator = OfertaPagination()
        pagina = paginator.paginate_queryset(ofertas, request, view=self)
        return paginator.get_paginated_response(OfertaSerializer(pagina, many=True).data)

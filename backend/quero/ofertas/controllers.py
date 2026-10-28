from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.anuncios.models import Anuncio

from .models import Oferta
from .services import (
    aceitar_oferta,
    cancelar_negociacao,
    editar_oferta,
    enviar_contraproposta,
    enviar_oferta,
    recusar_oferta,
    responder_contraproposta,
    retirar_oferta,
)
from .views import (
    ContrapropostaSerializer,
    EventoNegociacaoSerializer,
    NegociacaoSerializer,
    OfertaSerializer,
    RecusaOfertaSerializer,
    RespostaContrapropostaSerializer,
)


def _validation_error(exc):
    raise ValidationError(exc.messages) from exc


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
        return paginator.get_paginated_response(OfertaSerializer(pagina, many=True, context={"request": request}).data)

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
        return Response(
            OfertaSerializer(oferta, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class OfertaDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_oferta(self, request, oferta_id):
        oferta = get_object_or_404(Oferta.objects.select_related("anuncio"), pk=oferta_id)
        if oferta.vendedor_id != request.user.pk and oferta.anuncio.comprador_id != request.user.pk:
            raise PermissionDenied("Você não participa desta negociação.")
        return oferta

    def get(self, request, oferta_id):
        return Response(OfertaSerializer(self.get_oferta(request, oferta_id), context={"request": request}).data)

    def patch(self, request, oferta_id):
        oferta = self.get_oferta(request, oferta_id)
        serializer = OfertaSerializer(oferta, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            oferta = editar_oferta(oferta=oferta, vendedor=request.user, dados=serializer.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(OfertaSerializer(oferta, context={"request": request}).data)

    def delete(self, request, oferta_id):
        oferta = self.get_oferta(request, oferta_id)
        try:
            retirar_oferta(oferta=oferta, vendedor=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContrapropostaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, oferta_id):
        serializer = ContrapropostaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            evento = enviar_contraproposta(
                oferta_id=oferta_id,
                autor=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            _validation_error(exc)
        return Response(
            EventoNegociacaoSerializer(evento, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ResponderContrapropostaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, oferta_id):
        serializer = RespostaContrapropostaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        try:
            oferta = responder_contraproposta(
                oferta_id=oferta_id,
                usuario=request.user,
                acao=dados["acao"],
                justificativa=dados.get("justificativa", ""),
                preco=dados.get("preco"),
                texto=dados.get("texto", ""),
            )
        except DjangoValidationError as exc:
            _validation_error(exc)
        if oferta is None:
            return Response({"detail": "A contraproposta expirou."}, status=status.HTTP_409_CONFLICT)
        return Response(OfertaSerializer(oferta, context={"request": request}).data)


class DecisaoOfertaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, oferta_id):
        try:
            negociacao = aceitar_oferta(oferta_id=oferta_id, comprador=request.user)
        except DjangoValidationError as exc:
            _validation_error(exc)
        return Response(NegociacaoSerializer(negociacao).data, status=status.HTTP_201_CREATED)


class RecusarOfertaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, oferta_id):
        serializer = RecusaOfertaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            oferta = recusar_oferta(
                oferta_id=oferta_id,
                comprador=request.user,
                justificativa=serializer.validated_data.get("justificativa", ""),
            )
        except DjangoValidationError as exc:
            _validation_error(exc)
        return Response(OfertaSerializer(oferta, context={"request": request}).data)


class CancelarNegociacaoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, negociacao_id):
        try:
            negociacao = cancelar_negociacao(negociacao_id=negociacao_id, usuario=request.user)
        except DjangoValidationError as exc:
            _validation_error(exc)
        return Response(NegociacaoSerializer(negociacao).data)


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
        return paginator.get_paginated_response(OfertaSerializer(pagina, many=True, context={"request": request}).data)

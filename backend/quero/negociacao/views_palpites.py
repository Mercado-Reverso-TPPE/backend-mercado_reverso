from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.anuncios.models import Anuncio

from .serializers_palpites import EstimativaPrecoSerializer, PalpiteSerializer
from .services_palpites import criar_ou_atualizar_palpite, obter_estimativa_preco


class PalpiteAnuncioView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, anuncio_id):
        serializer = PalpiteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            palpite, criado = criar_ou_atualizar_palpite(
                vendedor=request.user,
                anuncio_id=anuncio_id,
                valor=serializer.validated_data["valor"],
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(
            PalpiteSerializer(palpite).data,
            status=status.HTTP_201_CREATED if criado else status.HTTP_200_OK,
        )


class EstimativaPrecoAnuncioView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, anuncio_id):
        anuncio = get_object_or_404(Anuncio, pk=anuncio_id)
        if anuncio.comprador_id != request.user.pk:
            raise PermissionDenied("A estimativa só está disponível para o comprador do anúncio.")
        resultado = obter_estimativa_preco(anuncio=anuncio)
        if not resultado["disponivel"]:
            return Response({"disponivel": False})
        return Response(EstimativaPrecoSerializer(resultado).data)

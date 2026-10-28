from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from quero.negociacao.services import obter_conversa

from .services import bloquear_usuario, bloqueios_do_usuario, denunciar_conversa, desbloquear_usuario
from .views import BloqueioSerializer, DenunciaConversaSerializer


class BloqueiosView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        bloqueios = bloqueios_do_usuario(request.user).order_by("-criada_em")
        return Response(BloqueioSerializer(bloqueios, many=True).data)

    def post(self, request):
        serializer = BloqueioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            bloqueio = bloquear_usuario(
                autor=request.user,
                alvo_id=serializer.validated_data["alvo_id"],
                motivo=serializer.validated_data.get("motivo", ""),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(BloqueioSerializer(bloqueio).data, status=status.HTTP_201_CREATED)


class BloqueioDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, usuario_id):
        try:
            desbloquear_usuario(autor=request.user, alvo_id=usuario_id)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class DenunciasConversaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, oferta_id):
        oferta = obter_conversa(oferta_id=oferta_id, usuario=request.user)
        serializer = DenunciaConversaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            denuncia = denunciar_conversa(
                autor=request.user,
                oferta=oferta,
                motivo=serializer.validated_data["motivo"],
                mensagem_id=serializer.validated_data.get("evento_id"),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(DenunciaConversaSerializer(denuncia).data, status=status.HTTP_201_CREATED)

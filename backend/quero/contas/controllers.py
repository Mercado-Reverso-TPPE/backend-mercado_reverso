from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .services import (
    confirmar_alteracao_email,
    confirmar_redefinicao_senha,
    solicitar_alteracao_email,
    solicitar_redefinicao_senha,
)
from .views import (
    CadastroSerializer,
    ConfirmarAlteracaoEmailSerializer,
    ConfirmarRedefinicaoSenhaSerializer,
    PerfilSerializer,
    SolicitarAlteracaoEmailSerializer,
    SolicitarRedefinicaoSenhaSerializer,
)


class CadastroView(generics.CreateAPIView):
    serializer_class = CadastroSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]


class PerfilView(generics.RetrieveUpdateAPIView):
    serializer_class = PerfilSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class SolicitarRedefinicaoSenhaView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = SolicitarRedefinicaoSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        solicitar_redefinicao_senha(serializer.validated_data["email"])
        return Response(
            {"detail": "Se a conta existir, enviaremos um link de redefinição."}, status=status.HTTP_202_ACCEPTED
        )


class ConfirmarRedefinicaoSenhaView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = ConfirmarRedefinicaoSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        try:
            confirmar_redefinicao_senha(uid=dados["uid"], token=dados["token"], nova_senha=dados["nova_senha"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class SolicitarAlteracaoEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SolicitarAlteracaoEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            solicitar_alteracao_email(usuario=request.user, novo_email=serializer.validated_data["novo_email"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(
            {"detail": "Enviamos um link de confirmação para o novo endereço."}, status=status.HTTP_202_ACCEPTED
        )


class ConfirmarAlteracaoEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ConfirmarAlteracaoEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            confirmar_alteracao_email(token=serializer.validated_data["token"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

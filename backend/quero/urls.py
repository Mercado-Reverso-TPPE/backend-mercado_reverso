from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions, status
from rest_framework.routers import DefaultRouter
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.serializers import TokenBlacklistSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from quero.anuncios.views import AnuncioViewSet, CategoriaListView
from quero.contas.views import CadastroView, ConfirmarAlteracaoEmailView, ConfirmarRedefinicaoSenhaView, PerfilView, SolicitarAlteracaoEmailView, SolicitarRedefinicaoSenhaView
from quero.contas.serializers import LoginSerializer
from quero.ofertas.views import MinhasOfertasView, OfertaDetailView, OfertasDoAnuncioView

router = DefaultRouter(trailing_slash=False)
router.register("anuncios", AnuncioViewSet, basename="anuncio")


class SessoesView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def delete(self, request):
        serializer = TokenBlacklistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_205_RESET_CONTENT)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/usuarios", CadastroView.as_view(), name="cadastro"),
    path("api/v1/sessoes", SessoesView.as_view(), name="sessoes"),
    path("api/v1/sessoes/renovar", TokenRefreshView.as_view(), name="renovar-sessao"),
    path("api/v1/perfil", PerfilView.as_view(), name="perfil"),
    path("api/v1/senha/redefinir", SolicitarRedefinicaoSenhaView.as_view(), name="solicitar-redefinicao-senha"),
    path("api/v1/senha/redefinir/confirmar", ConfirmarRedefinicaoSenhaView.as_view(), name="confirmar-redefinicao-senha"),
    path("api/v1/perfil/email", SolicitarAlteracaoEmailView.as_view(), name="solicitar-alteracao-email"),
    path("api/v1/perfil/email/confirmar", ConfirmarAlteracaoEmailView.as_view(), name="confirmar-alteracao-email"),
    path("api/v1/categorias", CategoriaListView.as_view(), name="categorias"),
    path("api/v1/anuncios/<uuid:anuncio_id>/ofertas", OfertasDoAnuncioView.as_view(), name="ofertas-do-anuncio"),
    path("api/v1/ofertas/meus", MinhasOfertasView.as_view(), name="minhas-ofertas"),
    path("api/v1/ofertas/<uuid:oferta_id>", OfertaDetailView.as_view(), name="detalhe-oferta"),
    path("api/v1/", include(router.urls)),
]

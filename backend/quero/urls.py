from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.serializers import TokenBlacklistSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from quero.anuncios.views import AnuncioViewSet, CategoriaListView
from quero.catalogo.views import ProdutoViewSet
from quero.contas.serializers import LoginSerializer
from quero.contas.views import (
    CadastroView,
    ConfirmarAlteracaoEmailView,
    ConfirmarRedefinicaoSenhaView,
    PerfilView,
    SolicitarAlteracaoEmailView,
    SolicitarRedefinicaoSenhaView,
)
from quero.descoberta.recomendacao_views import (
    ConvidarVendedorRecomendacaoView,
    DescartarRecomendacaoView,
    RecomendacoesAnuncioView,
)
from quero.descoberta.views import BuscaSalvaViewSet
from quero.moderacao.views import BloqueioDetailView, BloqueiosView, DenunciasConversaView
from quero.negociacao.views import (
    ConfirmarConclusaoView,
    ConversasView,
    HistoricoDetailView,
    HistoricoView,
    LeituraConversaView,
    MensagensNaoLidasView,
    MensagensView,
    NegociacaoDetailView,
    RecusarConclusaoView,
    SolicitarConclusaoView,
)
from quero.negociacao.views_palpites import EstimativaPrecoAnuncioView, PalpiteAnuncioView
from quero.notificacoes.views import (
    ContagemNaoLidasView,
    MarcarNotificacaoLidaView,
    NotificacoesView,
    PreferenciasNotificacaoView,
)
from quero.ofertas.views import (
    CancelarNegociacaoView,
    ContrapropostaView,
    DecisaoOfertaView,
    MinhasOfertasView,
    OfertaDetailView,
    OfertasDoAnuncioView,
    RecusarOfertaView,
    ResponderContrapropostaView,
)
from quero.reputacao.views import (
    AvaliacoesDoUsuarioView,
    AvaliacoesNegociacaoView,
    DenunciaAvaliacaoView,
    DetalheFilaModeracaoAvaliacaoView,
    FilaModeracaoAvaliacaoView,
    RespostaAvaliacaoView,
)

router = DefaultRouter(trailing_slash=False)
router.register("anuncios", AnuncioViewSet, basename="anuncio")
router.register("produtos", ProdutoViewSet, basename="produto")
router.register("buscas-salvas", BuscaSalvaViewSet, basename="busca-salva")


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
    path(
        "api/v1/senha/redefinir/confirmar", ConfirmarRedefinicaoSenhaView.as_view(), name="confirmar-redefinicao-senha"
    ),
    path("api/v1/perfil/email", SolicitarAlteracaoEmailView.as_view(), name="solicitar-alteracao-email"),
    path("api/v1/perfil/email/confirmar", ConfirmarAlteracaoEmailView.as_view(), name="confirmar-alteracao-email"),
    path("api/v1/categorias", CategoriaListView.as_view(), name="categorias"),
    path("api/v1/anuncios/<uuid:anuncio_id>/ofertas", OfertasDoAnuncioView.as_view(), name="ofertas-do-anuncio"),
    path("api/v1/anuncios/<uuid:anuncio_id>/palpite", PalpiteAnuncioView.as_view(), name="palpite-anuncio"),
    path(
        "api/v1/anuncios/<uuid:anuncio_id>/estimativa-preco",
        EstimativaPrecoAnuncioView.as_view(),
        name="estimativa-preco-anuncio",
    ),
    path(
        "api/v1/anuncios/<uuid:anuncio_id>/recomendacoes",
        RecomendacoesAnuncioView.as_view(),
        name="recomendacoes-anuncio",
    ),
    path(
        "api/v1/anuncios/<uuid:anuncio_id>/recomendacoes/<uuid:recomendacao_id>/descartar",
        DescartarRecomendacaoView.as_view(),
        name="descartar-recomendacao",
    ),
    path(
        "api/v1/anuncios/<uuid:anuncio_id>/recomendacoes/<uuid:recomendacao_id>/convidar",
        ConvidarVendedorRecomendacaoView.as_view(),
        name="convidar-vendedor-recomendacao",
    ),
    path("api/v1/ofertas/meus", MinhasOfertasView.as_view(), name="minhas-ofertas"),
    path("api/v1/ofertas/<uuid:oferta_id>", OfertaDetailView.as_view(), name="detalhe-oferta"),
    path("api/v1/ofertas/<uuid:oferta_id>/contrapropostas", ContrapropostaView.as_view(), name="contraproposta-oferta"),
    path(
        "api/v1/ofertas/<uuid:oferta_id>/contrapropostas/responder",
        ResponderContrapropostaView.as_view(),
        name="responder-contraproposta",
    ),
    path("api/v1/ofertas/<uuid:oferta_id>/aceitar", DecisaoOfertaView.as_view(), name="aceitar-oferta"),
    path("api/v1/ofertas/<uuid:oferta_id>/recusar", RecusarOfertaView.as_view(), name="recusar-oferta"),
    path(
        "api/v1/negociacoes/<uuid:negociacao_id>/cancelar", CancelarNegociacaoView.as_view(), name="cancelar-negociacao"
    ),
    path("api/v1/notificacoes", NotificacoesView.as_view(), name="notificacoes"),
    path("api/v1/notificacoes/nao-lidas", ContagemNaoLidasView.as_view(), name="notificacoes-nao-lidas"),
    path(
        "api/v1/notificacoes/<uuid:notificacao_id>/lida",
        MarcarNotificacaoLidaView.as_view(),
        name="marcar-notificacao-lida",
    ),
    path("api/v1/preferencias/notificacoes", PreferenciasNotificacaoView.as_view(), name="preferencias-notificacao"),
    path("api/v1/conversas", ConversasView.as_view(), name="conversas"),
    path("api/v1/conversas/nao-lidas", MensagensNaoLidasView.as_view(), name="mensagens-nao-lidas"),
    path("api/v1/conversas/<uuid:oferta_id>/mensagens", MensagensView.as_view(), name="mensagens"),
    path("api/v1/conversas/<uuid:oferta_id>/leitura", LeituraConversaView.as_view(), name="leitura-conversa"),
    path("api/v1/conversas/<uuid:oferta_id>/denuncias", DenunciasConversaView.as_view(), name="denuncias-conversa"),
    path("api/v1/bloqueios", BloqueiosView.as_view(), name="bloqueios"),
    path("api/v1/bloqueios/<uuid:usuario_id>", BloqueioDetailView.as_view(), name="desbloqueio"),
    path("api/v1/negociacoes/<uuid:negociacao_id>", NegociacaoDetailView.as_view(), name="negociacao"),
    path(
        "api/v1/negociacoes/<uuid:negociacao_id>/conclusao",
        SolicitarConclusaoView.as_view(),
        name="solicitar-conclusao",
    ),
    path(
        "api/v1/negociacoes/<uuid:negociacao_id>/conclusao/confirmacao",
        ConfirmarConclusaoView.as_view(),
        name="confirmar-conclusao",
    ),
    path(
        "api/v1/negociacoes/<uuid:negociacao_id>/conclusao/recusa",
        RecusarConclusaoView.as_view(),
        name="recusar-conclusao",
    ),
    path("api/v1/historico", HistoricoView.as_view(), name="historico"),
    path("api/v1/historico/<uuid:negociacao_id>", HistoricoDetailView.as_view(), name="historico-detalhe"),
    path(
        "api/v1/usuarios/<uuid:avaliado_id>/avaliacoes", AvaliacoesDoUsuarioView.as_view(), name="avaliacoes-do-usuario"
    ),
    path(
        "api/v1/negociacoes/<uuid:negociacao_id>/avaliacoes", AvaliacoesNegociacaoView.as_view(), name="criar-avaliacao"
    ),
    path("api/v1/avaliacoes/<uuid:avaliacao_id>/resposta", RespostaAvaliacaoView.as_view(), name="resposta-avaliacao"),
    path("api/v1/avaliacoes/<uuid:avaliacao_id>/denuncias", DenunciaAvaliacaoView.as_view(), name="denuncia-avaliacao"),
    path("api/v1/moderacao/avaliacoes", FilaModeracaoAvaliacaoView.as_view(), name="fila-moderacao-avaliacoes"),
    path(
        "api/v1/moderacao/avaliacoes/<uuid:acao_id>",
        DetalheFilaModeracaoAvaliacaoView.as_view(),
        name="detalhe-moderacao-avaliacao",
    ),
    path("api/v1/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

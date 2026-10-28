from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination

from quero.anuncios.views import AnuncioSerializer
from quero.ofertas.models import BuscaSalva

from .paginacao import PaginacaoPorChave
from .services import buscar_anuncios, filtros_da_busca_salva, salvar_busca
from .views import BuscaSalvaSerializer


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

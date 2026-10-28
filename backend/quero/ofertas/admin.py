from django.contrib import admin

from quero.ofertas.models import BuscaSalva, EventoNegociacao, Oferta


class SomenteLeituraMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EventoNegociacaoInline(SomenteLeituraMixin, admin.TabularInline):
    model = EventoNegociacao
    extra = 0
    fields = ("registrado_em", "tipo_evento", "autor", "preco", "status", "texto", "resultado")
    readonly_fields = fields


@admin.register(Oferta)
class OfertaAdmin(admin.ModelAdmin):
    list_display = ("id", "anuncio", "vendedor", "preco", "status", "criada_em")
    list_filter = ("status", "estado_conservacao")
    search_fields = ("anuncio__titulo", "vendedor__email", "nome_produto_snapshot")
    autocomplete_fields = ("anuncio", "vendedor", "produto")
    readonly_fields = ("id", "criada_em", "atualizada_em")
    date_hierarchy = "criada_em"
    inlines = (EventoNegociacaoInline,)


# Eventos e mensagens são o histórico imutável da negociação.
@admin.register(EventoNegociacao)
class EventoNegociacaoAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("oferta", "tipo_evento", "autor", "preco", "status", "resultado", "registrado_em")
    list_filter = ("tipo_evento", "status", "resultado")
    search_fields = ("oferta__id", "autor__email", "texto")
    date_hierarchy = "registrado_em"


@admin.register(BuscaSalva)
class BuscaSalvaAdmin(admin.ModelAdmin):
    list_display = ("nome", "usuario", "termo", "categoria", "ordenacao", "atualizada_em")
    list_filter = ("ordenacao", "categoria")
    search_fields = ("nome", "termo", "usuario__email")
    autocomplete_fields = ("usuario", "categoria")
    readonly_fields = ("id", "criada_em", "atualizada_em")

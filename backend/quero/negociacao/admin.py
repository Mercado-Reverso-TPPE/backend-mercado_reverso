from django.contrib import admin

from quero.negociacao.models import Negociacao, Palpite


@admin.register(Negociacao)
class NegociacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "oferta", "valor_final", "status", "criada_em", "concluida_em")
    list_filter = ("status",)
    search_fields = ("oferta__anuncio__titulo", "oferta__vendedor__email", "oferta__anuncio__comprador__email")
    autocomplete_fields = ("oferta",)
    readonly_fields = ("id", "criada_em", "atualizada_em")
    date_hierarchy = "criada_em"

    def has_change_permission(self, request, obj=None):
        # Negociacao.save recusa alterações em negociações concluídas.
        if obj is not None and obj.status == Negociacao.Status.CONCLUIDA:
            return False
        return super().has_change_permission(request, obj)


@admin.register(Palpite)
class PalpiteAdmin(admin.ModelAdmin):
    list_display = ("anuncio", "vendedor", "valor", "criado_em")
    search_fields = ("anuncio__titulo", "vendedor__email")
    autocomplete_fields = ("anuncio", "vendedor")
    readonly_fields = ("id", "criado_em", "atualizado_em")

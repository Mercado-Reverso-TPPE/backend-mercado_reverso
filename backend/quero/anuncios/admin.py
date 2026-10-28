from django.contrib import admin

from quero.anuncios.models import Anuncio, Categoria


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "ativa")
    list_filter = ("ativa",)
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Anuncio)
class AnuncioAdmin(admin.ModelAdmin):
    list_display = ("titulo", "comprador", "categoria", "status", "preco_min", "preco_max", "criado_em")
    list_filter = ("status", "categoria")
    search_fields = ("titulo", "descricao", "comprador__email")
    autocomplete_fields = ("comprador", "categoria")
    readonly_fields = ("id", "criado_em", "atualizado_em")
    date_hierarchy = "criado_em"

    def get_actions(self, request):
        # A exclusão em lote ignora Anuncio.delete e apagaria anúncios encerrados do histórico.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == Anuncio.Status.ENCERRADO:
            return False
        return super().has_delete_permission(request, obj)

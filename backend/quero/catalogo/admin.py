from django.contrib import admin

from quero.catalogo.models import FotoProduto, Produto


class FotoProdutoInline(admin.TabularInline):
    model = FotoProduto
    extra = 0
    readonly_fields = ("criada_em",)


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "vendedor", "categoria", "estado_conservacao", "preco", "status", "criado_em")
    list_filter = ("status", "estado_conservacao", "categoria")
    search_fields = ("nome", "descricao", "vendedor__email")
    autocomplete_fields = ("vendedor", "categoria")
    readonly_fields = ("id", "criado_em", "atualizado_em")
    inlines = (FotoProdutoInline,)

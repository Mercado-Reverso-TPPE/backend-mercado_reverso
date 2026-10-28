from django.contrib import admin

from quero.descoberta.models import Recomendacao


@admin.register(Recomendacao)
class RecomendacaoAdmin(admin.ModelAdmin):
    list_display = ("anuncio", "produto", "pontuacao", "estado", "calculada_em")
    list_filter = ("estado",)
    search_fields = ("anuncio__titulo", "produto__nome")
    autocomplete_fields = ("anuncio", "produto")
    readonly_fields = ("id", "calculada_em")

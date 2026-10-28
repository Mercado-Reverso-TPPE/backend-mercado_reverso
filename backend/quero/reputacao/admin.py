from django.contrib import admin

from quero.reputacao.models import Avaliacao


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = ("negociacao", "autor", "avaliado", "nota", "criada_em", "publicada_em")
    list_filter = ("nota",)
    search_fields = ("autor__email", "avaliado__email", "comentario")
    autocomplete_fields = ("negociacao", "autor", "avaliado")
    readonly_fields = ("id", "criada_em")
    date_hierarchy = "criada_em"

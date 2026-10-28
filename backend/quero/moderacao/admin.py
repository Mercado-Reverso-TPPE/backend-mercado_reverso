from django.contrib import admin

from quero.moderacao.models import AcaoModeracao


@admin.register(AcaoModeracao)
class AcaoModeracaoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "estado", "autor", "alvo", "criada_em")
    list_filter = ("tipo", "estado")
    search_fields = ("autor__email", "alvo__email", "motivo")
    autocomplete_fields = ("autor", "alvo", "oferta", "evento", "avaliacao")
    readonly_fields = ("id", "criada_em", "atualizada_em")
    date_hierarchy = "criada_em"

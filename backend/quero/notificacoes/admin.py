from django.contrib import admin

from quero.notificacoes.models import Notificacao, PreferenciaNotificacao


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "usuario", "tipo", "criada_em", "lida_em")
    list_filter = ("tipo",)
    search_fields = ("titulo", "mensagem", "usuario__email")
    autocomplete_fields = ("usuario", "anuncio", "oferta", "negociacao")
    readonly_fields = ("id", "criada_em")
    date_hierarchy = "criada_em"


@admin.register(PreferenciaNotificacao)
class PreferenciaNotificacaoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tipo", "canal", "habilitada", "atualizada_em")
    list_filter = ("canal", "habilitada", "tipo")
    search_fields = ("usuario__email", "tipo")
    autocomplete_fields = ("usuario",)
    readonly_fields = ("atualizada_em",)

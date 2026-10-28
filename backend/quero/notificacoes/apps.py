from django.apps import AppConfig


class NotificacoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "quero.notificacoes"

    def ready(self):
        from . import signals  # noqa: F401

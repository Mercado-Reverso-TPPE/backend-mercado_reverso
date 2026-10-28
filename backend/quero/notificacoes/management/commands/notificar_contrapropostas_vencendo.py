from django.core.management.base import BaseCommand

from quero.notificacoes.services import publicar_lembretes_contraproposta


class Command(BaseCommand):
    help = "Envia lembretes das contrapropostas com vencimento nas próximas 24 horas."

    def handle(self, *args, **options):
        enviados = publicar_lembretes_contraproposta()
        self.stdout.write(f"Lembretes criados: {enviados}")

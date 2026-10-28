from django.core.management.base import BaseCommand

from quero.ofertas.services import expirar_contrapropostas_vencidas


class Command(BaseCommand):
    help = "Marca como expiradas as contrapropostas cujo prazo terminou."

    def handle(self, *args, **options):
        total = expirar_contrapropostas_vencidas()
        self.stdout.write(f"{total} contraproposta(s) expirada(s).")

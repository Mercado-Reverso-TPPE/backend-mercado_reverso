from django.core.management.base import BaseCommand

from quero.negociacao.services import concluir_negociacoes_expiradas


class Command(BaseCommand):
    help = "Conclui automaticamente negociações cujo prazo de confirmação do comprador terminou."

    def handle(self, *args, **options):
        concluidas = concluir_negociacoes_expiradas()
        self.stdout.write(f"{concluidas} negociação(ões) concluída(s) automaticamente.")

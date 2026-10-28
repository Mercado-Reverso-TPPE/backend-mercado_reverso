import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from quero.anuncios.models import Anuncio
from quero.descoberta.recomendacoes import processar_proxima_atualizacao


class Command(BaseCommand):
    help = "Processa recomendações de produtos enfileiradas pelas consultas da API."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Processa a fila pronta e encerra.")
        parser.add_argument("--poll-seconds", type=float, default=5)
        parser.add_argument("--enqueue-all", action="store_true", help="Enfileira anúncios ativos desatualizados.")
        parser.add_argument("--retry-failed", action="store_true", help="Antecipar tentativas pendentes após falhas.")

    def handle(self, *args, **options):
        agora = timezone.now()
        if options["enqueue_all"]:
            limite = agora - timedelta(minutes=5)
            Anuncio.objects.filter(status=Anuncio.Status.ATIVO, recomendacoes_solicitadas_em__isnull=True).filter(
                Q(recomendacoes_calculadas_em__isnull=True) | Q(recomendacoes_calculadas_em__lt=limite)
            ).update(
                recomendacoes_solicitadas_em=agora,
                recomendacoes_tentar_em=agora,
                recomendacoes_ultimo_erro="",
            )
        if options["retry_failed"]:
            Anuncio.objects.filter(
                recomendacoes_solicitadas_em__isnull=False,
                recomendacoes_processando_em__isnull=True,
                recomendacoes_tentativas__gt=0,
            ).update(recomendacoes_tentar_em=agora, recomendacoes_ultimo_erro="")

        while True:
            if not processar_proxima_atualizacao():
                if options["once"]:
                    return
                time.sleep(max(options["poll_seconds"], 0.1))

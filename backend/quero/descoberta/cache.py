import hashlib

from django.conf import settings
from django.core.cache import cache


def resposta_em_cache(prefixo, request, montar):
    """Guarda por ``FEED_PUBLICO_CACHE_SEGUNDOS`` o corpo de uma leitura pública, por query string.

    Só respostas de sucesso entram no cache: ``montar`` levanta exceção quando os filtros são inválidos.
    O host entra na chave porque o link ``next`` da paginação é absoluto.
    """
    segundos = settings.FEED_PUBLICO_CACHE_SEGUNDOS
    if segundos <= 0:
        return montar()
    consulta = "&".join(sorted(f"{chave}={valor}" for chave, valor in request.query_params.items()))
    assinatura = hashlib.sha256(f"{request.get_host()}?{consulta}".encode()).hexdigest()
    chave = f"quero:{prefixo}:{assinatura}"
    dados = cache.get(chave)
    if dados is None:
        dados = montar()
        cache.set(chave, dados, segundos)
    return dados

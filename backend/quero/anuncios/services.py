from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Anuncio


@transaction.atomic
def criar_anuncio(*, comprador, dados):
    """Cria uma demanda usando a localização de referência do comprador."""
    if comprador.ponto is None:
        raise ValidationError("Cadastre uma localização antes de publicar um anúncio.")

    dados = dados.copy()
    dados["raio_m"] = dados.get("raio_m", settings.RAIO_PADRAO_KM * 1000)
    anuncio = Anuncio(comprador=comprador, **dados)
    anuncio.save()
    return anuncio


@transaction.atomic
def alterar_status_anuncio(*, anuncio, novo_status):
    transicoes_validas = {
        Anuncio.Status.ATIVO: {Anuncio.Status.PAUSADO, Anuncio.Status.ENCERRADO, Anuncio.Status.EM_NEGOCIACAO},
        Anuncio.Status.PAUSADO: {Anuncio.Status.ATIVO, Anuncio.Status.ENCERRADO},
        Anuncio.Status.EM_NEGOCIACAO: {Anuncio.Status.ATIVO},
    }
    if novo_status not in transicoes_validas.get(anuncio.status, set()):
        raise ValidationError("Transição de status inválida.")

    anuncio.status = novo_status
    anuncio.save(update_fields=["status", "atualizado_em"])
    return anuncio

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from quero.anuncios.models import Anuncio
from quero.negociacao.models import Negociacao
from quero.ofertas.models import EventoNegociacao
from quero.reputacao.models import Avaliacao

from .services import (
    notificar_avaliacao_publicada,
    notificar_evento_negociacao,
    notificar_negociacao_concluida,
    notificar_vendedores_compativeis,
)

logger = logging.getLogger(__name__)


def _apos_commit(callback, *args):
    def executar():
        try:
            callback(*args)
        except Exception:
            logger.exception(
                "Falha ao criar notificação de domínio (%s).",
                callback.__name__,
            )

    transaction.on_commit(executar)


@receiver(post_save, sender=Anuncio, dispatch_uid="notificacoes.anuncio_compativel")
def anuncio_criado(sender, instance, created, **kwargs):
    if created and instance.status == Anuncio.Status.ATIVO:
        # Anuncio.save materializes its spatial reach after post_save.
        _apos_commit(notificar_vendedores_compativeis, str(instance.pk))


@receiver(
    post_save,
    sender=EventoNegociacao,
    dispatch_uid="notificacoes.evento_negociacao",
)
def evento_negociacao_criado(sender, instance, created, **kwargs):
    if created:
        # Depois do commit a negociação aberta pelo aceite já existe e uma falha aqui não desfaz o evento.
        _apos_commit(notificar_evento_negociacao, instance.pk)


@receiver(
    post_save,
    sender=Negociacao,
    dispatch_uid="notificacoes.negociacao_concluida",
)
def negociacao_atualizada(sender, instance, **kwargs):
    if instance.status == Negociacao.Status.CONCLUIDA:
        _apos_commit(notificar_negociacao_concluida, instance.pk)


@receiver(
    post_save,
    sender=Avaliacao,
    dispatch_uid="notificacoes.avaliacao_publicada",
)
def avaliacao_publicada(sender, instance, **kwargs):
    if instance.publicada_em is not None:
        _apos_commit(notificar_avaliacao_publicada, instance.pk)

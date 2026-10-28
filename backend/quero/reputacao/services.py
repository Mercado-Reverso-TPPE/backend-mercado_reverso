from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from quero.negociacao.models import Negociacao

from .models import Avaliacao

# Prazo em dias para o sistema publicar a avaliação pendente caso a outra parte não avalie.
PRAZO_PUBLICACAO_DIAS = 7


def _partes_da_negociacao(negociacao: Negociacao):
    """Retorna (comprador, vendedor) de uma negociação, via Oferta → Anuncio."""
    oferta = negociacao.oferta
    return oferta.anuncio.comprador, oferta.vendedor


@transaction.atomic
def criar_avaliacao(*, autor, negociacao_id, nota, comentario=""):
    """
    Registra uma avaliação sigilosa de um participante sobre a contraparte.

    Regras:
    - A negociação deve estar concluída.
    - O autor precisa ser uma das duas partes (comprador ou vendedor).
    - Só é permitida uma avaliação por parte por negociação (UniqueConstraint no modelo).
    - A avaliação fica oculta (publicada_em=None) até o gatilho de publicação.
    """
    try:
        negociacao = Negociacao.objects.select_for_update().get(pk=negociacao_id)
    except Negociacao.DoesNotExist as exc:
        raise ValidationError("Negociação não encontrada.") from exc

    if negociacao.status != Negociacao.Status.CONCLUIDA:
        raise ValidationError("Só é possível avaliar negociações concluídas.")

    comprador, vendedor = _partes_da_negociacao(negociacao)

    if autor.pk == comprador.pk:
        avaliado = vendedor
    elif autor.pk == vendedor.pk:
        avaliado = comprador
    else:
        raise ValidationError("Você não participou desta negociação.")

    if Avaliacao.objects.filter(negociacao=negociacao, autor=autor).exists():
        raise ValidationError("Você já avaliou esta negociação.")

    avaliacao = Avaliacao.objects.create(
        negociacao=negociacao,
        autor=autor,
        avaliado=avaliado,
        nota=nota,
        comentario=comentario,
        publicada_em=None,
    )

    _tentar_publicar_par(negociacao)
    return avaliacao


def _tentar_publicar_par(negociacao: Negociacao):
    """
    Publica ambas as avaliações de uma negociação se as duas partes já avaliaram.
    Deve ser chamada dentro de uma transação atômica.
    """
    avaliacoes = list(Avaliacao.objects.filter(negociacao=negociacao, publicada_em__isnull=True))
    if len(avaliacoes) == 2:
        agora = timezone.now()
        for av in avaliacoes:
            av.publicada_em = agora
        Avaliacao.objects.bulk_update(avaliacoes, ["publicada_em"])
        from quero.notificacoes.services import notificar_avaliacao_publicada

        for avaliacao in avaliacoes:
            notificar_avaliacao_publicada(avaliacao.pk)


@transaction.atomic
def publicar_avaliacoes_vencidas():
    """
    Tarefa periódica: libera a avaliação da parte que avaliou quando o prazo expira
    e a outra ainda não avaliou.

    Retorna o número de avaliações publicadas.
    """
    prazo = timezone.now() - timedelta(days=PRAZO_PUBLICACAO_DIAS)
    pendentes = Avaliacao.objects.select_for_update().filter(
        publicada_em__isnull=True,
        criada_em__lte=prazo,
    )
    agora = timezone.now()
    ids = list(pendentes.values_list("pk", flat=True))
    count = pendentes.update(publicada_em=agora)
    if ids:
        from quero.notificacoes.services import notificar_avaliacao_publicada

        for avaliacao_id in ids:
            notificar_avaliacao_publicada(avaliacao_id)
    return count, ids


@transaction.atomic
def responder_avaliacao(*, avaliado, avaliacao_id, resposta):
    """
    Permite ao avaliado adicionar uma resposta pública única.

    Regras:
    - Só o avaliado pode responder.
    - A avaliação precisa estar publicada.
    - Resposta só pode ser enviada uma vez (imutável após envio).
    """
    try:
        avaliacao = Avaliacao.objects.select_for_update().get(pk=avaliacao_id)
    except Avaliacao.DoesNotExist as exc:
        raise ValidationError("Avaliação não encontrada.") from exc

    if avaliacao.avaliado_id != avaliado.pk:
        raise ValidationError("Você não é o avaliado desta avaliação.")

    if avaliacao.publicada_em is None:
        raise ValidationError("Esta avaliação ainda não foi publicada.")

    if avaliacao.respondida_em is not None:
        raise ValidationError("Esta avaliação já foi respondida e não pode ser alterada.")

    avaliacao.resposta = resposta
    avaliacao.respondida_em = timezone.now()
    avaliacao.save(update_fields=["resposta", "respondida_em"])
    return avaliacao


@transaction.atomic
def denunciar_avaliacao(*, denunciante, avaliacao_id, motivo=""):
    """
    Registra uma denúncia de comentário de avaliação na fila de moderação.

    - Cria uma AcaoModeracao do tipo denuncia_avaliacao em estado aberta.
    - Não altera a avaliação — ela permanece publicada até decisão do moderador.
    - Não permite denúncia duplicada aberta do mesmo denunciante para a mesma avaliação.
    """
    from quero.moderacao.models import AcaoModeracao

    try:
        avaliacao = Avaliacao.objects.get(pk=avaliacao_id)
    except Avaliacao.DoesNotExist as exc:
        raise ValidationError("Avaliação não encontrada.") from exc

    if avaliacao.publicada_em is None:
        raise ValidationError("Só é possível denunciar avaliações publicadas.")

    if denunciante.pk == avaliacao.autor_id:
        raise ValidationError("Você não pode denunciar sua própria avaliação.")

    ja_existe = AcaoModeracao.objects.filter(
        autor=denunciante,
        avaliacao=avaliacao,
        tipo=AcaoModeracao.Tipo.DENUNCIA_AVALIACAO,
        estado=AcaoModeracao.Estado.ABERTA,
    ).exists()
    if ja_existe:
        raise ValidationError("Você já denunciou esta avaliação.")

    acao = AcaoModeracao.objects.create(
        autor=denunciante,
        alvo=avaliacao.autor,
        tipo=AcaoModeracao.Tipo.DENUNCIA_AVALIACAO,
        estado=AcaoModeracao.Estado.ABERTA,
        avaliacao=avaliacao,
        motivo=motivo,
    )
    return acao

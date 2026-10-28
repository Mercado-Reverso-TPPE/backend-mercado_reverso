from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import Http404
from django.utils import timezone

from quero.anuncios.models import Anuncio
from quero.moderacao.services import bloqueio_entre
from quero.ofertas.models import EventoNegociacao, Oferta

from .models import Negociacao

MENSAGEM = EventoNegociacao.TipoEvento.MENSAGEM


def negociacao_da_oferta(oferta):
    try:
        return oferta.negociacao
    except ObjectDoesNotExist:
        return None


# Conversas (QRO-14): cada oferta é a conversa entre o comprador do anúncio e o vendedor.


def obter_conversa(*, oferta_id, usuario):
    oferta = (
        Oferta.objects.select_related("anuncio", "anuncio__comprador", "vendedor", "negociacao")
        .filter(pk=oferta_id)
        .first()
    )
    if oferta is None:
        raise Http404("Conversa não encontrada.")
    if usuario.pk not in (oferta.anuncio.comprador_id, oferta.vendedor_id):
        raise PermissionDenied("Você não participa desta conversa.")
    return oferta


def conversa_somente_leitura(oferta):
    if oferta.status in (Oferta.Status.RECUSADA, Oferta.Status.RETIRADA):
        return True
    if oferta.anuncio.status == Anuncio.Status.ENCERRADO:
        return True
    negociacao = negociacao_da_oferta(oferta)
    return negociacao is not None and negociacao.status != Negociacao.Status.EM_ANDAMENTO


def mensagens_da_conversa(oferta):
    return EventoNegociacao.objects.filter(oferta=oferta, tipo_evento=MENSAGEM).select_related("autor")


@transaction.atomic
def enviar_mensagem(*, oferta, autor, texto):
    oferta = Oferta.objects.select_for_update(of=("self",)).select_related("anuncio", "negociacao").get(pk=oferta.pk)
    comprador_id = oferta.anuncio.comprador_id
    if autor.pk not in (comprador_id, oferta.vendedor_id):
        raise PermissionDenied("Você não participa desta conversa.")
    texto = texto.strip()
    if not texto:
        raise ValidationError("A mensagem não pode ficar vazia.")
    if conversa_somente_leitura(oferta):
        raise ValidationError("Esta conversa foi encerrada e está disponível somente para leitura.")
    if bloqueio_entre(comprador_id, oferta.vendedor_id):
        raise ValidationError("Não é possível enviar mensagens: há um bloqueio entre vocês.")

    return EventoNegociacao.objects.create(
        oferta=oferta,
        autor=autor,
        status=oferta.status,
        tipo_evento=MENSAGEM,
        texto=texto,
    )


def marcar_mensagens_como_lidas(*, oferta, usuario):
    return (
        mensagens_da_conversa(oferta).filter(lida_em__isnull=True).exclude(autor=usuario).update(lida_em=timezone.now())
    )


def conversas_do_usuario(usuario):
    nao_lidas = Q(eventos__tipo_evento=MENSAGEM, eventos__lida_em__isnull=True) & ~Q(eventos__autor=usuario)
    return (
        Oferta.objects.filter(Q(vendedor=usuario) | Q(anuncio__comprador=usuario))
        .select_related("anuncio", "anuncio__comprador", "vendedor", "negociacao")
        .annotate(
            mensagens_nao_lidas=Count("eventos", filter=nao_lidas),
            ultima_mensagem_em=Max("eventos__registrado_em", filter=Q(eventos__tipo_evento=MENSAGEM)),
        )
    )


def total_mensagens_nao_lidas(usuario):
    return (
        EventoNegociacao.objects.filter(tipo_evento=MENSAGEM, lida_em__isnull=True)
        .filter(Q(oferta__vendedor=usuario) | Q(oferta__anuncio__comprador=usuario))
        .exclude(autor=usuario)
        .count()
    )


# Conclusão bilateral (QRO-16) e histórico (QRO-19).


def prazo_confirmacao():
    return timedelta(hours=settings.NEGOCIACAO_PRAZO_CONFIRMACAO_HORAS)


def prazo_confirmacao_vencido(negociacao, agora=None):
    if negociacao.conclusao_solicitada_em is None:
        return False
    return (agora or timezone.now()) >= negociacao.conclusao_solicitada_em + prazo_confirmacao()


def negociacoes_do_usuario(usuario):
    return (
        Negociacao.objects.filter(Q(oferta__vendedor=usuario) | Q(oferta__anuncio__comprador=usuario))
        .select_related(
            "oferta", "oferta__vendedor", "oferta__anuncio", "oferta__anuncio__comprador", "oferta__anuncio__categoria"
        )
        .prefetch_related("avaliacoes")
    )


def historico_do_usuario(usuario, *, papel=None, status=None):
    negociacoes = negociacoes_do_usuario(usuario).exclude(status=Negociacao.Status.EM_ANDAMENTO)
    if papel == "comprador":
        negociacoes = negociacoes.filter(oferta__anuncio__comprador=usuario)
    elif papel == "vendedor":
        negociacoes = negociacoes.filter(oferta__vendedor=usuario)
    if status:
        negociacoes = negociacoes.filter(status=status)
    return negociacoes


def _travar_negociacao(negociacao_id):
    return (
        Negociacao.objects.select_for_update(of=("self",))
        .select_related("oferta", "oferta__anuncio")
        .get(pk=negociacao_id)
    )


def _exigir_em_andamento(negociacao):
    if negociacao.status != Negociacao.Status.EM_ANDAMENTO:
        raise ValidationError("Esta negociação não está mais em andamento.")


def _concluir(negociacao, *, agora, confirmada):
    # O produto ofertado passa a vendido pelo receiver do catálogo ao salvar a negociação.
    negociacao.status = Negociacao.Status.CONCLUIDA
    negociacao.confirmada_em = agora if confirmada else None
    negociacao.concluida_em = agora
    negociacao.save(update_fields=["status", "confirmada_em", "concluida_em", "atualizada_em"])

    anuncio = Anuncio.objects.select_for_update().get(pk=negociacao.oferta.anuncio_id)
    anuncio.status = Anuncio.Status.ENCERRADO
    anuncio.save(update_fields=["status", "atualizado_em"])
    # As partes são convidadas a avaliar pelo signal de notificações (negociação concluída).
    return negociacao


def concluir_negociacoes_expiradas(*, usuario=None, negociacao_id=None, agora=None):
    """Confirma automaticamente as conclusões cujo prazo de resposta do comprador terminou."""
    agora = agora or timezone.now()
    vencidas = Negociacao.objects.filter(
        status=Negociacao.Status.EM_ANDAMENTO,
        conclusao_solicitada_em__lte=agora - prazo_confirmacao(),
    )
    if usuario is not None:
        vencidas = vencidas.filter(Q(oferta__vendedor=usuario) | Q(oferta__anuncio__comprador=usuario))
    if negociacao_id is not None:
        vencidas = vencidas.filter(pk=negociacao_id)

    concluidas = 0
    for pk in vencidas.values_list("pk", flat=True):
        with transaction.atomic():
            negociacao = _travar_negociacao(pk)
            if negociacao.status == Negociacao.Status.EM_ANDAMENTO and prazo_confirmacao_vencido(negociacao, agora):
                _concluir(negociacao, agora=agora, confirmada=False)
                concluidas += 1
    return concluidas


@transaction.atomic
def solicitar_conclusao(*, negociacao, usuario):
    negociacao = _travar_negociacao(negociacao.pk)
    if usuario.pk != negociacao.oferta.vendedor_id:
        raise PermissionDenied("Apenas o vendedor pode solicitar a conclusão.")
    _exigir_em_andamento(negociacao)
    if negociacao.conclusao_solicitada_em is not None:
        raise ValidationError("A conclusão já foi solicitada e aguarda a resposta do comprador.")
    negociacao.conclusao_solicitada_em = timezone.now()
    negociacao.save(update_fields=["conclusao_solicitada_em", "atualizada_em"])
    return negociacao


def confirmar_conclusao(*, negociacao, usuario):
    concluir_negociacoes_expiradas(negociacao_id=negociacao.pk)
    with transaction.atomic():
        negociacao = _travar_negociacao(negociacao.pk)
        if usuario.pk != negociacao.oferta.anuncio.comprador_id:
            raise PermissionDenied("Apenas o comprador pode confirmar a conclusão.")
        if negociacao.status == Negociacao.Status.CONCLUIDA:
            raise ValidationError("Esta negociação já foi concluída.")
        _exigir_em_andamento(negociacao)
        if negociacao.conclusao_solicitada_em is None:
            raise ValidationError("O vendedor ainda não solicitou a conclusão.")
        return _concluir(negociacao, agora=timezone.now(), confirmada=True)


def recusar_conclusao(*, negociacao, usuario):
    # A expiração é aplicada em transação própria para persistir mesmo quando a recusa é rejeitada.
    if concluir_negociacoes_expiradas(negociacao_id=negociacao.pk):
        raise ValidationError("O prazo de resposta terminou e a negociação foi concluída automaticamente.")
    with transaction.atomic():
        negociacao = _travar_negociacao(negociacao.pk)
        if usuario.pk != negociacao.oferta.anuncio.comprador_id:
            raise PermissionDenied("Apenas o comprador pode recusar a conclusão.")
        _exigir_em_andamento(negociacao)
        if negociacao.conclusao_solicitada_em is None:
            raise ValidationError("Não há solicitação de conclusão pendente.")
        negociacao.conclusao_solicitada_em = None
        negociacao.save(update_fields=["conclusao_solicitada_em", "atualizada_em"])
        return negociacao

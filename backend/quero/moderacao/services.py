from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from quero.contas.models import Usuario
from quero.ofertas.models import EventoNegociacao

from .models import AcaoModeracao


def bloqueio_entre(usuario_a_id, usuario_b_id):
    """Indica se há bloqueio ativo em qualquer sentido entre os dois usuários."""
    return AcaoModeracao.objects.filter(
        Q(autor_id=usuario_a_id, alvo_id=usuario_b_id) | Q(autor_id=usuario_b_id, alvo_id=usuario_a_id),
        tipo=AcaoModeracao.Tipo.BLOQUEIO_USUARIO,
        estado=AcaoModeracao.Estado.ATIVA,
    ).exists()


def bloqueios_do_usuario(usuario):
    return AcaoModeracao.objects.filter(
        autor=usuario,
        tipo=AcaoModeracao.Tipo.BLOQUEIO_USUARIO,
        estado=AcaoModeracao.Estado.ATIVA,
    ).select_related("alvo")


@transaction.atomic
def bloquear_usuario(*, autor, alvo_id, motivo=""):
    if alvo_id == autor.pk:
        raise ValidationError("Você não pode bloquear a si mesmo.")
    alvo = Usuario.objects.filter(pk=alvo_id, is_active=True).first()
    if alvo is None:
        raise ValidationError("Usuário não encontrado.")

    try:
        with transaction.atomic():
            return AcaoModeracao.objects.create(
                autor=autor,
                alvo=alvo,
                tipo=AcaoModeracao.Tipo.BLOQUEIO_USUARIO,
                estado=AcaoModeracao.Estado.ATIVA,
                motivo=motivo,
            )
    except IntegrityError as exc:
        raise ValidationError("Este usuário já está bloqueado.") from exc


@transaction.atomic
def desbloquear_usuario(*, autor, alvo_id):
    bloqueio = bloqueios_do_usuario(autor).select_for_update(of=("self",)).filter(alvo_id=alvo_id).first()
    if bloqueio is None:
        raise ValidationError("Não há bloqueio ativo para este usuário.")
    bloqueio.estado = AcaoModeracao.Estado.REVOGADA
    bloqueio.save(update_fields=["estado", "atualizada_em"])
    return bloqueio


@transaction.atomic
def denunciar_conversa(*, autor, oferta, motivo, mensagem_id=None):
    comprador_id = oferta.anuncio.comprador_id
    if autor.pk not in (comprador_id, oferta.vendedor_id):
        raise ValidationError("Apenas participantes podem denunciar esta conversa.")
    if not motivo.strip():
        raise ValidationError("Informe o motivo da denúncia.")

    mensagem = None
    if mensagem_id is not None:
        mensagem = EventoNegociacao.objects.filter(
            pk=mensagem_id,
            oferta=oferta,
            tipo_evento=EventoNegociacao.TipoEvento.MENSAGEM,
        ).first()
        if mensagem is None:
            raise ValidationError("A mensagem denunciada não pertence a esta conversa.")
        if mensagem.autor_id == autor.pk:
            raise ValidationError("Você não pode denunciar sua própria mensagem.")

    alvo_id = oferta.vendedor_id if autor.pk == comprador_id else comprador_id
    try:
        with transaction.atomic():
            return AcaoModeracao.objects.create(
                autor=autor,
                alvo_id=alvo_id,
                tipo=AcaoModeracao.Tipo.DENUNCIA_CONVERSA,
                estado=AcaoModeracao.Estado.ABERTA,
                oferta=oferta,
                evento=mensagem,
                motivo=motivo.strip(),
            )
    except IntegrityError as exc:
        raise ValidationError("Você já tem uma denúncia aberta para esta conversa.") from exc

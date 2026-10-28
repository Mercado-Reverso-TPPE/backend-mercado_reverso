import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.negociacao.models import Negociacao
from quero.ofertas.models import EventoNegociacao

from .catalogo import TipoNotificacao
from .models import EventoNotificacao, Notificacao, PreferenciaNotificacao

logger = logging.getLogger(__name__)


def _habilitada(usuario, tipo, canal):
    if tipo == TipoNotificacao.SEGURANCA_CONTA:
        return True
    preferencia = PreferenciaNotificacao.objects.filter(
        usuario=usuario,
        tipo=tipo,
        canal=canal,
    ).values_list("habilitada", flat=True).first()
    return preferencia is not False


def emitir_notificacao(
    *,
    usuario,
    tipo,
    titulo,
    mensagem,
    chave_evento,
    contexto=None,
    agrupamento="",
    anuncio=None,
    oferta=None,
    negociacao=None,
):
    """Persist an in-app event once, then deliver opted-in email after commit."""
    if tipo not in TipoNotificacao.values:
        raise ValueError(f"Tipo de notificação não catalogado: {tipo}")
    if len(chave_evento) > 180:
        raise ValueError("A chave de idempotência excede 180 caracteres.")
    if not agrupamento:
        agrupamento = f"{tipo}:{chave_evento}"[:100]
    contexto = contexto or {}
    with transaction.atomic():
        if EventoNotificacao.objects.filter(usuario=usuario, chave_evento=chave_evento).exists():
            return None

        app_habilitado = _habilitada(
            usuario,
            tipo,
            PreferenciaNotificacao.Canal.APLICATIVO,
        )
        notificacao = None
        if app_habilitado:
            notificacao = (
                Notificacao.objects.select_for_update()
                .filter(usuario=usuario, agrupamento=agrupamento)
                .first()
            )
            if notificacao is None:
                try:
                    with transaction.atomic():
                        notificacao = Notificacao.objects.create(
                            usuario=usuario,
                            tipo=tipo,
                            titulo=titulo,
                            mensagem=mensagem,
                            agrupamento=agrupamento,
                            anuncio=anuncio,
                            oferta=oferta,
                            negociacao=negociacao,
                        )
                except IntegrityError:
                    notificacao = Notificacao.objects.select_for_update().get(
                        usuario=usuario,
                        agrupamento=agrupamento,
                    )

        ledger, created = EventoNotificacao.objects.get_or_create(
            usuario=usuario,
            chave_evento=chave_evento,
            defaults={
                "notificacao": notificacao,
                "contexto": contexto,
            },
        )
        if not created:
            return None

        if app_habilitado:
            EventoNotificacao.objects.filter(pk=ledger.pk).update(notificacao=notificacao)
            entradas = list(notificacao.contexto or [])
            entradas.append(contexto)
            notificacao.contexto = entradas[-100:]
            notificacao.criada_em = timezone.now()
            notificacao.titulo = titulo
            notificacao.mensagem = mensagem
            notificacao.anuncio = anuncio or notificacao.anuncio
            notificacao.oferta = oferta or notificacao.oferta
            notificacao.negociacao = negociacao or notificacao.negociacao
            notificacao.lida_em = None
            notificacao.save(
                update_fields=(
                    "contexto",
                    "criada_em",
                    "titulo",
                    "mensagem",
                    "anuncio",
                    "oferta",
                    "negociacao",
                    "lida_em",
                )
            )

        if _habilitada(usuario, tipo, PreferenciaNotificacao.Canal.EMAIL):
            email = usuario.email
            transaction.on_commit(
                lambda: _enviar_email(
                    email=email,
                    tipo=tipo,
                    titulo=titulo,
                    mensagem=mensagem,
                    chave_evento=chave_evento,
                )
            )
        return notificacao


def _enviar_email(*, email, tipo, titulo, mensagem, chave_evento):
    try:
        enviado = send_mail(
            subject=titulo,
            message=mensagem,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        if not enviado:
            logger.error(
                "E-mail de notificação não enviado (tipo=%s, evento=%s).",
                tipo,
                chave_evento,
            )
    except Exception:
        logger.exception(
            "Falha ao enviar e-mail de notificação (tipo=%s, evento=%s).",
            tipo,
            chave_evento,
        )


def emitir_alerta_seguranca(*, usuario, titulo, mensagem, chave_evento, contexto=None):
    return emitir_notificacao(
        usuario=usuario,
        tipo=TipoNotificacao.SEGURANCA_CONTA,
        titulo=titulo,
        mensagem=mensagem,
        chave_evento=chave_evento,
        contexto=contexto,
        agrupamento=f"seguranca:{chave_evento}"[:100],
    )


def notificar_vendedores_compativeis(anuncio_id):
    anuncio = Anuncio.objects.select_related("comprador", "categoria").filter(
        pk=anuncio_id,
        status=Anuncio.Status.ATIVO,
    ).first()
    if anuncio is None:
        return 0
    produtos = Produto.objects.filter(
        categoria_id=anuncio.categoria_id,
        status=Produto.Status.DISPONIVEL,
        vendedor__ponto__isnull=False,
    )
    if anuncio.alcance is not None:
        produtos = produtos.filter(vendedor__ponto__intersects=anuncio.alcance)
    else:
        # A polygon can be temporarily unavailable while the location materialization runs.
        produtos = produtos.filter(
            Q(vendedor__cidade__iexact=anuncio.comprador.cidade)
            & Q(vendedor__uf__iexact=anuncio.comprador.uf)
        )
    recipients = produtos.exclude(vendedor_id=anuncio.comprador_id).values_list(
        "vendedor_id",
        flat=True,
    ).distinct()
    count = 0
    for recipient_id in recipients:
        from quero.contas.models import Usuario

        usuario = Usuario.objects.get(pk=recipient_id)
        notification = emitir_notificacao(
            usuario=usuario,
            tipo=TipoNotificacao.ANUNCIO_COMPATIVEL,
            titulo="Novo anúncio compatível na sua região",
            mensagem=f'“{anuncio.titulo}” pode combinar com um produto disponível do seu catálogo.',
            chave_evento=f"anuncio:{anuncio.pk}:regional:{usuario.pk}",
            agrupamento=f"anuncio_compativel:{usuario.pk}",
            anuncio=anuncio,
            contexto={
                "anuncio_id": str(anuncio.pk),
                "categoria": anuncio.categoria.nome,
                "titulo": anuncio.titulo,
            },
        )
        count += notification is not None
    return count


def notificar_evento_negociacao(evento_id):
    evento = EventoNegociacao.objects.select_related(
        "autor",
        "oferta",
        "oferta__anuncio",
        "oferta__anuncio__comprador",
        "oferta__vendedor",
    ).filter(pk=evento_id).first()
    if evento is None:
        return
    oferta = evento.oferta
    recipient = (
        oferta.vendedor
        if evento.autor_id == oferta.anuncio.comprador_id
        else oferta.anuncio.comprador
    )
    if recipient.pk == evento.autor_id:
        return
    builders = {
        EventoNegociacao.TipoEvento.ENVIADA: (
            TipoNotificacao.OFERTA_RECEBIDA,
            "Nova oferta recebida",
            "Você recebeu uma nova oferta para seu anúncio.",
        ),
        EventoNegociacao.TipoEvento.EDITADA: (
            TipoNotificacao.OFERTA_ATUALIZADA,
            "Oferta atualizada",
            "Uma oferta relacionada à sua negociação foi atualizada.",
        ),
        EventoNegociacao.TipoEvento.RETIRADA: (
            TipoNotificacao.OFERTA_ATUALIZADA,
            "Oferta retirada",
            "Uma oferta relacionada à sua negociação foi retirada.",
        ),
        EventoNegociacao.TipoEvento.CONTRAPROPOSTA: (
            TipoNotificacao.CONTRAPROPOSTA_RECEBIDA,
            "Nova contraproposta",
            "Você recebeu uma contraproposta. Confira a negociação para responder.",
        ),
        EventoNegociacao.TipoEvento.CONTRAPROPOSTA_ACEITA: (
            TipoNotificacao.NEGOCIACAO_ATUALIZADA,
            "Contraproposta aceita",
            "Sua contraproposta foi aceita.",
        ),
        EventoNegociacao.TipoEvento.CONTRAPROPOSTA_RECUSADA: (
            TipoNotificacao.NEGOCIACAO_ATUALIZADA,
            "Contraproposta recusada",
            "Sua contraproposta foi recusada.",
        ),
        EventoNegociacao.TipoEvento.CONTRAPROPOSTA_EXPIRADA: (
            TipoNotificacao.NEGOCIACAO_ATUALIZADA,
            "Contraproposta expirada",
            "Uma contraproposta da negociação expirou.",
        ),
        EventoNegociacao.TipoEvento.CONTRAPROPOSTA_SUBSTITUIDA: (
            TipoNotificacao.NEGOCIACAO_ATUALIZADA,
            "Contraproposta substituída",
            "Uma contraproposta da negociação foi substituída.",
        ),
        EventoNegociacao.TipoEvento.ACEITA: (
            TipoNotificacao.NEGOCIACAO_ATUALIZADA,
            "Oferta aceita",
            "Sua oferta foi aceita.",
        ),
        EventoNegociacao.TipoEvento.RECUSADA: (
            TipoNotificacao.NEGOCIACAO_ATUALIZADA,
            "Oferta recusada",
            "Sua oferta foi recusada.",
        ),
        EventoNegociacao.TipoEvento.MENSAGEM: (
            TipoNotificacao.MENSAGEM_RECEBIDA,
            "Nova mensagem",
            "Você recebeu uma mensagem. Acesse a negociação para lê-la.",
        ),
    }
    data = builders.get(evento.tipo_evento)
    if data is None:
        return
    tipo, titulo, mensagem = data
    negociacao = Negociacao.objects.filter(oferta_id=oferta.pk).first()
    emitir_notificacao(
        usuario=recipient,
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        chave_evento=f"evento-negociacao:{evento.pk}:{recipient.pk}",
        agrupamento=f"{tipo}:{oferta.pk}:{recipient.pk}",
        contexto={
            "evento_id": evento.pk,
            "oferta_id": str(oferta.pk),
            "evento": evento.tipo_evento,
        },
        anuncio=oferta.anuncio,
        oferta=oferta,
        negociacao=negociacao,
    )


def notificar_negociacao_concluida(negociacao_id):
    negociacao = Negociacao.objects.select_related(
        "oferta",
        "oferta__anuncio",
        "oferta__anuncio__comprador",
        "oferta__vendedor",
    ).filter(pk=negociacao_id, status=Negociacao.Status.CONCLUIDA).first()
    if negociacao is None:
        return
    oferta = negociacao.oferta
    for usuario in (oferta.anuncio.comprador, oferta.vendedor):
        emitir_notificacao(
            usuario=usuario,
            tipo=TipoNotificacao.NEGOCIACAO_CONCLUIDA,
            titulo="Negociação concluída",
            mensagem="A negociação foi concluída. Você já pode avaliar a outra parte.",
            chave_evento=f"negociacao-concluida:{negociacao.pk}:{usuario.pk}",
            agrupamento=f"negociacao-concluida:{negociacao.pk}:{usuario.pk}",
            contexto={"negociacao_id": str(negociacao.pk)},
            anuncio=oferta.anuncio,
            oferta=oferta,
            negociacao=negociacao,
        )


def notificar_avaliacao_publicada(avaliacao_id):
    from quero.reputacao.models import Avaliacao

    avaliacao = Avaliacao.objects.select_related(
        "avaliado",
        "negociacao",
        "negociacao__oferta",
        "negociacao__oferta__anuncio",
    ).filter(pk=avaliacao_id, publicada_em__isnull=False).first()
    if avaliacao is None:
        return
    oferta = avaliacao.negociacao.oferta
    emitir_notificacao(
        usuario=avaliacao.avaliado,
        tipo=TipoNotificacao.AVALIACAO_RECEBIDA,
        titulo="Uma avaliação foi publicada",
        mensagem="Uma avaliação sobre você está disponível.",
        chave_evento=f"avaliacao-publicada:{avaliacao.pk}:{avaliacao.avaliado_id}",
        agrupamento=f"avaliacao:{avaliacao.avaliado_id}",
        contexto={"avaliacao_id": str(avaliacao.pk)},
        anuncio=oferta.anuncio,
        oferta=oferta,
        negociacao=avaliacao.negociacao,
    )


def publicar_lembretes_contraproposta(*, agora=None, janela_horas=24):
    agora = agora or timezone.now()
    limite = agora + timedelta(hours=janela_horas)
    eventos = EventoNegociacao.objects.filter(
        tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
        resultado=EventoNegociacao.Resultado.PENDENTE,
        respondida_em__isnull=True,
        expira_em__gt=agora,
        expira_em__lte=limite,
    ).select_related(
        "autor",
        "oferta",
        "oferta__anuncio",
        "oferta__anuncio__comprador",
        "oferta__vendedor",
    )
    count = 0
    for evento in eventos.iterator():
        recipient = (
            evento.oferta.vendedor
            if evento.autor_id == evento.oferta.anuncio.comprador_id
            else evento.oferta.anuncio.comprador
        )
        notification = emitir_notificacao(
            usuario=recipient,
            tipo=TipoNotificacao.CONTRAPROPOSTA_VENCENDO,
            titulo="Sua contraproposta está perto do vencimento",
            mensagem="Responda à contraproposta antes do prazo para não perdê-la.",
            chave_evento=f"lembrete-contraproposta:{evento.pk}",
            agrupamento=f"lembrete-contraproposta:{evento.pk}",
            contexto={
                "evento_id": evento.pk,
                "oferta_id": str(evento.oferta_id),
                "expira_em": evento.expira_em.isoformat(),
            },
            anuncio=evento.oferta.anuncio,
            oferta=evento.oferta,
            negociacao=Negociacao.objects.filter(oferta_id=evento.oferta_id).first(),
        )
        count += notification is not None
    return count

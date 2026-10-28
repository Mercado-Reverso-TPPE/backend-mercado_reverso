from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.catalogo.services import copiar_foto_para_snapshot
from quero.negociacao.models import Negociacao

from .models import EventoNegociacao, Oferta

OFERTAS_ATIVAS = (Oferta.Status.ENVIADA, Oferta.Status.EM_NEGOCIACAO)


@transaction.atomic
def enviar_oferta(*, vendedor, anuncio_id, dados):
    try:
        anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
    except Anuncio.DoesNotExist as exc:
        raise ValidationError("O anúncio não existe.") from exc

    if anuncio.status != Anuncio.Status.ATIVO:
        raise ValidationError("Só é possível ofertar em anúncios ativos.")
    if anuncio.comprador_id == vendedor.pk:
        raise ValidationError("Não é possível ofertar no próprio anúncio.")
    ponto_vendedor = vendedor.ponto
    if ponto_vendedor is None:
        raise ValidationError("Cadastre uma localização antes de enviar uma oferta.")

    esta_no_raio = Anuncio.objects.filter(pk=anuncio.pk, alcance__intersects=ponto_vendedor).exists()
    if not esta_no_raio:
        raise ValidationError("Sua localização está fora do raio deste anúncio.")

    dados = dados.copy()
    produto_id = dados.pop("produto_id", None)
    if produto_id is not None:
        dados.update(_snapshot_do_produto(vendedor=vendedor, produto_id=produto_id, dados=dados))
    elif any(dados.get(campo) in (None, "") for campo in CAMPOS_COPIADOS_DO_PRODUTO):
        raise ValidationError("Informe descrição, estado de conservação e preço ou escolha um produto do catálogo.")

    try:
        with transaction.atomic():
            oferta = Oferta.objects.create(anuncio=anuncio, vendedor=vendedor, **dados)
    except IntegrityError as exc:
        if dados.get("foto_produto_snapshot"):
            default_storage.delete(dados["foto_produto_snapshot"])
        raise ValidationError("Você já tem uma oferta ativa neste anúncio.") from exc

    EventoNegociacao.objects.create(
        oferta=oferta,
        autor=vendedor,
        preco=oferta.preco,
        status=oferta.status,
        tipo_evento=EventoNegociacao.TipoEvento.ENVIADA,
    )
    return oferta


CAMPOS_COPIADOS_DO_PRODUTO = ("descricao", "estado_conservacao", "preco")


def _snapshot_do_produto(*, vendedor, produto_id, dados):
    """Copia os dados do produto para a oferta; edições futuras no catálogo não a afetam."""
    produto = Produto.objects.select_for_update().filter(pk=produto_id, vendedor=vendedor).first()
    if produto is None:
        raise ValidationError("O produto não existe no seu catálogo.")
    if produto.status != Produto.Status.DISPONIVEL:
        raise ValidationError("Só é possível ofertar produtos disponíveis.")
    snapshot = {campo: dados.get(campo) or getattr(produto, campo) for campo in CAMPOS_COPIADOS_DO_PRODUTO}
    snapshot.update(
        produto=produto,
        nome_produto_snapshot=produto.nome,
        foto_produto_snapshot=copiar_foto_para_snapshot(produto),
    )
    return snapshot


@transaction.atomic
def editar_oferta(*, oferta, vendedor, dados):
    anuncio_id = Oferta.objects.values_list("anuncio_id", flat=True).get(pk=oferta.pk)
    anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
    oferta = Oferta.objects.select_for_update().get(pk=oferta.pk)
    if oferta.vendedor_id != vendedor.pk:
        raise ValidationError("Você só pode alterar suas próprias ofertas.")
    if oferta.status != Oferta.Status.ENVIADA or anuncio.status != Anuncio.Status.ATIVO:
        raise ValidationError("Esta oferta não pode mais ser alterada.")

    mudou_preco = "preco" in dados and dados["preco"] != oferta.preco
    for campo, valor in dados.items():
        setattr(oferta, campo, valor)
    oferta.save(update_fields=[*dados.keys(), "atualizada_em"])
    if mudou_preco:
        EventoNegociacao.objects.create(
            oferta=oferta,
            autor=vendedor,
            preco=oferta.preco,
            status=oferta.status,
            tipo_evento=EventoNegociacao.TipoEvento.EDITADA,
        )
    return oferta


@transaction.atomic
def retirar_oferta(*, oferta, vendedor):
    anuncio_id = Oferta.objects.values_list("anuncio_id", flat=True).get(pk=oferta.pk)
    anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
    oferta = Oferta.objects.select_for_update().get(pk=oferta.pk)
    if oferta.vendedor_id != vendedor.pk:
        raise ValidationError("Você só pode retirar suas próprias ofertas.")
    if oferta.status != Oferta.Status.ENVIADA or anuncio.status != Anuncio.Status.ATIVO:
        raise ValidationError("Esta oferta não pode mais ser retirada.")
    oferta.status = Oferta.Status.RETIRADA
    oferta.save(update_fields=["status", "atualizada_em"])
    EventoNegociacao.objects.create(
        oferta=oferta,
        autor=vendedor,
        preco=oferta.preco,
        status=oferta.status,
        tipo_evento=EventoNegociacao.TipoEvento.RETIRADA,
    )
    return oferta


def _lock_offer(oferta_id):
    try:
        anuncio_id = Oferta.objects.values_list("anuncio_id", flat=True).get(pk=oferta_id)
        anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
        oferta = Oferta.objects.select_for_update().get(pk=oferta_id)
    except (Oferta.DoesNotExist, Anuncio.DoesNotExist) as exc:
        raise ValidationError("A oferta não existe.") from exc
    return anuncio, oferta


def _is_participant(anuncio, oferta, usuario):
    return usuario.pk in (anuncio.comprador_id, oferta.vendedor_id)


def _open_counteroffer(oferta):
    return (
        EventoNegociacao.objects.select_for_update()
        .filter(
            oferta=oferta,
            tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
        )
        .filter(Q(resultado=EventoNegociacao.Resultado.PENDENTE) | Q(resultado__isnull=True))
        .filter(respondida_em__isnull=True)
        .first()
    )


def _record_counteroffer_outcome(oferta, contraproposta, *, event_type, result, actor, reason=""):
    now = timezone.now()
    contraproposta.resultado = result
    contraproposta.respondida_em = now
    contraproposta.save(update_fields=["resultado", "respondida_em"])
    EventoNegociacao.objects.create(
        oferta=oferta,
        autor=actor,
        preco=contraproposta.preco,
        status=oferta.status,
        tipo_evento=event_type,
        justificativa=reason,
        rodada=contraproposta.rodada,
        respondida_em=now,
        resultado=result,
    )


def _expire_counteroffer(oferta, contraproposta, *, now=None):
    now = now or timezone.now()
    if contraproposta.expira_em is None or contraproposta.expira_em > now:
        return False
    _record_counteroffer_outcome(
        oferta,
        contraproposta,
        event_type=EventoNegociacao.TipoEvento.CONTRAPROPOSTA_EXPIRADA,
        result=EventoNegociacao.Resultado.EXPIRADA,
        actor=contraproposta.autor,
    )
    return True


def _expire_if_due(oferta, contraproposta):
    if _expire_counteroffer(oferta, contraproposta):
        return True
    return False


def _counteroffer_count(oferta):
    return EventoNegociacao.objects.filter(
        oferta=oferta,
        tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
        rodada__gt=0,
    ).count()


def _may_counter(anuncio, oferta, actor):
    latest = (
        EventoNegociacao.objects.filter(
            oferta=oferta,
            tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
            rodada__gt=0,
        )
        .order_by("-rodada", "-registrado_em", "-pk")
        .first()
    )
    if latest is None:
        return actor.pk == anuncio.comprador_id
    response = EventoNegociacao.objects.filter(
        oferta=oferta,
        rodada=latest.rodada,
        tipo_evento__in=(
            EventoNegociacao.TipoEvento.CONTRAPROPOSTA_ACEITA,
            EventoNegociacao.TipoEvento.CONTRAPROPOSTA_RECUSADA,
            EventoNegociacao.TipoEvento.CONTRAPROPOSTA_EXPIRADA,
            EventoNegociacao.TipoEvento.CONTRAPROPOSTA_SUBSTITUIDA,
        ),
    ).order_by("-registrado_em", "-pk").first()
    if response is not None and response.tipo_evento != EventoNegociacao.TipoEvento.CONTRAPROPOSTA_EXPIRADA:
        return response.autor_id == actor.pk
    return latest.autor_id != actor.pk


@transaction.atomic
def enviar_contraproposta(*, oferta_id, autor, preco, texto=""):
    if preco is None or preco <= 0:
        raise ValidationError("O preço da contraproposta deve ser positivo.")
    anuncio, oferta = _lock_offer(oferta_id)
    if not _is_participant(anuncio, oferta, autor):
        raise ValidationError("Você não participa desta negociação.")
    if anuncio.status != Anuncio.Status.ATIVO or oferta.status not in OFERTAS_ATIVAS:
        raise ValidationError("Esta oferta não aceita contrapropostas.")

    pendente = _open_counteroffer(oferta)
    if pendente is not None:
        if _expire_if_due(oferta, pendente):
            pendente = None
        else:
            raise ValidationError("Já existe uma contraproposta aguardando resposta.")

    limite = settings.CONTRAPROPOSTA_LIMITE_RODADAS
    if _counteroffer_count(oferta) >= limite:
        raise ValidationError("O limite de rodadas de contraproposta foi atingido.")
    if not _may_counter(anuncio, oferta, autor):
        raise ValidationError("A contraproposta deve ser enviada pela outra parte.")
    prazo_horas = settings.CONTRAPROPOSTA_PRAZO_HORAS
    if limite < 1 or prazo_horas < 1:
        raise ValidationError("A configuração de contrapropostas deve definir limite e prazo positivos.")

    rodada = _counteroffer_count(oferta) + 1
    if oferta.status == Oferta.Status.ENVIADA:
        oferta.status = Oferta.Status.EM_NEGOCIACAO
        oferta.save(update_fields=["status", "atualizada_em"])
    return EventoNegociacao.objects.create(
        oferta=oferta,
        autor=autor,
        preco=preco,
        status=oferta.status,
        tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
        texto=texto,
        rodada=rodada,
        expira_em=timezone.now() + timedelta(hours=prazo_horas),
        resultado=EventoNegociacao.Resultado.PENDENTE,
    )


def _mark_competitors_rejected(anuncio, oferta, actor):
    competitors = (
        Oferta.objects.select_for_update()
        .filter(
            anuncio=anuncio,
            status__in=(Oferta.Status.ENVIADA, Oferta.Status.EM_NEGOCIACAO),
        )
        .exclude(pk=oferta.pk)
        .order_by("pk")
    )
    now = timezone.now()
    for competitor in competitors:
        for pending in (
            EventoNegociacao.objects.select_for_update()
            .filter(oferta=competitor, tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA)
            .filter(Q(resultado=EventoNegociacao.Resultado.PENDENTE) | Q(resultado__isnull=True))
            .filter(respondida_em__isnull=True)
        ):
            _record_counteroffer_outcome(
                competitor,
                pending,
                event_type=EventoNegociacao.TipoEvento.CONTRAPROPOSTA_SUBSTITUIDA,
                result=EventoNegociacao.Resultado.SUBSTITUIDA,
                actor=actor,
            )
        competitor.status = Oferta.Status.RECUSADA
        competitor.save(update_fields=["status", "atualizada_em"])
        EventoNegociacao.objects.create(
            oferta=competitor,
            autor=actor,
            preco=competitor.preco,
            status=competitor.status,
            tipo_evento=EventoNegociacao.TipoEvento.RECUSADA,
            justificativa="Outra oferta foi aceita para este anúncio.",
            respondida_em=now,
            resultado=EventoNegociacao.Resultado.RECUSADA,
        )


def _accept_locked(anuncio, oferta, *, actor, final_price, accepted_counter=None):
    if anuncio.status != Anuncio.Status.ATIVO or oferta.status not in OFERTAS_ATIVAS:
        raise ValidationError("Esta oferta não pode mais ser aceita.")
    if accepted_counter is None and _open_counteroffer(oferta) is not None:
        raise ValidationError("Responda à contraproposta aberta antes de aceitar a oferta.")
    if oferta.produto_id:
        produto = Produto.objects.select_for_update().get(pk=oferta.produto_id)
        if produto.status != Produto.Status.DISPONIVEL:
            raise ValidationError("O produto vinculado não está disponível para reserva.")

    if accepted_counter is not None:
        _record_counteroffer_outcome(
            oferta,
            accepted_counter,
            event_type=EventoNegociacao.TipoEvento.CONTRAPROPOSTA_ACEITA,
            result=EventoNegociacao.Resultado.ACEITA,
            actor=actor,
        )
    oferta.preco = final_price
    oferta.status = Oferta.Status.ACEITA
    oferta.save(update_fields=["preco", "status", "atualizada_em"])
    _mark_competitors_rejected(anuncio, oferta, actor)
    anuncio.status = Anuncio.Status.EM_NEGOCIACAO
    anuncio.save(update_fields=["status", "atualizado_em"])
    EventoNegociacao.objects.create(
        oferta=oferta,
        autor=actor,
        preco=final_price,
        status=oferta.status,
        tipo_evento=EventoNegociacao.TipoEvento.ACEITA,
        rodada=accepted_counter.rodada if accepted_counter else 0,
        respondida_em=timezone.now(),
        resultado=EventoNegociacao.Resultado.ACEITA,
    )
    return Negociacao.objects.create(anuncio=anuncio, oferta=oferta, valor_final=final_price)


@transaction.atomic
def aceitar_oferta(*, oferta_id, comprador):
    anuncio, oferta = _lock_offer(oferta_id)
    if anuncio.comprador_id != comprador.pk:
        raise ValidationError("Somente o comprador do anúncio pode aceitar a oferta.")
    if not _is_participant(anuncio, oferta, comprador):
        raise ValidationError("Você não participa desta negociação.")
    pending = _open_counteroffer(oferta)
    if pending is not None:
        _expire_if_due(oferta, pending)
        if pending.respondida_em is None:
            raise ValidationError("Responda à contraproposta aberta antes de aceitar a oferta.")
    return _accept_locked(anuncio, oferta, actor=comprador, final_price=oferta.preco)


@transaction.atomic
def recusar_oferta(*, oferta_id, comprador, justificativa=""):
    anuncio, oferta = _lock_offer(oferta_id)
    if anuncio.comprador_id != comprador.pk:
        raise ValidationError("Somente o comprador do anúncio pode recusar a oferta.")
    if oferta.status not in OFERTAS_ATIVAS:
        raise ValidationError("Esta oferta não pode mais ser recusada.")
    pending = _open_counteroffer(oferta)
    if pending is not None:
        _expire_if_due(oferta, pending)
        if pending.respondida_em is None:
            raise ValidationError("Responda à contraproposta aberta antes de recusar a oferta.")
    oferta.status = Oferta.Status.RECUSADA
    oferta.save(update_fields=["status", "atualizada_em"])
    EventoNegociacao.objects.create(
        oferta=oferta,
        autor=comprador,
        preco=oferta.preco,
        status=oferta.status,
        tipo_evento=EventoNegociacao.TipoEvento.RECUSADA,
        justificativa=justificativa,
        respondida_em=timezone.now(),
        resultado=EventoNegociacao.Resultado.RECUSADA,
    )
    return oferta


@transaction.atomic
def responder_contraproposta(*, oferta_id, usuario, acao, justificativa="", preco=None, texto=""):
    anuncio, oferta = _lock_offer(oferta_id)
    if not _is_participant(anuncio, oferta, usuario):
        raise ValidationError("Você não participa desta negociação.")
    if anuncio.status != Anuncio.Status.ATIVO or oferta.status not in OFERTAS_ATIVAS:
        raise ValidationError("Esta oferta não aceita respostas.")
    pending = _open_counteroffer(oferta)
    if pending is None:
        raise ValidationError("Não há contraproposta aguardando resposta.")
    if pending.autor_id == usuario.pk:
        raise ValidationError("Somente o destinatário pode responder à contraproposta.")
    if _expire_if_due(oferta, pending):
        return None

    if acao == "aceitar":
        _accept_locked(
            anuncio,
            oferta,
            actor=usuario,
            final_price=pending.preco,
            accepted_counter=pending,
        )
        return oferta
    if acao == "recusar":
        _record_counteroffer_outcome(
            oferta,
            pending,
            event_type=EventoNegociacao.TipoEvento.CONTRAPROPOSTA_RECUSADA,
            result=EventoNegociacao.Resultado.RECUSADA,
            actor=usuario,
            reason=justificativa,
        )
        return oferta
    if acao == "contrapropor":
        if preco is None or preco <= 0:
            raise ValidationError("O preço da contraproposta deve ser positivo.")
        _record_counteroffer_outcome(
            oferta,
            pending,
            event_type=EventoNegociacao.TipoEvento.CONTRAPROPOSTA_SUBSTITUIDA,
            result=EventoNegociacao.Resultado.SUBSTITUIDA,
            actor=usuario,
        )
        limite = settings.CONTRAPROPOSTA_LIMITE_RODADAS
        prazo_horas = settings.CONTRAPROPOSTA_PRAZO_HORAS
        if _counteroffer_count(oferta) >= limite:
            raise ValidationError("O limite de rodadas de contraproposta foi atingido.")
        if limite < 1 or prazo_horas < 1:
            raise ValidationError("A configuração de contrapropostas deve definir limite e prazo positivos.")
        rodada = _counteroffer_count(oferta) + 1
        EventoNegociacao.objects.create(
            oferta=oferta,
            autor=usuario,
            preco=preco,
            status=oferta.status,
            tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
            texto=texto,
            rodada=rodada,
            expira_em=timezone.now() + timedelta(hours=prazo_horas),
            resultado=EventoNegociacao.Resultado.PENDENTE,
        )
        return oferta
    raise ValidationError("Ação de resposta inválida.")


@transaction.atomic
def cancelar_negociacao(*, negociacao_id, usuario):
    try:
        anuncio_id = Negociacao.objects.values_list("anuncio_id", flat=True).get(pk=negociacao_id)
        anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
        negociacao = (
            Negociacao.objects.select_for_update()
            .select_related("oferta")
            .get(pk=negociacao_id)
        )
    except (Negociacao.DoesNotExist, Anuncio.DoesNotExist) as exc:
        raise ValidationError("A negociação não existe.") from exc
    oferta = Oferta.objects.select_for_update().get(pk=negociacao.oferta_id)
    if not _is_participant(anuncio, oferta, usuario):
        raise ValidationError("Você não participa desta negociação.")
    if negociacao.status != Negociacao.Status.EM_ANDAMENTO:
        raise ValidationError("Somente negociações em andamento podem ser canceladas.")
    if anuncio.status != Anuncio.Status.EM_NEGOCIACAO:
        raise ValidationError("O anúncio não está em negociação.")

    negociacao.status = Negociacao.Status.CANCELADA
    negociacao.cancelada_em = timezone.now()
    negociacao.save(update_fields=["status", "cancelada_em", "atualizada_em"])
    anuncio.status = Anuncio.Status.ATIVO
    anuncio.save(update_fields=["status", "atualizado_em"])
    if oferta.produto_id:
        produto = Produto.objects.select_for_update().get(pk=oferta.produto_id)
        if produto.status == Produto.Status.RESERVADO:
            produto.status = Produto.Status.DISPONIVEL
            produto.save(update_fields=["status", "atualizado_em"])
    EventoNegociacao.objects.create(
        oferta=oferta,
        autor=usuario,
        preco=negociacao.valor_final,
        status=oferta.status,
        tipo_evento=EventoNegociacao.TipoEvento.NEGOCIACAO_CANCELADA,
        respondida_em=timezone.now(),
    )
    return negociacao


def expirar_contrapropostas_vencidas(*, agora=None):
    agora = agora or timezone.now()
    ids = list(
        EventoNegociacao.objects.filter(
            tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
        )
        .filter(Q(resultado=EventoNegociacao.Resultado.PENDENTE) | Q(resultado__isnull=True))
        .filter(respondida_em__isnull=True, expira_em__lte=agora)
        .values_list("oferta_id", flat=True)
        .distinct()
    )
    expiradas = 0
    for oferta_id in ids:
        with transaction.atomic():
            anuncio, oferta = _lock_offer(oferta_id)
            if oferta.status not in OFERTAS_ATIVAS:
                continue
            pending = _open_counteroffer(oferta)
            if pending and _expire_counteroffer(oferta, pending, now=agora):
                expiradas += 1
    return expiradas

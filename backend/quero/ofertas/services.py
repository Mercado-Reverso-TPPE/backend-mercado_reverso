from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ObjectDoesNotExist

from quero.anuncios.models import Anuncio

from .models import HistoricoOferta, Oferta


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
    try:
        ponto_vendedor = vendedor.localizacao.ponto
    except ObjectDoesNotExist as exc:
        raise ValidationError("Cadastre uma localização antes de enviar uma oferta.") from exc

    esta_no_raio = Anuncio.objects.filter(pk=anuncio.pk, alcance__intersects=ponto_vendedor).exists()
    if not esta_no_raio:
        raise ValidationError("Sua localização está fora do raio deste anúncio.")

    try:
        with transaction.atomic():
            oferta = Oferta.objects.create(anuncio=anuncio, vendedor=vendedor, **dados)
    except IntegrityError as exc:
        raise ValidationError("Você já tem uma oferta ativa neste anúncio.") from exc

    HistoricoOferta.objects.create(oferta=oferta, autor=vendedor, preco=oferta.preco, status=oferta.status)
    return oferta


@transaction.atomic
def editar_oferta(*, oferta, vendedor, dados):
    oferta = Oferta.objects.select_for_update().get(pk=oferta.pk)
    if oferta.vendedor_id != vendedor.pk:
        raise ValidationError("Você só pode alterar suas próprias ofertas.")
    if oferta.status != Oferta.Status.ENVIADA:
        raise ValidationError("Esta oferta não pode mais ser alterada.")

    mudou_preco = "preco" in dados and dados["preco"] != oferta.preco
    for campo, valor in dados.items():
        setattr(oferta, campo, valor)
    oferta.save(update_fields=[*dados.keys(), "atualizada_em"])
    if mudou_preco:
        HistoricoOferta.objects.create(oferta=oferta, autor=vendedor, preco=oferta.preco, status=oferta.status)
    return oferta


@transaction.atomic
def retirar_oferta(*, oferta, vendedor):
    oferta = Oferta.objects.select_for_update().get(pk=oferta.pk)
    if oferta.vendedor_id != vendedor.pk:
        raise ValidationError("Você só pode retirar suas próprias ofertas.")
    if oferta.status != Oferta.Status.ENVIADA:
        raise ValidationError("Esta oferta não pode mais ser retirada.")
    oferta.status = Oferta.Status.RETIRADA
    oferta.save(update_fields=["status", "atualizada_em"])
    HistoricoOferta.objects.create(oferta=oferta, autor=vendedor, preco=oferta.preco, status=oferta.status)
    return oferta

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.catalogo.services import copiar_foto_para_snapshot

from .models import EventoNegociacao, Oferta


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
    oferta = Oferta.objects.select_for_update().get(pk=oferta.pk)
    if oferta.vendedor_id != vendedor.pk:
        raise ValidationError("Você só pode retirar suas próprias ofertas.")
    if oferta.status != Oferta.Status.ENVIADA:
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

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Max, Min

from quero.anuncios.models import Anuncio

from .models import Palpite


@transaction.atomic
def criar_ou_atualizar_palpite(*, vendedor, anuncio_id, valor):
    try:
        anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
    except Anuncio.DoesNotExist as exc:
        raise ValidationError("O anúncio não existe.") from exc

    if anuncio.status != Anuncio.Status.ATIVO:
        raise ValidationError("Só é possível enviar palpites para anúncios ativos.")
    if anuncio.comprador_id == vendedor.pk:
        raise ValidationError("Não é possível enviar um palpite para o próprio anúncio.")
    if vendedor.ponto is None:
        raise ValidationError("Cadastre uma localização antes de enviar um palpite.")
    if not Anuncio.objects.filter(pk=anuncio.pk, alcance__intersects=vendedor.ponto).exists():
        raise ValidationError("Sua localização está fora do raio deste anúncio.")

    palpite, criado = Palpite.objects.update_or_create(
        anuncio=anuncio,
        vendedor=vendedor,
        defaults={"valor": valor},
    )
    return palpite, criado


def obter_estimativa_preco(*, anuncio):
    agregados = anuncio.palpites.aggregate(
        vendedores=Count("vendedor", distinct=True),
        minimo=Min("valor"),
        media=Avg("valor"),
        maximo=Max("valor"),
    )
    if agregados["vendedores"] < 3:
        return {"disponivel": False}

    media = agregados["media"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if anuncio.preco_min is None and anuncio.preco_max is None:
        diverge = None
    else:
        diverge = (anuncio.preco_min is not None and media < anuncio.preco_min) or (
            anuncio.preco_max is not None and media > anuncio.preco_max
        )

    return {
        "disponivel": True,
        "minimo": agregados["minimo"],
        "media": media,
        "maximo": agregados["maximo"],
        "diverge_da_faixa_solicitada": diverge,
    }

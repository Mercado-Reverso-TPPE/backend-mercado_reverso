from decimal import Decimal

from django.contrib.gis.db.models.functions import Distance
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, F, FloatField, Q, Value
from django.db.models.functions import Cast, Coalesce

from quero.anuncios.models import Anuncio
from quero.ofertas.models import BuscaSalva

Ordenacao = BuscaSalva.Ordenacao

# Anúncios sem orçamento ficam no fim em ambas as ordenações de preço.
_SEM_ORCAMENTO_CRESCENTE = Value(Decimal("99999999.99"))
_SEM_ORCAMENTO_DECRESCENTE = Value(Decimal("-1"))

# Cada ordenação termina em "id" para ser total: a paginação por chave depende disso.
ORDENACOES = {
    Ordenacao.DISTANCIA: (("distancia_m", False), ("criado_em", True), ("id", True)),
    Ordenacao.RECENTES: (("criado_em", True), ("id", True)),
    Ordenacao.PRECO_MINIMO: (("orcamento_ordem", False), ("criado_em", True), ("id", True)),
    Ordenacao.PRECO_MAXIMO: (("orcamento_ordem", True), ("criado_em", True), ("id", True)),
}


def anuncios_visiveis(usuario):
    """Anúncios ativos cujo alcance cobre a localização do usuário, com a distância em metros.

    Toda busca parte deste queryset, então nenhum filtro amplia o conjunto além dele.
    """
    if usuario.ponto is None:
        # Mantém as anotações para que ordenação e paginação funcionem sobre o conjunto vazio.
        return Anuncio.objects.annotate(
            distancia_m=Value(None, output_field=FloatField()),
            ofertas_ativas=Value(0),
        ).none()
    return (
        Anuncio.objects.filter(status=Anuncio.Status.ATIVO, alcance__intersects=usuario.ponto)
        .select_related("comprador", "categoria")
        .annotate(
            distancia_m=Cast(Distance("comprador__ponto", usuario.ponto), FloatField()),
            ofertas_ativas=Count(
                "ofertas",
                filter=Q(ofertas__status__in=("enviada", "aceita")),
                distinct=True,
            ),
        )
    )


def buscar_anuncios(
    *,
    usuario,
    termo="",
    categoria=None,
    preco_min=None,
    preco_max=None,
    distancia_max_km=None,
    ordenacao=Ordenacao.DISTANCIA,
):
    anuncios = anuncios_visiveis(usuario)
    for palavra in termo.split():
        anuncios = anuncios.filter(Q(titulo__icontains=palavra) | Q(descricao__icontains=palavra))
    if categoria is not None:
        anuncios = anuncios.filter(categoria=categoria)
    # O orçamento do anúncio precisa se sobrepor à faixa informada; limites ausentes não restringem.
    if preco_min is not None:
        anuncios = anuncios.filter(Q(preco_max__isnull=True) | Q(preco_max__gte=preco_min))
    if preco_max is not None:
        anuncios = anuncios.filter(Q(preco_min__isnull=True) | Q(preco_min__lte=preco_max))
    if distancia_max_km is not None:
        anuncios = anuncios.filter(distancia_m__lte=distancia_max_km * 1000)
    if ordenacao in (Ordenacao.PRECO_MINIMO, Ordenacao.PRECO_MAXIMO):
        sem_orcamento = _SEM_ORCAMENTO_CRESCENTE if ordenacao == Ordenacao.PRECO_MINIMO else _SEM_ORCAMENTO_DECRESCENTE
        anuncios = anuncios.annotate(
            orcamento_ordem=Coalesce(
                F("preco_max"),
                F("preco_min"),
                sem_orcamento,
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
    return anuncios.order_by(*(f"-{campo}" if decrescente else campo for campo, decrescente in ORDENACOES[ordenacao]))


def filtros_da_busca_salva(busca):
    return {
        "termo": busca.termo,
        "categoria": busca.categoria,
        "preco_min": busca.preco_min,
        "preco_max": busca.preco_max,
        "distancia_max_km": busca.distancia_max_km,
        "ordenacao": busca.ordenacao,
    }


@transaction.atomic
def salvar_busca(*, usuario, dados, busca=None):
    busca = busca or BuscaSalva(usuario=usuario)
    if busca.usuario_id != usuario.pk:
        raise ValidationError("Você só pode alterar suas próprias buscas salvas.")
    for campo, valor in dados.items():
        setattr(busca, campo, valor)
    try:
        with transaction.atomic():
            busca.save()
    except IntegrityError as exc:
        raise ValidationError({"nome": "Você já tem uma busca salva com este nome."}) from exc
    return busca

import logging
import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import Distance
from django.db import transaction
from django.db.models import FloatField, Q, Value
from django.db.models.functions import Cast
from django.utils import timezone

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.descoberta.models import Recomendacao

logger = logging.getLogger(__name__)

_TOKENS_IGNORADOS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "mais", "na", "nas", "no", "nos", "o", "os",
    "para", "por", "que", "sem", "um", "uma",
}
_TEMPO_ATUALIZACAO = timedelta(minutes=5)
_TEMPO_LEASE = timedelta(minutes=10)


def _pesos_normalizados(pesos=None):
    pesos = pesos or getattr(settings, "PESOS_RECOMENDACAO", {})
    padroes = {"categoria": 40, "palavras_chave": 25, "preco": 20, "distancia": 15}
    valores = {chave: Decimal(str(pesos.get(chave, padrao))) for chave, padrao in padroes.items()}
    if any(valor < 0 for valor in valores.values()) or sum(valores.values()) <= 0:
        raise ValueError("Pesos de recomendação devem ser não negativos e ter soma maior que zero.")
    total = sum(valores.values())
    return {chave: valor / total for chave, valor in valores.items()}


def _termos(texto):
    return {
        termo
        for termo in re.findall(r"[^\W_]+", texto.casefold(), flags=re.UNICODE)
        if len(termo) > 1 and termo not in _TOKENS_IGNORADOS
    }


def _pontuacao_preco(produto, anuncio):
    preco = Decimal(produto.preco)
    minimo = anuncio.preco_min
    maximo = anuncio.preco_max
    if minimo is None and maximo is None:
        return Decimal("50"), "O anúncio não informa faixa de preço."
    if minimo is not None and (maximo is None or preco >= minimo) and (maximo is None or preco <= maximo):
        return Decimal("100"), "O preço está dentro da faixa informada."
    if minimo is not None and preco < minimo:
        diferenca = minimo - preco
        nota = Decimal("100") * max(Decimal("0"), Decimal("1") - diferenca / max(minimo, Decimal("1")))
    else:
        diferenca = preco - maximo
        nota = Decimal("100") * max(Decimal("0"), Decimal("1") - diferenca / max(maximo, Decimal("1")))
    return nota, "O preço está fora da faixa; a pontuação diminui conforme a diferença."


def compatibility_score(anuncio, produto, distancia_m, pesos=None):
    """Calcula uma pontuação determinística de 0–100 e seus fatores explicáveis."""
    termos_anuncio = _termos(f"{anuncio.titulo} {anuncio.descricao}")
    termos_produto = _termos(f"{produto.nome} {produto.descricao}")
    termos_encontrados = sorted(termos_anuncio & termos_produto)
    if termos_anuncio:
        nota_palavras = Decimal(100) * Decimal(len(termos_encontrados)) / Decimal(len(termos_anuncio))
        explicacao_palavras = f"{len(termos_encontrados)} de {len(termos_anuncio)} termos relevantes coincidem."
    else:
        nota_palavras = Decimal("50")
        explicacao_palavras = "Não há termos relevantes para comparar."

    nota_preco, explicacao_preco = _pontuacao_preco(produto, anuncio)
    raio_m = Decimal(anuncio.raio_m)
    distancia = max(Decimal("0"), Decimal(str(distancia_m)))
    nota_distancia = Decimal(100) * max(Decimal("0"), Decimal(1) - distancia / raio_m)
    nota_categoria = Decimal(100) if produto.categoria_id == anuncio.categoria_id else Decimal(0)
    pesos_usados = _pesos_normalizados(pesos)

    componentes = {
        "categoria": {
            "pontuacao": int(nota_categoria),
            "explicacao": "Categoria igual à do anúncio." if nota_categoria else "Categoria diferente da do anúncio.",
        },
        "palavras_chave": {
            "pontuacao": int(nota_palavras.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "termos_encontrados": termos_encontrados,
            "explicacao": explicacao_palavras,
        },
        "preco": {
            "pontuacao": int(nota_preco.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "explicacao": explicacao_preco,
        },
        "distancia": {
            "pontuacao": int(nota_distancia.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "distancia_m": float(distancia.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
            "raio_m": anuncio.raio_m,
            "explicacao": "Pontuação decrescente linearmente até o limite do raio.",
        },
    }
    for componente, peso in pesos_usados.items():
        componentes[componente]["peso_percentual"] = float(
            (peso * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
    notas = {
        "categoria": nota_categoria,
        "palavras_chave": nota_palavras,
        "preco": nota_preco,
        "distancia": nota_distancia,
    }
    total = sum(notas[chave] * pesos_usados[chave] for chave in notas)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), componentes


def _produtos_para_anuncio(anuncio):
    return (
        Produto.objects.filter(
            status=Produto.Status.DISPONIVEL,
            vendedor__is_active=True,
            vendedor__ponto__isnull=False,
            vendedor__ponto__intersects=anuncio.alcance,
        )
        .exclude(vendedor_id=anuncio.comprador_id)
        .exclude(ofertas__anuncio_id=anuncio.pk)
        .select_related("categoria", "vendedor")
        .annotate(
            distancia_m=Cast(
                Distance(
                    "vendedor__ponto",
                    Value(
                        anuncio.comprador.ponto,
                        output_field=gis_models.PointField(geography=True, srid=4326),
                    ),
                ),
                FloatField(),
            )
        )
        .order_by("pk")
    )


def recomendacoes_visiveis(anuncio):
    if anuncio.alcance is None or anuncio.comprador.ponto is None:
        return Recomendacao.objects.none()
    return (
        Recomendacao.objects.filter(
            anuncio=anuncio,
            anuncio__status=Anuncio.Status.ATIVO,
            produto__status=Produto.Status.DISPONIVEL,
            produto__vendedor__is_active=True,
            produto__vendedor__ponto__isnull=False,
            produto__vendedor__ponto__intersects=anuncio.alcance,
            estado__in=(Recomendacao.Estado.ATIVA, Recomendacao.Estado.CONVITE_ENVIADO),
        )
        .exclude(produto__vendedor_id=anuncio.comprador_id)
        .exclude(produto__ofertas__anuncio_id=anuncio.pk)
        .select_related("produto", "produto__categoria")
        .annotate(
            distancia_m=Cast(
                Distance("produto__vendedor__ponto", "anuncio__comprador__ponto"),
                FloatField(),
            )
        )
        .order_by("-pontuacao", "produto_id")
    )


@transaction.atomic
def solicitar_atualizacao(anuncio):
    anuncio = Anuncio.objects.select_for_update().get(pk=anuncio.pk)
    if anuncio.status != Anuncio.Status.ATIVO:
        return anuncio
    atualizacao_pendente = anuncio.recomendacoes_solicitadas_em is not None
    desatualizada = (
        anuncio.recomendacoes_calculadas_em is None
        or anuncio.recomendacoes_calculadas_em < timezone.now() - _TEMPO_ATUALIZACAO
    )
    if desatualizada and not atualizacao_pendente:
        agora = timezone.now()
        anuncio.recomendacoes_solicitadas_em = agora
        anuncio.recomendacoes_tentar_em = agora
        anuncio.recomendacoes_ultimo_erro = ""
        Anuncio.objects.filter(pk=anuncio.pk).update(
            recomendacoes_solicitadas_em=agora,
            recomendacoes_tentar_em=agora,
            recomendacoes_ultimo_erro="",
        )
    return anuncio


def atualizar_recomendacoes(anuncio):
    if anuncio.status != Anuncio.Status.ATIVO or anuncio.alcance is None:
        return
    for produto in _produtos_para_anuncio(anuncio).iterator():
        pontuacao, explicacao = compatibility_score(anuncio, produto, produto.distancia_m)
        Recomendacao.objects.update_or_create(
            anuncio=anuncio,
            produto=produto,
            defaults={"pontuacao": pontuacao, "explicacao": explicacao},
        )


def processar_proxima_atualizacao():
    agora = timezone.now()
    with transaction.atomic():
        anuncio = (
            Anuncio.objects.select_for_update(skip_locked=True)
            .filter(
                recomendacoes_solicitadas_em__isnull=False,
                recomendacoes_tentar_em__lte=agora,
            )
            .filter(
                Q(recomendacoes_processando_em__isnull=True)
                | Q(recomendacoes_processando_em__lt=agora - _TEMPO_LEASE)
            )
            .order_by("recomendacoes_solicitadas_em", "pk")
            .first()
        )
        if anuncio is None:
            return False
        Anuncio.objects.filter(pk=anuncio.pk).update(
            recomendacoes_processando_em=agora,
            recomendacoes_tentativas=anuncio.recomendacoes_tentativas + 1,
        )
        anuncio_id = anuncio.pk

    try:
        anuncio = Anuncio.objects.select_related("comprador").get(pk=anuncio_id)
        with transaction.atomic():
            atualizar_recomendacoes(anuncio)
            Anuncio.objects.filter(pk=anuncio_id).update(
                recomendacoes_solicitadas_em=None,
                recomendacoes_processando_em=None,
                recomendacoes_calculadas_em=timezone.now(),
                recomendacoes_tentar_em=None,
                recomendacoes_tentativas=0,
                recomendacoes_ultimo_erro="",
            )
    except Exception as exc:
        logger.exception("Falha ao atualizar recomendações do anúncio %s", anuncio_id)
        with transaction.atomic():
            anuncio = Anuncio.objects.select_for_update().get(pk=anuncio_id)
            Anuncio.objects.filter(pk=anuncio_id).update(
                recomendacoes_processando_em=None,
                recomendacoes_tentar_em=timezone.now()
                + timedelta(minutes=min(2 ** min(anuncio.recomendacoes_tentativas, 6), 60)),
                recomendacoes_ultimo_erro=str(exc)[:2000],
            )
        return True
    return True


@transaction.atomic
def descartar_recomendacao(*, anuncio, recomendacao_id):
    recomendacao = (
        Recomendacao.objects.select_for_update()
        .filter(anuncio=anuncio, pk=recomendacao_id)
        .first()
    )
    if recomendacao is None:
        return None
    if recomendacao.estado == Recomendacao.Estado.DESCARTADA:
        return recomendacao
    if recomendacao.estado != Recomendacao.Estado.ATIVA:
        raise ValueError("Somente recomendações ativas podem ser descartadas.")
    recomendacao.estado = Recomendacao.Estado.DESCARTADA
    recomendacao.save(update_fields=("estado",))
    return recomendacao


@transaction.atomic
def convidar_vendedor(*, anuncio, recomendacao_id):
    anuncio = Anuncio.objects.select_for_update().get(pk=anuncio.pk)
    recomendacao = (
        Recomendacao.objects.select_for_update()
        .select_related("produto", "produto__vendedor")
        .filter(anuncio=anuncio, pk=recomendacao_id)
        .first()
    )
    if recomendacao is None:
        return None
    if recomendacao.estado == Recomendacao.Estado.CONVITE_ENVIADO:
        return recomendacao
    if recomendacao.estado != Recomendacao.Estado.ATIVA:
        raise ValueError("Somente recomendações ativas podem gerar um convite.")
    produto = Produto.objects.select_for_update().select_related("vendedor").get(pk=recomendacao.produto_id)
    if not recomendacoes_visiveis(anuncio).filter(pk=recomendacao.pk).exists():
        raise ValueError("O produto não está mais disponível para recomendação.")

    from quero.notificacoes.catalogo import TipoNotificacao
    from quero.notificacoes.services import emitir_notificacao

    recomendacao.produto = produto
    emitir_notificacao(
        usuario=produto.vendedor,
        tipo=TipoNotificacao.CONVITE_RECOMENDACAO,
        titulo="Convite para enviar uma oferta",
        mensagem=(
            f"O comprador do anúncio “{anuncio.titulo}” convidou você a enviar uma oferta "
            f"pelo produto “{produto.nome}”. Nenhuma oferta foi criada."
        ),
        chave_evento=f"convite-recomendacao:{recomendacao.pk}",
        contexto={"recomendacao_id": str(recomendacao.pk), "produto_id": str(produto.pk)},
        anuncio=anuncio,
        agrupamento=f"recomendacao:{recomendacao.pk}",
    )
    recomendacao.estado = Recomendacao.Estado.CONVITE_ENVIADO
    recomendacao.save(update_fields=("estado",))
    return recomendacao

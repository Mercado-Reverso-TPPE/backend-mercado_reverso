from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.contas.models import Usuario
from quero.negociacao.models import Negociacao, Palpite
from quero.negociacao.views_palpites import (
    EstimativaPrecoAnuncioView,
    PalpiteAnuncioView,
)
from quero.ofertas.models import EventoNegociacao, Oferta


def _request(view, method, user, anuncio, data=None):
    factory = APIRequestFactory()
    request = getattr(factory, method)(
        f"/api/v1/anuncios/{anuncio.pk}/{method}",
        data=data,
        format="json",
    )
    force_authenticate(request, user=user)
    return view.as_view()(request, anuncio_id=anuncio.pk)


def _vendedor_no_raio(anuncio, email):
    vendedor = Usuario.objects.create_user(email=email, password="senha-segura-123", nome=email)
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])
    return vendedor


@pytest.mark.django_db
def test_vendedor_substitui_palpite_sem_criar_oferta_ou_negociacao(anuncio):
    vendedor = _vendedor_no_raio(anuncio, "vendedor-palpite@example.com")
    produto = Produto.objects.create(
        vendedor=vendedor,
        categoria=anuncio.categoria,
        nome="Notebook",
        descricao="Notebook disponível",
        estado_conservacao=Produto.EstadoConservacao.NOVO,
        preco=Decimal("200.00"),
    )

    primeira = _request(PalpiteAnuncioView, "post", vendedor, anuncio, {"valor": "125.00"})
    substituicao = _request(PalpiteAnuncioView, "post", vendedor, anuncio, {"valor": "150.00"})

    assert primeira.status_code == status.HTTP_201_CREATED
    assert substituicao.status_code == status.HTTP_200_OK
    assert substituicao.data == {"valor": "150.00"}
    assert Palpite.objects.filter(anuncio=anuncio, vendedor=vendedor).count() == 1
    assert Palpite.objects.get(anuncio=anuncio, vendedor=vendedor).valor == Decimal("150.00")
    assert not Oferta.objects.filter(anuncio=anuncio).exists()
    assert not EventoNegociacao.objects.exists()
    assert not Negociacao.objects.exists()
    produto.refresh_from_db()
    assert produto.status == Produto.Status.DISPONIVEL
    assert anuncio.status == Anuncio.Status.ATIVO


@pytest.mark.django_db
def test_estimativa_indisponivel_ate_tres_vendedores_distintos(anuncio):
    primeiro = _vendedor_no_raio(anuncio, "primeiro@example.com")
    segundo = _vendedor_no_raio(anuncio, "segundo@example.com")
    primeiro_reenvio = _request(PalpiteAnuncioView, "post", primeiro, anuncio, {"valor": "100.00"})
    _request(PalpiteAnuncioView, "post", primeiro, anuncio, {"valor": "120.00"})
    _request(PalpiteAnuncioView, "post", segundo, anuncio, {"valor": "130.00"})

    resposta = _request(EstimativaPrecoAnuncioView, "get", anuncio.comprador, anuncio)

    assert primeiro_reenvio.status_code == status.HTTP_201_CREATED
    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data == {"disponivel": False}
    assert "minimo" not in resposta.data
    assert Palpite.objects.filter(anuncio=anuncio).values("vendedor").distinct().count() == 2


@pytest.mark.django_db
def test_estimativa_agrega_sem_expor_identidades_ou_valores_individuais(anuncio):
    anuncio.preco_min = Decimal("100.00")
    anuncio.preco_max = Decimal("200.00")
    anuncio.save(update_fields=["preco_min", "preco_max"])
    for index, valor in enumerate(("50.00", "110.00", "190.00", "300.00")):
        vendedor = _vendedor_no_raio(anuncio, f"vendedor-{index}@example.com")
        _request(
            PalpiteAnuncioView,
            "post",
            vendedor,
            anuncio,
            {"valor": valor},
        )

    resposta = _request(EstimativaPrecoAnuncioView, "get", anuncio.comprador, anuncio)

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data == {
        "disponivel": True,
        "minimo": "50.00",
        "media": "162.50",
        "maximo": "300.00",
        "diverge_da_faixa_solicitada": False,
    }
    assert not {"vendedor", "vendedor_id", "nome", "palpites", "valores"} & set(resposta.data)
    assert "110.00" not in str(resposta.data)
    assert "190.00" not in str(resposta.data)


@pytest.mark.django_db
def test_estimativa_indica_media_fora_da_faixa_ou_nulo_sem_faixa(anuncio):
    vendedores = [_vendedor_no_raio(anuncio, f"faixa-{index}@example.com") for index in range(3)]
    for vendedor in vendedores:
        _request(
            PalpiteAnuncioView,
            "post",
            vendedor,
            anuncio,
            {"valor": "300.00"},
        )
    anuncio.preco_min = Decimal("100.00")
    anuncio.preco_max = Decimal("200.00")
    anuncio.save(update_fields=["preco_min", "preco_max"])

    fora_da_faixa = _request(EstimativaPrecoAnuncioView, "get", anuncio.comprador, anuncio)
    anuncio.preco_min = None
    anuncio.preco_max = None
    anuncio.save(update_fields=["preco_min", "preco_max"])
    sem_faixa = _request(EstimativaPrecoAnuncioView, "get", anuncio.comprador, anuncio)

    assert fora_da_faixa.data["diverge_da_faixa_solicitada"] is True
    assert sem_faixa.data["diverge_da_faixa_solicitada"] is None


@pytest.mark.django_db
def test_controle_de_papel_e_validacoes_do_palpite(anuncio, vendedor):
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])

    palpite_proprio = _request(
        PalpiteAnuncioView,
        "post",
        anuncio.comprador,
        anuncio,
        {"valor": "100.00"},
    )
    estimativa_por_vendedor = _request(EstimativaPrecoAnuncioView, "get", vendedor, anuncio)
    estimativa_por_terceiro = _request(
        EstimativaPrecoAnuncioView,
        "get",
        _vendedor_no_raio(anuncio, "terceiro@example.com"),
        anuncio,
    )
    valor_invalido = _request(PalpiteAnuncioView, "post", vendedor, anuncio, {"valor": "0"})

    assert palpite_proprio.status_code == status.HTTP_400_BAD_REQUEST
    assert estimativa_por_vendedor.status_code == status.HTTP_403_FORBIDDEN
    assert estimativa_por_terceiro.status_code == status.HTTP_403_FORBIDDEN
    assert valor_invalido.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
@pytest.mark.parametrize(
    "estado",
    [Anuncio.Status.PAUSADO, Anuncio.Status.EM_NEGOCIACAO, Anuncio.Status.ENCERRADO],
)
def test_palpite_exige_anuncio_ativo(anuncio, vendedor, estado):
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])
    anuncio.status = estado
    anuncio.save(update_fields=["status"])

    resposta = _request(PalpiteAnuncioView, "post", vendedor, anuncio, {"valor": "100.00"})

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST
    assert not Palpite.objects.filter(anuncio=anuncio).exists()


@pytest.mark.django_db
def test_palpite_exige_localizacao_no_raio(anuncio, vendedor):
    resposta_sem_localizacao = _request(PalpiteAnuncioView, "post", vendedor, anuncio, {"valor": "100.00"})
    vendedor.ponto = Point(-48.0, -23.5505, srid=4326)
    vendedor.save(update_fields=["ponto"])
    resposta_fora_do_raio = _request(PalpiteAnuncioView, "post", vendedor, anuncio, {"valor": "100.00"})

    assert resposta_sem_localizacao.status_code == status.HTTP_400_BAD_REQUEST
    assert resposta_fora_do_raio.status_code == status.HTTP_400_BAD_REQUEST
    assert not Palpite.objects.filter(anuncio=anuncio).exists()

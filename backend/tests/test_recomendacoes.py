from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from quero.catalogo.models import Produto
from quero.descoberta.models import Recomendacao
from quero.descoberta.recomendacao_views import (
    ConvidarVendedorRecomendacaoView,
    DescartarRecomendacaoView,
    RecomendacoesAnuncioView,
)
from quero.descoberta.recomendacoes import (
    atualizar_recomendacoes,
    compatibility_score,
    processar_proxima_atualizacao,
    recomendacoes_visiveis,
)
from quero.negociacao.models import Negociacao
from quero.notificacoes.models import Notificacao
from quero.ofertas.models import Oferta


@pytest.fixture
def produto(anuncio, vendedor):
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=("ponto",))
    return Produto.objects.create(
        vendedor=vendedor,
        categoria=anuncio.categoria,
        nome="Notebook para estudo",
        descricao="Notebook seminovo para estudar",
        estado_conservacao=Produto.EstadoConservacao.SEMINOVO,
        preco=Decimal("1000.00"),
    )


@pytest.mark.django_db
def test_pontuacao_tem_componentes_explicaveis_e_pesos_ajustaveis(anuncio, produto):
    score, explicacao = compatibility_score(
        anuncio,
        produto,
        distancia_m=0,
        pesos={"categoria": 1, "palavras_chave": 0, "preco": 0, "distancia": 0},
    )

    assert score == Decimal("100.00")
    assert explicacao["categoria"]["pontuacao"] == 100
    assert "notebook" in explicacao["palavras_chave"]["termos_encontrados"]
    assert explicacao["preco"]["pontuacao"] == 50
    assert explicacao["distancia"]["pontuacao"] == 100


@pytest.mark.django_db
def test_pontuacao_de_preco_e_distancia_diminui_fora_da_faixa(anuncio, produto):
    anuncio.preco_min = Decimal("1000")
    anuncio.preco_max = Decimal("1200")
    produto.preco = Decimal("1500")
    score_fora, explicacao = compatibility_score(
        anuncio,
        produto,
        distancia_m=anuncio.raio_m,
        pesos={"categoria": 0, "palavras_chave": 0, "preco": 1, "distancia": 0},
    )

    assert score_fora == Decimal("75.00")
    produto.preco = Decimal("1100")
    score_na_faixa, _ = compatibility_score(
        anuncio,
        produto,
        distancia_m=0,
        pesos={"categoria": 0, "palavras_chave": 0, "preco": 1, "distancia": 0},
    )
    assert score_fora < score_na_faixa
    assert explicacao["distancia"]["pontuacao"] == 0


@pytest.mark.django_db
def test_atualizacao_exclui_fora_do_raio_indisponivel_inativo_e_ja_ofertado(anuncio, produto, vendedor):
    vendedor_distante = type(vendedor).objects.create_user(
        email="distante@example.com", password="senha-valida-123", nome="Distante"
    )
    vendedor_distante.ponto = Point(-48.0, -23.5505, srid=4326)
    vendedor_distante.save(update_fields=("ponto",))
    distante = type(produto).objects.create(
        vendedor=vendedor_distante,
        categoria=anuncio.categoria,
        nome="Notebook distante",
        descricao="Notebook",
        estado_conservacao=Produto.EstadoConservacao.NOVO,
        preco=Decimal("900.00"),
    )
    indisponivel = type(produto).objects.create(
        vendedor=type(vendedor).objects.create_user(
            email="inativo@example.com", password="senha-valida-123", nome="Inativo", is_active=False
        ),
        categoria=anuncio.categoria,
        nome="Notebook indisponível",
        descricao="Notebook",
        estado_conservacao=Produto.EstadoConservacao.NOVO,
        preco=Decimal("900.00"),
    )
    indisponivel.vendedor.ponto = anuncio.comprador.ponto
    indisponivel.vendedor.save(update_fields=("ponto",))
    indisponivel.status = Produto.Status.RESERVADO
    indisponivel.save(update_fields=("status",))

    vendedor_inativo_disponivel = type(vendedor).objects.create_user(
        email="inativo-disponivel@example.com",
        password="senha-valida-123",
        nome="Vendedor inativo",
        is_active=False,
    )
    vendedor_inativo_disponivel.ponto = anuncio.comprador.ponto
    vendedor_inativo_disponivel.save(update_fields=("ponto",))
    produto_vendedor_inativo = type(produto).objects.create(
        vendedor=vendedor_inativo_disponivel,
        categoria=anuncio.categoria,
        nome="Notebook vendedor inativo",
        descricao="Notebook",
        estado_conservacao=Produto.EstadoConservacao.NOVO,
        preco=Decimal("900.00"),
    )

    vendedor_reservado = type(vendedor).objects.create_user(
        email="reservado@example.com", password="senha-valida-123", nome="Vendedor reservado"
    )
    vendedor_reservado.ponto = anuncio.comprador.ponto
    vendedor_reservado.save(update_fields=("ponto",))
    produto_reservado = type(produto).objects.create(
        vendedor=vendedor_reservado,
        categoria=anuncio.categoria,
        nome="Notebook reservado",
        descricao="Notebook",
        estado_conservacao=Produto.EstadoConservacao.NOVO,
        preco=Decimal("900.00"),
        status=Produto.Status.RESERVADO,
    )

    vendedor_no_raio = type(vendedor).objects.create_user(
        email="oferta@example.com", password="senha-valida-123", nome="Já ofertou"
    )
    vendedor_no_raio.ponto = anuncio.comprador.ponto
    vendedor_no_raio.save(update_fields=("ponto",))
    ja_ofertado = type(produto).objects.create(
        vendedor=vendedor_no_raio,
        categoria=anuncio.categoria,
        nome="Produto já ofertado",
        descricao="Notebook",
        estado_conservacao=Produto.EstadoConservacao.NOVO,
        preco=Decimal("900.00"),
    )
    Oferta.objects.create(
        anuncio=anuncio,
        vendedor=vendedor_no_raio,
        produto=ja_ofertado,
        descricao=ja_ofertado.descricao,
        estado_conservacao=ja_ofertado.estado_conservacao,
        preco=ja_ofertado.preco,
    )

    atualizar_recomendacoes(anuncio)

    visiveis = set(recomendacoes_visiveis(anuncio).values_list("produto_id", flat=True))
    assert visiveis == {produto.pk}
    assert distante.pk not in visiveis
    assert indisponivel.pk not in visiveis
    assert produto_vendedor_inativo.pk not in visiveis
    assert produto_reservado.pk not in visiveis
    assert ja_ofertado.pk not in visiveis


@pytest.mark.django_db
def test_descartada_permanece_excluida_apos_recarga(anuncio, produto):
    atualizar_recomendacoes(anuncio)
    recomendacao = Recomendacao.objects.get(anuncio=anuncio, produto=produto)

    request = APIRequestFactory().post("/")
    force_authenticate(request, user=anuncio.comprador)
    response = DescartarRecomendacaoView.as_view()(
        request, anuncio_id=anuncio.pk, recomendacao_id=recomendacao.pk
    )
    assert response.status_code == status.HTTP_200_OK

    atualizar_recomendacoes(anuncio)
    recomendacao.refresh_from_db()
    assert recomendacao.estado == Recomendacao.Estado.DESCARTADA
    assert not recomendacoes_visiveis(anuncio).exists()


@pytest.mark.django_db
def test_consulta_devolve_contrato_seguro_e_enfileira_sem_calcular_na_requisicao(anuncio, produto):
    request = APIRequestFactory().get("/")
    force_authenticate(request, user=anuncio.comprador)

    response = RecomendacoesAnuncioView.as_view()(request, anuncio_id=anuncio.pk)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["atualizacao_pendente"] is True
    assert response.data["resultados"] == []
    assert response.data.keys() == {"atualizacao_pendente", "calculada_em", "resultados"}
    anuncio.refresh_from_db()
    assert anuncio.recomendacoes_solicitadas_em is not None

    assert processar_proxima_atualizacao() is True
    request = APIRequestFactory().get("/")
    force_authenticate(request, user=anuncio.comprador)
    response = RecomendacoesAnuncioView.as_view()(request, anuncio_id=anuncio.pk)
    item = response.data["resultados"][0]
    assert item["pontuacao"] is not None
    assert item["explicacao"]["categoria"]["pontuacao"] == 100
    assert set(item) == {
        "id",
        "produto_id",
        "nome",
        "categoria",
        "categoria_nome",
        "preco",
        "estado_conservacao",
        "distancia_m",
        "pontuacao",
        "explicacao",
        "estado",
        "calculada_em",
    }


@pytest.mark.django_db
def test_convite_notifica_vendedor_sem_criar_oferta_ou_negociacao(anuncio, produto):
    recomendacao = Recomendacao.objects.create(anuncio=anuncio, produto=produto, pontuacao=Decimal("90"))

    def convidar():
        request = APIRequestFactory().post("/")
        force_authenticate(request, user=anuncio.comprador)
        return ConvidarVendedorRecomendacaoView.as_view()(
            request, anuncio_id=anuncio.pk, recomendacao_id=recomendacao.pk
        )

    resposta = convidar()

    assert resposta.status_code == status.HTTP_200_OK
    assert "nenhuma oferta ou negociação" in resposta.data["mensagem"]
    recomendacao.refresh_from_db()
    assert recomendacao.estado == Recomendacao.Estado.CONVITE_ENVIADO
    assert Notificacao.objects.filter(usuario=produto.vendedor, anuncio=anuncio).count() == 1
    assert Oferta.objects.filter(anuncio=anuncio).count() == 0
    assert Negociacao.objects.filter(anuncio=anuncio).count() == 0

    assert convidar().status_code == status.HTTP_200_OK
    assert Notificacao.objects.filter(usuario=produto.vendedor, anuncio=anuncio).count() == 1

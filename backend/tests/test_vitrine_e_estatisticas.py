import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework import status

from quero.anuncios.models import Anuncio, Categoria
from quero.catalogo.models import Produto
from quero.contas.models import Usuario

LATITUDE = -23.5505
LONGITUDE = -46.6333
_sequencia = itertools.count()


def criar_usuario(deslocamento_longitude=None):
    """Pessoa em São Paulo, deslocada para leste: 0,01 grau de longitude ≈ 1 km."""
    numero = next(_sequencia)
    usuario = Usuario.objects.create_user(
        email=f"vitrine{numero}@example.com", password="Senha-forte-123!", nome=f"Pessoa {numero}"
    )
    if deslocamento_longitude is not None:
        usuario.ponto = Point(LONGITUDE + deslocamento_longitude, LATITUDE, srid=4326)
        usuario.save(update_fields=["ponto"])
    return usuario


def criar_anuncio(comprador, categoria, titulo, *, preco_max=None, status_anuncio=Anuncio.Status.ATIVO):
    anuncio = Anuncio.objects.create(
        comprador=comprador,
        categoria=categoria,
        titulo=titulo,
        descricao="Descrição",
        preco_max=preco_max,
        raio_m=20_000,
    )
    Anuncio.objects.filter(pk=anuncio.pk).update(status=status_anuncio, criado_em=timezone.now() - timedelta(hours=1))
    return anuncio


def percorrer(cliente_api, url):
    vistos = []
    while url:
        resposta = cliente_api.get(url)
        assert resposta.status_code == status.HTTP_200_OK, resposta.data
        vistos.extend(item["id"] for item in resposta.data["results"])
        url = resposta.data["next"]
    return vistos


def criar_produto(vendedor, categoria, nome, preco, *, status_produto=Produto.Status.DISPONIVEL):
    produto = Produto.objects.create(
        vendedor=vendedor,
        categoria=categoria,
        nome=nome,
        descricao="Bem conservado",
        estado_conservacao=Produto.EstadoConservacao.USADO_BOM,
        preco=Decimal(preco),
    )
    if status_produto != Produto.Status.DISPONIVEL:
        Produto.objects.filter(pk=produto.pk).update(status=status_produto)
    return produto


@pytest.fixture
def vendedor_sp(db):
    return criar_usuario(0)


@pytest.fixture
def games(db):
    return Categoria.objects.get_or_create(slug="games", defaults={"nome": "Games"})[0]


@pytest.fixture
def vitrine(categoria, games):
    """Produtos a ~1, 3 e 5 km de quem busca, além de produtos que nunca devem aparecer."""
    perto, medio, longe = criar_usuario(0.01), criar_usuario(0.03), criar_usuario(0.05)
    distante = criar_usuario(1.0)  # ~100 km
    visiveis = {
        "ps5": criar_produto(perto, games, "PlayStation 5", "3200"),
        "tv": criar_produto(medio, categoria, "Smart TV 55", "2200"),
        "switch": criar_produto(longe, games, "Nintendo Switch OLED", "1850"),
    }
    invisiveis = [
        criar_produto(perto, games, "Xbox reservado", "1500", status_produto=Produto.Status.RESERVADO),
        criar_produto(perto, games, "Xbox vendido", "1500", status_produto=Produto.Status.VENDIDO),
        criar_produto(distante, games, "PS4 distante", "900"),
    ]
    return visiveis, invisiveis


@pytest.mark.django_db
def test_vitrine_exige_sessao(cliente_api):
    assert cliente_api.get("/api/v1/vitrine").status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_vitrine_so_mostra_disponiveis_no_alcance_e_nunca_os_proprios(cliente_api, vendedor_sp, vitrine):
    visiveis, invisiveis = vitrine
    criar_produto(vendedor_sp, visiveis["ps5"].categoria, "Meu próprio produto", "100")
    cliente_api.force_authenticate(user=vendedor_sp)

    ids = percorrer(cliente_api, "/api/v1/vitrine?tamanho=2")

    assert set(ids) == {str(produto.pk) for produto in visiveis.values()}
    assert not {str(produto.pk) for produto in invisiveis} & set(ids)


@pytest.mark.django_db
def test_vitrine_filtra_ordena_e_devolve_o_vendedor(cliente_api, vendedor_sp, vitrine):
    visiveis, _ = vitrine
    cliente_api.force_authenticate(user=vendedor_sp)

    resposta = cliente_api.get("/api/v1/vitrine?categoria=games&ordenacao=preco_minimo")

    assert resposta.status_code == status.HTTP_200_OK
    assert [item["nome"] for item in resposta.data["results"]] == ["Nintendo Switch OLED", "PlayStation 5"]
    item = resposta.data["results"][0]
    assert item["categoria"] == "games"
    assert item["distancia_km"] == pytest.approx(5, abs=0.5)
    assert item["vendedor_publico"] == {
        "id": str(visiveis["switch"].vendedor_id),
        "nome": visiveis["switch"].vendedor.nome,
        "foto": None,
        "nota": None,
        "avaliacoes": 0,
    }

    resposta = cliente_api.get("/api/v1/vitrine?distancia_max_km=2")
    assert [item["nome"] for item in resposta.data["results"]] == ["PlayStation 5"]


@pytest.mark.django_db
def test_vitrine_vazia_sem_localizacao(cliente_api, vitrine):
    sem_local = criar_usuario()
    cliente_api.force_authenticate(user=sem_local)

    resposta = cliente_api.get("/api/v1/vitrine")

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["count"] == 0


@pytest.mark.django_db
def test_contagem_por_categoria_ignora_a_categoria_e_respeita_os_outros_filtros(
    cliente_api, vendedor_sp, vitrine, categoria, games
):
    perto = criar_usuario(0.01)
    criar_anuncio(perto, categoria, "Notebook gamer", preco_max=Decimal("4000"))
    criar_anuncio(perto, games, "Controle de PS5", preco_max=Decimal("400"))
    cliente_api.force_authenticate(user=vendedor_sp)

    anuncios = cliente_api.get("/api/v1/anuncios/categorias?categoria=games")
    produtos = cliente_api.get("/api/v1/vitrine/categorias?preco_max=2500")

    assert anuncios.status_code == status.HTTP_200_OK
    assert anuncios.data == [{"slug": "eletronicos", "total": 1}, {"slug": "games", "total": 1}]
    assert produtos.data == [{"slug": "eletronicos", "total": 1}, {"slug": "games", "total": 1}]


@pytest.mark.django_db
def test_estatisticas_sao_publicas(cliente_api, vitrine, categoria):
    comprador = criar_usuario(0.01)
    comprador.cidade, comprador.uf = "São Paulo", "SP"
    comprador.save(update_fields=["cidade", "uf"])
    criar_anuncio(comprador, categoria, "Notebook")
    criar_anuncio(comprador, categoria, "Pausado", status_anuncio=Anuncio.Status.PAUSADO)

    resposta = cliente_api.get("/api/v1/estatisticas")

    assert resposta.status_code == status.HTTP_200_OK
    # Os vendedores da vitrine não têm cidade; o comprador conta como uma cidade com atividade.
    assert resposta.data == {"anuncios_ativos": 1, "cidades": 1, "vendedores": 4}


@pytest.mark.django_db
def test_popular_banco_cria_o_ciclo_completo_e_nao_repete(settings):
    settings.DEBUG = True
    Usuario.objects.create_user(email="ja-existia@example.com", password="Senha-forte-123!", nome="Já existia")

    call_command("popular_banco")

    assert Usuario.objects.filter(email="ja-existia@example.com").exists()
    assert Usuario.objects.filter(email="voce@example.com", ponto__isnull=False).exists()
    assert Anuncio.objects.filter(status=Anuncio.Status.ATIVO).exists()
    assert Produto.objects.filter(status=Produto.Status.DISPONIVEL).exists()
    assert Usuario.objects.get(email="bruno@example.com").avaliacoes_recebidas.filter(publicada_em__isnull=False)
    with pytest.raises(CommandError, match="já foi populado"):
        call_command("popular_banco")


@pytest.mark.django_db
def test_popular_banco_recusa_sem_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("popular_banco")

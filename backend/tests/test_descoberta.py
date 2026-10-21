import base64
import itertools
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework import status

from quero.anuncios.models import Anuncio, Categoria
from quero.contas.models import Usuario
from quero.ofertas.models import BuscaSalva

LATITUDE = -23.5505
LONGITUDE = -46.6333
_sequencia = itertools.count()


def criar_usuario(deslocamento_longitude=None):
    numero = next(_sequencia)
    usuario = Usuario.objects.create_user(email=f"pessoa{numero}@example.com", password="Senha-forte-123!", nome=f"Pessoa {numero}")
    if deslocamento_longitude is not None:
        usuario.ponto = Point(LONGITUDE + deslocamento_longitude, LATITUDE, srid=4326)
        usuario.save(update_fields=["ponto"])
    return usuario


def criar_anuncio(comprador, categoria, titulo, *, descricao="Descrição", preco_min=None, preco_max=None, status_anuncio=Anuncio.Status.ATIVO, horas_atras=0, raio_m=20_000):
    anuncio = Anuncio.objects.create(
        comprador=comprador, categoria=categoria, titulo=titulo, descricao=descricao,
        preco_min=preco_min, preco_max=preco_max, raio_m=raio_m,
    )
    Anuncio.objects.filter(pk=anuncio.pk).update(status=status_anuncio, criado_em=timezone.now() - timedelta(hours=horas_atras))
    return anuncio


def titulos(resposta):
    return [item["titulo"] for item in resposta.data["results"]]


def percorrer(cliente_api, url):
    vistos = []
    while url:
        resposta = cliente_api.get(url)
        assert resposta.status_code == status.HTTP_200_OK, resposta.data
        vistos.extend(item["id"] for item in resposta.data["results"])
        url = resposta.data["next"]
    return vistos


@pytest.fixture
def moveis(db):
    return Categoria.objects.get_or_create(slug="moveis", defaults={"nome": "Móveis"})[0]


@pytest.fixture
def vendedor_sp(db):
    return criar_usuario(0)


@pytest.fixture
def cenario(categoria, moveis):
    """Anúncios a ~1, 3 e 5 km do vendedor, além de anúncios que nunca devem aparecer."""
    perto, medio, longe = criar_usuario(0.01), criar_usuario(0.03), criar_usuario(0.05)
    fora_do_raio = criar_usuario(1.0)
    visiveis = {
        "notebook": criar_anuncio(perto, categoria, "Notebook gamer", descricao="Placa de vídeo dedicada", preco_min=Decimal("2000"), preco_max=Decimal("4000"), horas_atras=5),
        "celular": criar_anuncio(medio, categoria, "Celular usado", descricao="Tela intacta e bateria boa", preco_max=Decimal("800"), horas_atras=1),
        "sofa": criar_anuncio(longe, moveis, "Sofá retrátil", descricao="Para sala pequena", preco_min=Decimal("500"), preco_max=Decimal("1500"), horas_atras=3),
        "mesa": criar_anuncio(perto, moveis, "Mesa de jantar", descricao="Madeira, seis lugares", horas_atras=2),
    }
    invisiveis = [
        criar_anuncio(perto, categoria, "Notebook pausado", status_anuncio=Anuncio.Status.PAUSADO),
        criar_anuncio(perto, categoria, "Notebook encerrado", status_anuncio=Anuncio.Status.ENCERRADO),
        criar_anuncio(perto, categoria, "Notebook em negociação", status_anuncio=Anuncio.Status.EM_NEGOCIACAO),
        criar_anuncio(fora_do_raio, categoria, "Notebook distante"),
        criar_anuncio(longe, categoria, "Notebook raio curto", raio_m=1_000),
    ]
    return visiveis, invisiveis


@pytest.mark.django_db
@pytest.mark.parametrize("ordenacao", [choice for choice, _ in BuscaSalva.Ordenacao.choices])
@pytest.mark.parametrize(
    "filtros",
    ["", "q=notebook", "categoria=eletronicos", "preco_min=0&preco_max=99999999", "distancia_max_km=200"],
)
def test_filtros_e_ordenacoes_nao_contornam_raio_nem_status(cliente_api, vendedor_sp, cenario, ordenacao, filtros):
    _, invisiveis = cenario
    cliente_api.force_authenticate(user=vendedor_sp)

    ids = percorrer(cliente_api, f"/api/v1/anuncios?ordenacao={ordenacao}&tamanho=2&{filtros}")

    assert not {str(anuncio.pk) for anuncio in invisiveis} & set(ids)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parametros", "esperados"),
    [
        ("", {"Notebook gamer", "Celular usado", "Sofá retrátil", "Mesa de jantar"}),
        ("q=notebook", {"Notebook gamer"}),
        ("q=MADEIRA", {"Mesa de jantar"}),
        ("q=tela bateria", {"Celular usado"}),
        ("q=tela madeira", set()),
        ("categoria=moveis", {"Sofá retrátil", "Mesa de jantar"}),
        ("preco_min=1000", {"Notebook gamer", "Sofá retrátil", "Mesa de jantar"}),
        ("preco_max=700", {"Celular usado", "Sofá retrátil", "Mesa de jantar"}),
        ("preco_min=900&preco_max=1800", {"Sofá retrátil", "Mesa de jantar"}),
        ("distancia_max_km=2", {"Notebook gamer", "Mesa de jantar"}),
        ("distancia_max_km=4&categoria=eletronicos", {"Notebook gamer", "Celular usado"}),
        ("categoria=moveis&preco_max=1000&distancia_max_km=10&q=sala", {"Sofá retrátil"}),
        ("categoria=moveis&q=notebook", set()),
    ],
)
def test_filtros_combinaveis_e_contagem(cliente_api, vendedor_sp, cenario, parametros, esperados):
    cliente_api.force_authenticate(user=vendedor_sp)

    resposta = cliente_api.get(f"/api/v1/anuncios?{parametros}")

    assert resposta.status_code == status.HTTP_200_OK
    assert set(titulos(resposta)) == esperados
    assert resposta.data["count"] == len(esperados)
    assert resposta.data["next"] is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ordenacao", "esperado"),
    [
        ("distancia", ["Mesa de jantar", "Notebook gamer", "Celular usado", "Sofá retrátil"]),
        ("recentes", ["Celular usado", "Mesa de jantar", "Sofá retrátil", "Notebook gamer"]),
        ("preco_minimo", ["Celular usado", "Sofá retrátil", "Notebook gamer", "Mesa de jantar"]),
        ("preco_maximo", ["Notebook gamer", "Sofá retrátil", "Celular usado", "Mesa de jantar"]),
    ],
)
def test_ordenacoes(cliente_api, vendedor_sp, cenario, ordenacao, esperado):
    cliente_api.force_authenticate(user=vendedor_sp)

    resposta = cliente_api.get(f"/api/v1/anuncios?ordenacao={ordenacao}")

    assert titulos(resposta) == esperado
    if ordenacao == "distancia":
        distancias = [item["distancia_km"] for item in resposta.data["results"]]
        assert distancias == sorted(distancias)
        assert 0.5 < distancias[0] < 1.5


@pytest.mark.django_db
@pytest.mark.parametrize("ordenacao", [choice for choice, _ in BuscaSalva.Ordenacao.choices])
@pytest.mark.parametrize("tamanho", [1, 3, 50])
def test_paginacao_nao_duplica_nem_perde_registros_com_empates(cliente_api, vendedor_sp, categoria, ordenacao, tamanho):
    # Mesmo comprador, mesmo instante e mesmo orçamento: só o desempate por id diferencia.
    compradores = [criar_usuario(0.01), criar_usuario(0.02)]
    for indice in range(9):
        criar_anuncio(compradores[indice % 2], categoria, f"Anúncio {indice}", preco_max=Decimal(100 * (indice % 3)) or None)
    Anuncio.objects.update(criado_em=timezone.now())
    cliente_api.force_authenticate(user=vendedor_sp)

    url = f"/api/v1/anuncios?ordenacao={ordenacao}&tamanho={tamanho}"
    ids = percorrer(cliente_api, url)
    completa = cliente_api.get(f"{url.split('&tamanho')[0]}&tamanho=50")

    assert len(ids) == len(set(ids)) == 9
    assert ids == [item["id"] for item in completa.data["results"]]
    assert completa.data["count"] == 9


@pytest.mark.django_db
def test_insercao_entre_paginas_nao_desloca_resultados(cliente_api, vendedor_sp, categoria):
    comprador = criar_usuario(0.01)
    originais = [criar_anuncio(comprador, categoria, f"Anúncio {indice}", horas_atras=indice) for indice in range(4)]
    cliente_api.force_authenticate(user=vendedor_sp)

    primeira = cliente_api.get("/api/v1/anuncios?ordenacao=recentes&tamanho=2")
    criar_anuncio(comprador, categoria, "Novo")
    restantes = percorrer(cliente_api, primeira.data["next"])

    vistos = [item["id"] for item in primeira.data["results"]] + restantes
    assert vistos == [str(anuncio.pk) for anuncio in originais]


@pytest.mark.django_db
def test_resultado_vazio_e_usuario_sem_localizacao(cliente_api, cenario):
    cliente_api.force_authenticate(user=criar_usuario())

    resposta = cliente_api.get("/api/v1/anuncios?q=notebook")

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data == {"count": 0, "next": None, "results": []}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parametros", "campo"),
    [
        ("preco_min=500&preco_max=100", "preco_max"),
        ("preco_min=-1", "preco_min"),
        ("distancia_max_km=0", "distancia_max_km"),
        ("distancia_max_km=201", "distancia_max_km"),
        ("ordenacao=aleatoria", "ordenacao"),
        ("categoria=inexistente", "categoria"),
        ("tamanho=51", "tamanho"),
        ("cursor=nao-e-um-cursor", "cursor"),
        ("ordenacao=recentes&cursor=" + base64.urlsafe_b64encode(json.dumps({"o": "distancia", "v": [1.0, "x", "y"]}).encode()).decode(), "cursor"),
        ("ordenacao=recentes&cursor=" + base64.urlsafe_b64encode(json.dumps({"o": "recentes", "v": ["ontem", "x"]}).encode()).decode(), "cursor"),
    ],
)
def test_parametros_invalidos(cliente_api, vendedor_sp, parametros, campo):
    cliente_api.force_authenticate(user=vendedor_sp)

    resposta = cliente_api.get(f"/api/v1/anuncios?{parametros}")

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST
    assert campo in resposta.data


@pytest.mark.django_db
def test_crud_de_buscas_salvas_e_execucao(cliente_api, vendedor_sp, cenario):
    cliente_api.force_authenticate(user=vendedor_sp)
    dados = {"nome": "Móveis baratos", "categoria": "moveis", "preco_max": "1000.00", "ordenacao": "recentes"}

    criada = cliente_api.post("/api/v1/buscas-salvas", dados, format="json")
    assert criada.status_code == status.HTTP_201_CREATED
    url = f"/api/v1/buscas-salvas/{criada.data['id']}"

    duplicada = cliente_api.post("/api/v1/buscas-salvas", dados, format="json")
    assert duplicada.status_code == status.HTTP_400_BAD_REQUEST
    assert "nome" in duplicada.data

    resultados = cliente_api.get(f"{url}/anuncios")
    assert titulos(resultados) == ["Mesa de jantar", "Sofá retrátil"]
    assert resultados.data["count"] == 2

    editada = cliente_api.patch(url, {"termo": "sala", "preco_min": "2000.00"}, format="json")
    assert editada.status_code == status.HTTP_400_BAD_REQUEST
    editada = cliente_api.patch(url, {"termo": "sala"}, format="json")
    assert editada.status_code == status.HTTP_200_OK
    assert titulos(cliente_api.get(f"{url}/anuncios")) == ["Sofá retrátil"]

    assert [item["nome"] for item in cliente_api.get("/api/v1/buscas-salvas").data["results"]] == ["Móveis baratos"]
    assert cliente_api.delete(url).status_code == status.HTTP_204_NO_CONTENT
    assert not BuscaSalva.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("metodo", "sufixo", "dados"),
    [("get", "", None), ("patch", "", {"nome": "Invadida"}), ("put", "", {"nome": "Invadida"}), ("delete", "", None), ("get", "/anuncios", None)],
)
def test_usuario_nao_acessa_buscas_salvas_de_terceiros(cliente_api, vendedor_sp, metodo, sufixo, dados):
    busca = BuscaSalva.objects.create(usuario=vendedor_sp, nome="Minha busca", termo="notebook")
    cliente_api.force_authenticate(user=criar_usuario(0))

    resposta = getattr(cliente_api, metodo)(f"/api/v1/buscas-salvas/{busca.pk}{sufixo}", dados, format="json")

    assert resposta.status_code == status.HTTP_404_NOT_FOUND
    assert cliente_api.get("/api/v1/buscas-salvas").data["results"] == []
    busca.refresh_from_db()
    assert busca.nome == "Minha busca"


@pytest.mark.django_db
def test_nomes_de_buscas_sao_unicos_por_usuario(cliente_api, vendedor_sp):
    BuscaSalva.objects.create(usuario=vendedor_sp, nome="Notebooks")
    cliente_api.force_authenticate(user=criar_usuario(0))

    resposta = cliente_api.post("/api/v1/buscas-salvas", {"nome": "Notebooks"}, format="json")

    assert resposta.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_listagem_propria_e_detalhe_respeitam_proprietario(cliente_api, vendedor_sp, cenario):
    visiveis, invisiveis = cenario
    pausado = invisiveis[0]
    cliente_api.force_authenticate(user=pausado.comprador)

    for url in ("/api/v1/anuncios?meus=true", "/api/v1/anuncios/meus"):
        assert str(pausado.pk) in [item["id"] for item in cliente_api.get(url).data["results"]]
    assert cliente_api.get(f"/api/v1/anuncios/{pausado.pk}?meus=true").status_code == status.HTTP_200_OK

    cliente_api.force_authenticate(user=vendedor_sp)
    assert cliente_api.get(f"/api/v1/anuncios/{pausado.pk}").status_code == status.HTTP_404_NOT_FOUND
    detalhe = cliente_api.get(f"/api/v1/anuncios/{visiveis['sofa'].pk}")
    assert detalhe.status_code == status.HTTP_200_OK
    assert 4 < detalhe.data["distancia_km"] < 6

import itertools

import pytest
from django.contrib.gis.geos import Point
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from quero.anuncios.models import Anuncio, Categoria
from quero.contas.models import Usuario

URL = "/api/v1/anuncios/publicos"
CAMPOS_PUBLICOS = {"id", "titulo", "categoria", "categoria_nome", "preco_min", "preco_max", "cidade", "uf", "criado_em"}
_sequencia = itertools.count()


def criar_comprador(cidade, uf, longitude, latitude):
    numero = next(_sequencia)
    usuario = Usuario.objects.create_user(
        email=f"publico{numero}@example.com",
        password="Senha-forte-123!",
        nome=f"Comprador Secreto {numero}",
        telefone="(11) 99999-0000",
    )
    usuario.ponto = Point(longitude, latitude, srid=4326)
    usuario.cidade = cidade
    usuario.uf = uf
    usuario.save(update_fields=["ponto", "cidade", "uf"])
    return usuario


def criar_anuncio(comprador, categoria, titulo, *, status_anuncio=Anuncio.Status.ATIVO, preco_max=None):
    anuncio = Anuncio.objects.create(
        comprador=comprador,
        categoria=categoria,
        titulo=titulo,
        descricao="Descrição completa que só quem entrou pode ler",
        preco_min=None,
        preco_max=preco_max,
        raio_m=5_000,
    )
    if status_anuncio != Anuncio.Status.ATIVO:
        Anuncio.objects.filter(pk=anuncio.pk).update(status=status_anuncio)
    return anuncio


@pytest.fixture
def paulista(db):
    return criar_comprador("São Paulo", "SP", -46.6333, -23.5505)


@pytest.fixture
def carioca(db):
    return criar_comprador("Rio de Janeiro", "RJ", -43.1729, -22.9068)


@pytest.fixture
def games(db):
    return Categoria.objects.get_or_create(slug="games", defaults={"nome": "Games"})[0]


@pytest.fixture
def anuncios(categoria, games, paulista, carioca):
    return {
        "notebook_sp": criar_anuncio(paulista, categoria, "Procuro notebook", preco_max=3000),
        "console_sp": criar_anuncio(paulista, games, "Procuro console", preco_max=2000),
        "celular_rj": criar_anuncio(carioca, categoria, "Procuro celular", preco_max=1500),
        "pausado": criar_anuncio(paulista, categoria, "Anúncio pausado", status_anuncio=Anuncio.Status.PAUSADO),
        "encerrado": criar_anuncio(carioca, categoria, "Anúncio encerrado", status_anuncio=Anuncio.Status.ENCERRADO),
        "negociando": criar_anuncio(
            carioca, categoria, "Anúncio em negociação", status_anuncio=Anuncio.Status.EM_NEGOCIACAO
        ),
    }


def titulos(resposta):
    return {item["titulo"] for item in resposta.data["results"]}


def test_anonimo_lista_anuncios(cliente_api, anuncios):
    resposta = cliente_api.get(URL)

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["count"] == 3


def test_payload_tem_so_os_campos_do_card(cliente_api, anuncios, paulista):
    resposta = cliente_api.get(URL)
    item = next(item for item in resposta.data["results"] if item["titulo"] == "Procuro notebook")

    assert set(item) == CAMPOS_PUBLICOS
    assert item["cidade"] == "São Paulo"
    assert item["uf"] == "SP"
    # Nada de localização exata, raio ou dados de quem comprou.
    for proibido in (
        "comprador",
        "comprador_publico",
        "ponto",
        "alcance",
        "latitude",
        "longitude",
        "raio_km",
        "raio_m",
        "distancia_km",
        "cep",
        "descricao",
        "ofertas_recebidas",
        "status",
    ):
        assert proibido not in item
    conteudo = resposta.content.decode()
    assert str(paulista.id) not in conteudo
    assert paulista.nome not in conteudo
    assert paulista.email not in conteudo
    assert paulista.telefone not in conteudo
    assert "-46.6333" not in conteudo and "-23.5505" not in conteudo
    assert "só quem entrou" not in conteudo


def test_detalhe_continua_exigindo_sessao(cliente_api, anuncios):
    anuncio = anuncios["notebook_sp"]

    assert cliente_api.get(f"/api/v1/anuncios/{anuncio.id}").status_code == status.HTTP_401_UNAUTHORIZED
    assert cliente_api.get("/api/v1/anuncios").status_code == status.HTTP_401_UNAUTHORIZED
    assert cliente_api.get(f"/api/v1/anuncios/{anuncio.id}/ofertas").status_code == status.HTTP_401_UNAUTHORIZED
    assert cliente_api.get(f"/api/v1/anuncios/{anuncio.id}/estimativa-preco").status_code == (
        status.HTTP_401_UNAUTHORIZED
    )
    assert cliente_api.get("/api/v1/vitrine").status_code == status.HTTP_401_UNAUTHORIZED


def test_permissao_padrao_continua_exigindo_sessao(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == ["rest_framework.permissions.IsAuthenticated"]


def test_pausados_encerrados_e_em_negociacao_ficam_de_fora(cliente_api, anuncios):
    resposta = cliente_api.get(URL)

    assert titulos(resposta) == {"Procuro notebook", "Procuro console", "Procuro celular"}


def test_sem_uf_a_listagem_e_nacional_e_ignora_o_raio(cliente_api, anuncios):
    # Os raios de 5 km não se cruzam entre SP e RJ, e mesmo assim os dois aparecem.
    resposta = cliente_api.get(URL)

    assert {item["uf"] for item in resposta.data["results"]} == {"SP", "RJ"}


def test_filtro_por_uf(cliente_api, anuncios):
    assert titulos(cliente_api.get(URL, {"uf": "SP"})) == {"Procuro notebook", "Procuro console"}
    assert titulos(cliente_api.get(URL, {"uf": "rj"})) == {"Procuro celular"}
    assert cliente_api.get(URL, {"uf": "AM"}).data["count"] == 0


def test_uf_invalida_e_recusada(cliente_api, anuncios):
    assert cliente_api.get(URL, {"uf": "XX"}).status_code == status.HTTP_400_BAD_REQUEST


def test_uf_combina_com_categoria_busca_preco_e_ordenacao(cliente_api, anuncios):
    assert titulos(cliente_api.get(URL, {"uf": "SP", "categoria": "games"})) == {"Procuro console"}
    assert titulos(cliente_api.get(URL, {"q": "notebook"})) == {"Procuro notebook"}
    # A busca pública não olha a descrição, que o visitante não vê.
    assert cliente_api.get(URL, {"q": "entrou"}).data["count"] == 0
    assert titulos(cliente_api.get(URL, {"preco_max": "1800"})) == {
        "Procuro notebook",
        "Procuro console",
        "Procuro celular",
    }
    assert titulos(cliente_api.get(URL, {"preco_min": "2500"})) == {"Procuro notebook"}
    ordem = [item["titulo"] for item in cliente_api.get(URL, {"ordenacao": "preco_minimo"}).data["results"]]
    assert ordem == ["Procuro celular", "Procuro console", "Procuro notebook"]


def test_ordenacao_por_distancia_nao_existe_para_visitante(cliente_api, anuncios):
    assert cliente_api.get(URL, {"ordenacao": "distancia"}).status_code == status.HTTP_400_BAD_REQUEST


def test_paginacao(cliente_api, anuncios):
    primeira = cliente_api.get(URL, {"tamanho": 2})
    segunda = cliente_api.get(primeira.data["next"])

    assert len(primeira.data["results"]) == 2
    assert len(segunda.data["results"]) == 1
    assert segunda.data["next"] is None


def test_contagem_por_categoria_publica(cliente_api, anuncios):
    resposta = cliente_api.get(f"{URL}/categorias", {"uf": "SP", "categoria": "games"})

    assert resposta.status_code == status.HTTP_200_OK
    assert {item["slug"]: item["total"] for item in resposta.data} == {"eletronicos": 1, "games": 1}


def test_token_invalido_nao_bloqueia_a_home(cliente_api, anuncios):
    cliente_api.credentials(HTTP_AUTHORIZATION="Bearer token-expirado")

    assert cliente_api.get(URL).status_code == status.HTTP_200_OK


def test_listagem_fica_em_cache(cliente_api, anuncios, paulista, categoria, settings):
    settings.FEED_PUBLICO_CACHE_SEGUNDOS = 60
    assert cliente_api.get(URL).data["count"] == 3

    criar_anuncio(paulista, categoria, "Procuro monitor")

    assert cliente_api.get(URL).data["count"] == 3
    assert cliente_api.get(URL, {"uf": "SP"}).data["count"] == 3


def test_throttling_ativo_para_anonimos(cliente_api, anuncios, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "feed_publico", "3/min")

    respostas = [cliente_api.get(URL).status_code for _ in range(4)]

    assert respostas == [200, 200, 200, status.HTTP_429_TOO_MANY_REQUESTS]


def test_uf_do_anuncio_segue_a_localizacao_do_comprador(anuncios, paulista):
    from quero.contas.services import atualizar_perfil

    atualizar_perfil(
        usuario=paulista,
        dados={
            "localizacao": {
                "cidade": "Curitiba",
                "uf": "PR",
                "_ponto": Point(-49.2733, -25.4284, srid=4326),
            }
        },
    )

    anuncios["notebook_sp"].refresh_from_db()
    anuncios["pausado"].refresh_from_db()
    assert (anuncios["notebook_sp"].cidade, anuncios["notebook_sp"].uf) == ("Curitiba", "PR")
    assert anuncios["pausado"].uf == "PR"


@pytest.mark.django_db
def test_popular_banco_preenche_a_uf(settings):
    from django.core.management import call_command

    settings.DEBUG = True
    call_command("popular_banco")

    assert Anuncio.objects.exists()
    assert not Anuncio.objects.filter(uf="").exists()

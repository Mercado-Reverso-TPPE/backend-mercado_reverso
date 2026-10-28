import pytest
from django.contrib.gis.geos import Point
from django.core.cache import cache
from rest_framework.test import APIClient

from quero.anuncios.models import Anuncio, Categoria
from quero.contas.models import Usuario


@pytest.fixture
def cliente_api():
    return APIClient()


@pytest.fixture(autouse=True)
def limpar_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def categoria(db):
    categoria, _ = Categoria.objects.get_or_create(
        slug="eletronicos",
        defaults={"nome": "Eletrônicos"},
    )
    return categoria


@pytest.fixture
def usuario(db):
    return Usuario.objects.create_user(
        email="pessoa@example.com",
        password="Senha-forte-123!",
        nome="Pessoa de Teste",
    )


@pytest.fixture
def usuario_com_localizacao(usuario):
    usuario.ponto = Point(-46.6333, -23.5505, srid=4326)
    usuario.cidade = "São Paulo"
    usuario.uf = "SP"
    usuario.save(update_fields=["ponto", "cidade", "uf"])
    return usuario


@pytest.fixture
def vendedor(db):
    return Usuario.objects.create_user(
        email="vendedor@example.com",
        password="Senha-forte-123!",
        nome="Vendedor de Teste",
    )


@pytest.fixture
def anuncio(categoria, usuario_com_localizacao):
    return Anuncio.objects.create(
        comprador=usuario_com_localizacao,
        titulo="Procuro notebook",
        categoria=categoria,
        descricao="Notebook para estudo",
        raio_m=20_000,
    )

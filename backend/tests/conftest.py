import pytest
from django.contrib.gis.geos import Point
from rest_framework.test import APIClient

from quero.anuncios.models import Anuncio, Categoria
from quero.contas.models import Localizacao, Usuario


@pytest.fixture
def cliente_api():
    return APIClient()


@pytest.fixture
def categoria(db):
    return Categoria.objects.create(nome="Eletrônicos", slug="eletronicos")


@pytest.fixture
def usuario(db):
    return Usuario.objects.create_user(
        email="pessoa@example.com",
        password="Senha-forte-123!",
        nome="Pessoa de Teste",
    )


@pytest.fixture
def usuario_com_localizacao(usuario):
    Localizacao.objects.create(
        usuario=usuario,
        ponto=Point(-46.6333, -23.5505, srid=4326),
        cidade="São Paulo",
        uf="SP",
    )
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
        ponto=usuario_com_localizacao.localizacao.ponto,
        cidade="São Paulo",
        uf="SP",
    )

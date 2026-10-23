import pytest
from django.core.cache import cache
from django.contrib.gis.geos import Point
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


@pytest.fixture
def vendedor_no_raio(vendedor, anuncio):
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])
    return vendedor


@pytest.fixture
def terceiro(db):
    return Usuario.objects.create_user(
        email="terceiro@example.com",
        password="Senha-forte-123!",
        nome="Terceiro de Teste",
    )


@pytest.fixture
def oferta(anuncio, vendedor_no_raio):
    from quero.ofertas.models import Oferta
    from quero.ofertas.services import enviar_oferta

    return enviar_oferta(
        vendedor=vendedor_no_raio,
        anuncio_id=anuncio.pk,
        dados={"descricao": "Notebook revisado", "estado_conservacao": Oferta.EstadoConservacao.SEMINOVO, "preco": "1500.00"},
    )


@pytest.fixture
def produto(categoria, vendedor):
    from quero.catalogo.models import Produto

    return Produto.objects.create(
        vendedor=vendedor,
        categoria=categoria,
        nome="Notebook",
        descricao="Notebook revisado",
        estado_conservacao=Produto.EstadoConservacao.SEMINOVO,
        preco="1500.00",
    )


@pytest.fixture
def negociacao(oferta, produto):
    """Estado produzido pelo aceite de uma oferta (QRO-13): anúncio em negociação e produto reservado."""
    from quero.negociacao.models import Negociacao
    from quero.ofertas.models import Oferta

    oferta.status = Oferta.Status.ACEITA
    oferta.produto = produto
    oferta.save(update_fields=["status", "produto"])
    oferta.anuncio.status = Anuncio.Status.EM_NEGOCIACAO
    oferta.anuncio.save(update_fields=["status"])
    return Negociacao.objects.create(oferta=oferta, valor_final="1400.00")

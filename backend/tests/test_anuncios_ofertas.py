import pytest
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from rest_framework import status

from quero.anuncios.models import Anuncio
from quero.anuncios.services import alterar_status_anuncio, criar_anuncio
from quero.contas.models import Localizacao, Usuario
from quero.ofertas.models import HistoricoOferta, Oferta
from quero.ofertas.services import editar_oferta, enviar_oferta, retirar_oferta


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("estado_inicial", "novo_estado", "esperado"),
    [
        (Anuncio.Status.ATIVO, Anuncio.Status.PAUSADO, True),
        (Anuncio.Status.ATIVO, Anuncio.Status.ENCERRADO, True),
        (Anuncio.Status.PAUSADO, Anuncio.Status.ATIVO, True),
        (Anuncio.Status.PAUSADO, Anuncio.Status.ENCERRADO, True),
        (Anuncio.Status.ENCERRADO, Anuncio.Status.ATIVO, False),
        (Anuncio.Status.EM_NEGOCIACAO, Anuncio.Status.ENCERRADO, False),
    ],
)
def test_transicoes_de_status_do_anuncio(anuncio, estado_inicial, novo_estado, esperado):
    anuncio.status = estado_inicial
    anuncio.save(update_fields=["status"])

    if esperado:
        atualizado = alterar_status_anuncio(anuncio=anuncio, novo_status=novo_estado)
        assert atualizado.status == novo_estado
    else:
        with pytest.raises(ValidationError):
            alterar_status_anuncio(anuncio=anuncio, novo_status=novo_estado)


@pytest.mark.django_db
@pytest.mark.parametrize("tem_localizacao", [True, False])
def test_criacao_de_anuncio_exige_localizacao(categoria, usuario, tem_localizacao):
    if tem_localizacao:
        Localizacao.objects.create(
            usuario=usuario,
            ponto=Point(-46.63, -23.55, srid=4326),
            cidade="São Paulo",
            uf="SP",
        )

    dados = {"titulo": "Procuro bicicleta", "categoria": categoria, "descricao": "Em bom estado"}
    if tem_localizacao:
        anuncio = criar_anuncio(comprador=usuario, dados=dados)
        assert anuncio.raio_m == 20_000
        assert anuncio.ponto == usuario.localizacao.ponto
        assert anuncio.cidade == "São Paulo"
    else:
        with pytest.raises(ValidationError, match="localização"):
            criar_anuncio(comprador=usuario, dados=dados)


@pytest.mark.django_db
def test_listagem_de_categorias_expõe_apenas_categorias_ativas(cliente_api, categoria):
    from quero.anuncios.models import Categoria

    Categoria.objects.create(nome="Oculta", slug="oculta", ativa=False)

    resposta = cliente_api.get("/api/v1/categorias")

    assert resposta.status_code == status.HTTP_200_OK
    assert [item["slug"] for item in resposta.data] == [categoria.slug]


@pytest.mark.django_db
@pytest.mark.parametrize("estado_anuncio", [Anuncio.Status.PAUSADO, Anuncio.Status.ENCERRADO, Anuncio.Status.EM_NEGOCIACAO])
def test_nao_e_possivel_ofertar_em_anuncio_inativo(anuncio, vendedor, estado_anuncio):
    anuncio.status = estado_anuncio
    anuncio.save(update_fields=["status"])
    Localizacao.objects.create(usuario=vendedor, ponto=anuncio.ponto)

    with pytest.raises(ValidationError, match="anúncios ativos"):
        enviar_oferta(
            vendedor=vendedor,
            anuncio_id=anuncio.pk,
            dados={"descricao": "Minha oferta", "estado_conservacao": Oferta.EstadoConservacao.USADO, "preco": "100.00"},
        )


@pytest.mark.django_db
@pytest.mark.parametrize("longitude", [-46.6333, -48.0])
def test_oferta_so_pode_ser_enviada_por_vendedor_dentro_do_raio(anuncio, vendedor, longitude):
    Localizacao.objects.create(usuario=vendedor, ponto=Point(longitude, -23.5505, srid=4326))
    dados = {"descricao": "Notebook em ótimo estado", "estado_conservacao": Oferta.EstadoConservacao.SEMINOVO, "preco": "1200.00"}

    if longitude == -46.6333:
        oferta = enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)
        assert oferta.status == Oferta.Status.ENVIADA
        assert oferta.historico.count() == 1
    else:
        with pytest.raises(ValidationError, match="fora do raio"):
            enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)


@pytest.mark.django_db
def test_oferta_unica_por_vendedor_edicao_e_retirada_registram_historico(anuncio, vendedor):
    Localizacao.objects.create(usuario=vendedor, ponto=anuncio.ponto)
    dados = {"descricao": "Notebook em ótimo estado", "estado_conservacao": Oferta.EstadoConservacao.SEMINOVO, "preco": "1200.00"}
    oferta = enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)

    with pytest.raises(ValidationError, match="oferta ativa"):
        enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)

    oferta = editar_oferta(oferta=oferta, vendedor=vendedor, dados={"preco": "1100.00"})
    assert oferta.historico.count() == 2
    retirar_oferta(oferta=oferta, vendedor=vendedor)
    assert oferta.historico.count() == 3
    assert oferta.status == Oferta.Status.RETIRADA
    assert HistoricoOferta.objects.filter(oferta=oferta).count() == 3


@pytest.mark.django_db
def test_comprador_ve_ofertas_do_anuncio_e_vendedor_ve_apenas_as_proprias(
    cliente_api, anuncio, vendedor
):
    outro_vendedor = Usuario.objects.create_user(
        email="outro@example.com", password="Senha-forte-123!", nome="Outro Vendedor"
    )
    Localizacao.objects.create(usuario=vendedor, ponto=anuncio.ponto)
    Localizacao.objects.create(usuario=outro_vendedor, ponto=anuncio.ponto)
    dados = {"descricao": "Oferta", "estado_conservacao": Oferta.EstadoConservacao.NOVO, "preco": "100.00"}
    oferta_propria = enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)
    enviar_oferta(vendedor=outro_vendedor, anuncio_id=anuncio.pk, dados=dados)

    cliente_api.force_authenticate(user=anuncio.comprador)
    resposta_comprador = cliente_api.get(f"/api/v1/anuncios/{anuncio.pk}/ofertas")
    assert resposta_comprador.status_code == status.HTTP_200_OK
    assert resposta_comprador.data["count"] == 2

    cliente_api.force_authenticate(user=vendedor)
    resposta_vendedor = cliente_api.get(f"/api/v1/anuncios/{anuncio.pk}/ofertas")
    assert resposta_vendedor.status_code == status.HTTP_200_OK
    assert resposta_vendedor.data["count"] == 1
    assert resposta_vendedor.data["results"][0]["id"] == str(oferta_propria.pk)

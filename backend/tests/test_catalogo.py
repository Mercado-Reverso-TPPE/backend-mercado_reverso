import io
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status

from quero.catalogo.models import FotoProduto, Produto
from quero.catalogo.services import adicionar_fotos, alterar_status_produto, atualizar_produto, excluir_produto
from quero.contas.models import Usuario
from quero.negociacao.models import Negociacao
from quero.ofertas.models import Oferta
from quero.ofertas.services import enviar_oferta


def imagem(nome="foto.png", formato="PNG"):
    conteudo = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(conteudo, format=formato)
    return SimpleUploadedFile(nome, conteudo.getvalue(), content_type=f"image/{formato.lower()}")


def arquivos_salvos(media_root):
    return [caminho for caminho in media_root.rglob("*") if caminho.is_file()]


@pytest.fixture(autouse=True)
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.PRODUTO_FOTOS_MAXIMO = 3
    settings.PRODUTO_FOTO_TAMANHO_MAXIMO_MB = 1
    return tmp_path


@pytest.fixture
def vendedor_no_raio(vendedor, anuncio):
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])
    return vendedor


@pytest.fixture
def produto(vendedor, categoria):
    return Produto.objects.create(
        vendedor=vendedor,
        categoria=categoria,
        nome="Notebook Dell",
        descricao="Notebook com 16 GB de RAM",
        estado_conservacao=Produto.EstadoConservacao.SEMINOVO,
        preco="2500.00",
    )


@pytest.fixture
def outro_vendedor(db):
    return Usuario.objects.create_user(email="outro@example.com", password="Senha-forte-123!", nome="Outro Vendedor")


@pytest.mark.django_db
def test_vendedor_gerencia_o_proprio_catalogo(cliente_api, vendedor, categoria):
    cliente_api.force_authenticate(user=vendedor)
    dados = {
        "nome": "Bicicleta",
        "descricao": "Aro 29",
        "categoria": categoria.slug,
        "estado_conservacao": "usado_bom",
        "preco": "900.00",
    }

    criado = cliente_api.post("/api/v1/produtos", dados, format="json")
    assert criado.status_code == status.HTTP_201_CREATED
    assert criado.data["status"] == Produto.Status.DISPONIVEL
    url = f"/api/v1/produtos/{criado.data['id']}"

    assert [item["id"] for item in cliente_api.get("/api/v1/produtos").data["results"]] == [criado.data["id"]]
    editado = cliente_api.patch(url, {"preco": "850.00", "status": "vendido"}, format="json")
    assert editado.status_code == status.HTTP_200_OK
    assert editado.data["preco"] == "850.00"
    assert editado.data["status"] == Produto.Status.DISPONIVEL

    assert cliente_api.delete(url).status_code == status.HTTP_204_NO_CONTENT
    assert not Produto.objects.filter(pk=criado.data["id"]).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("metodo", "sufixo", "dados"),
    [
        ("get", "", None),
        ("patch", "", {"nome": "Invadido"}),
        ("delete", "", None),
        ("patch", "/status", {"status": "vendido"}),
        ("post", "/fotos", None),
    ],
)
def test_vendedor_nao_acessa_produto_de_outro(cliente_api, produto, outro_vendedor, metodo, sufixo, dados):
    cliente_api.force_authenticate(user=outro_vendedor)
    if sufixo == "/fotos":
        dados = {"fotos": [imagem()]}
    formato = "multipart" if sufixo == "/fotos" else "json"

    resposta = getattr(cliente_api, metodo)(f"/api/v1/produtos/{produto.pk}{sufixo}", dados, format=formato)

    assert resposta.status_code == status.HTTP_404_NOT_FOUND
    assert cliente_api.get("/api/v1/produtos").data["results"] == []
    produto.refresh_from_db()
    assert produto.nome == "Notebook Dell"
    assert produto.status == Produto.Status.DISPONIVEL
    assert not produto.fotos.exists()


@pytest.mark.django_db
def test_upload_e_remocao_de_fotos(cliente_api, produto, media_temporaria, django_capture_on_commit_callbacks):
    cliente_api.force_authenticate(user=produto.vendedor)
    url = f"/api/v1/produtos/{produto.pk}/fotos"

    resposta = cliente_api.post(url, {"fotos": [imagem("a.png"), imagem("b.jpg", "JPEG")]}, format="multipart")

    assert resposta.status_code == status.HTTP_201_CREATED
    assert [foto["ordem"] for foto in resposta.data] == [1, 2]
    assert len(arquivos_salvos(media_temporaria)) == 2

    with django_capture_on_commit_callbacks(execute=True):
        removida = cliente_api.delete(f"{url}/{resposta.data[0]['id']}")
    assert removida.status_code == status.HTTP_204_NO_CONTENT
    assert list(produto.fotos.values_list("ordem", flat=True)) == [2]
    assert len(arquivos_salvos(media_temporaria)) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("arquivos", "mensagem"),
    [
        (lambda: [imagem(f"{i}.png") for i in range(4)], "no máximo 3 fotos"),
        (
            lambda: [imagem(), SimpleUploadedFile("grande.png", b"0" * (1024 * 1024 + 1), content_type="image/png")],
            "excede o limite",
        ),
        (
            lambda: [imagem(), SimpleUploadedFile("texto.png", b"nao sou imagem", content_type="image/png")],
            "não é uma imagem válida",
        ),
        (lambda: [imagem(), imagem("animada.gif", "GIF")], "formatos"),
    ],
)
def test_upload_rejeita_arquivos_fora_dos_limites(cliente_api, produto, media_temporaria, arquivos, mensagem):
    cliente_api.force_authenticate(user=produto.vendedor)

    resposta = cliente_api.post(f"/api/v1/produtos/{produto.pk}/fotos", {"fotos": arquivos()}, format="multipart")

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST
    assert any(mensagem in erro for erro in resposta.data["fotos"])
    assert not produto.fotos.exists()
    assert arquivos_salvos(media_temporaria) == []


@pytest.mark.django_db
def test_falha_ao_gravar_fotos_nao_deixa_registros_nem_arquivos(produto, media_temporaria):
    salvar_original = FotoProduto.save
    chamadas = []

    def salvar_com_falha(foto, *args, **kwargs):
        chamadas.append(foto)
        if len(chamadas) == 2:
            raise RuntimeError("falha de banco")
        return salvar_original(foto, *args, **kwargs)

    with patch.object(FotoProduto, "save", salvar_com_falha), pytest.raises(RuntimeError):
        adicionar_fotos(produto=produto, arquivos=[imagem("a.png"), imagem("b.png")])

    assert not produto.fotos.exists()
    assert arquivos_salvos(media_temporaria) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("inicial", "novo", "permitido"),
    [
        (Produto.Status.DISPONIVEL, Produto.Status.RESERVADO, True),
        (Produto.Status.DISPONIVEL, Produto.Status.VENDIDO, True),
        (Produto.Status.RESERVADO, Produto.Status.DISPONIVEL, True),
        (Produto.Status.RESERVADO, Produto.Status.VENDIDO, True),
        (Produto.Status.VENDIDO, Produto.Status.DISPONIVEL, False),
        (Produto.Status.VENDIDO, Produto.Status.RESERVADO, False),
        (Produto.Status.DISPONIVEL, Produto.Status.DISPONIVEL, False),
    ],
)
def test_transicoes_de_status_do_produto(produto, inicial, novo, permitido):
    Produto.objects.filter(pk=produto.pk).update(status=inicial)

    if permitido:
        assert alterar_status_produto(produto=produto, novo_status=novo).status == novo
    else:
        with pytest.raises(ValidationError, match="Transição"):
            alterar_status_produto(produto=produto, novo_status=novo)


@pytest.mark.django_db
def test_produto_vendido_nao_e_editavel_e_reservado_nao_e_excluido(produto):
    Produto.objects.filter(pk=produto.pk).update(status=Produto.Status.RESERVADO)
    with pytest.raises(ValidationError, match="reservados"):
        excluir_produto(produto=produto)

    Produto.objects.filter(pk=produto.pk).update(status=Produto.Status.VENDIDO)
    with pytest.raises(ValidationError, match="vendidos"):
        atualizar_produto(produto=produto, dados={"nome": "Outro"})
    with pytest.raises(ValidationError, match="vendidos"):
        adicionar_fotos(produto=produto, arquivos=[imagem()])


@pytest.mark.django_db
@pytest.mark.parametrize("status_produto", [Produto.Status.RESERVADO, Produto.Status.VENDIDO])
def test_produto_indisponivel_nao_pode_ser_ofertado(anuncio, vendedor_no_raio, produto, status_produto):
    Produto.objects.filter(pk=produto.pk).update(status=status_produto)

    with pytest.raises(ValidationError, match="produtos disponíveis"):
        enviar_oferta(vendedor=vendedor_no_raio, anuncio_id=anuncio.pk, dados={"produto_id": produto.pk})
    assert not Oferta.objects.exists()


@pytest.mark.django_db
def test_vendedor_nao_oferta_produto_de_outro(anuncio, produto, outro_vendedor):
    outro_vendedor.ponto = anuncio.comprador.ponto
    outro_vendedor.save(update_fields=["ponto"])

    with pytest.raises(ValidationError, match="seu catálogo"):
        enviar_oferta(vendedor=outro_vendedor, anuncio_id=anuncio.pk, dados={"produto_id": produto.pk})


@pytest.mark.django_db
def test_oferta_exige_dados_quando_nao_usa_produto(anuncio, vendedor_no_raio):
    with pytest.raises(ValidationError, match="escolha um produto"):
        enviar_oferta(vendedor=vendedor_no_raio, anuncio_id=anuncio.pk, dados={"descricao": "Sem preço"})


@pytest.mark.django_db
def test_alteracoes_no_catalogo_nao_alteram_snapshot_da_oferta(
    cliente_api, anuncio, vendedor_no_raio, produto, media_temporaria, django_capture_on_commit_callbacks
):
    adicionar_fotos(produto=produto, arquivos=[imagem("capa.png")])
    cliente_api.force_authenticate(user=vendedor_no_raio)

    resposta = cliente_api.post(
        f"/api/v1/anuncios/{anuncio.pk}/ofertas",
        {"produto_id": str(produto.pk), "preco": "2300.00"},
        format="json",
    )

    assert resposta.status_code == status.HTTP_201_CREATED
    assert resposta.data["produto_id"] == str(produto.pk)
    assert resposta.data["produto_nome"] == "Notebook Dell"
    assert resposta.data["descricao"] == "Notebook com 16 GB de RAM"
    assert resposta.data["estado_conservacao"] == Produto.EstadoConservacao.SEMINOVO
    assert resposta.data["preco"] == "2300.00"
    oferta = Oferta.objects.get(pk=resposta.data["id"])
    assert oferta.foto_produto_snapshot.startswith("ofertas/snapshots/")
    assert resposta.data["produto_foto"].endswith(oferta.foto_produto_snapshot)

    atualizar_produto(produto=produto, dados={"nome": "Outro nome", "descricao": "Outra descrição", "preco": "10.00"})
    with django_capture_on_commit_callbacks(execute=True):
        excluir_produto(produto=produto)

    oferta.refresh_from_db()
    assert oferta.produto is None
    assert oferta.nome_produto_snapshot == "Notebook Dell"
    assert oferta.descricao == "Notebook com 16 GB de RAM"
    assert str(oferta.preco) == "2300.00"
    assert default_storage.exists(oferta.foto_produto_snapshot)
    assert not FotoProduto.objects.exists()


@pytest.mark.django_db
def test_produto_acompanha_o_ciclo_da_negociacao(cliente_api, anuncio, vendedor_no_raio, produto):
    oferta = enviar_oferta(vendedor=vendedor_no_raio, anuncio_id=anuncio.pk, dados={"produto_id": produto.pk})

    negociacao = Negociacao.objects.create(oferta=oferta, valor_final=oferta.preco)
    produto.refresh_from_db()
    assert produto.status == Produto.Status.RESERVADO

    cliente_api.force_authenticate(user=vendedor_no_raio)
    resposta = cliente_api.patch(f"/api/v1/produtos/{produto.pk}/status", {"status": "disponivel"}, format="json")
    assert resposta.status_code == status.HTTP_400_BAD_REQUEST

    negociacao.status = Negociacao.Status.CONCLUIDA
    negociacao.save(update_fields=["status"])
    produto.refresh_from_db()
    assert produto.status == Produto.Status.VENDIDO


@pytest.mark.django_db
def test_negociacao_cancelada_libera_o_produto_e_reserva_e_exclusiva(anuncio, vendedor_no_raio, produto, categoria):
    oferta = enviar_oferta(vendedor=vendedor_no_raio, anuncio_id=anuncio.pk, dados={"produto_id": produto.pk})
    negociacao = Negociacao.objects.create(oferta=oferta, valor_final=oferta.preco)

    outro_anuncio = anuncio.__class__.objects.create(
        comprador=anuncio.comprador, titulo="Outro", categoria=categoria, descricao="Outro", raio_m=20_000
    )
    outra_oferta = Oferta.objects.create(
        anuncio=outro_anuncio,
        vendedor=vendedor_no_raio,
        produto=produto,
        descricao="x",
        estado_conservacao=produto.estado_conservacao,
        preco="10.00",
    )
    with pytest.raises(ValidationError, match="não está mais disponível"):
        Negociacao.objects.create(oferta=outra_oferta, valor_final="10.00")

    negociacao.status = Negociacao.Status.CANCELADA
    negociacao.save(update_fields=["status"])
    produto.refresh_from_db()
    assert produto.status == Produto.Status.DISPONIVEL

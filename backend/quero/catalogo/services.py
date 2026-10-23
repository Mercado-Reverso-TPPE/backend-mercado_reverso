import posixpath
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max
from PIL import Image

from .models import FotoProduto, Produto

TRANSICOES_STATUS = {
    Produto.Status.DISPONIVEL: {Produto.Status.RESERVADO, Produto.Status.VENDIDO},
    Produto.Status.RESERVADO: {Produto.Status.DISPONIVEL, Produto.Status.VENDIDO},
    Produto.Status.VENDIDO: set(),
}


def _bloquear_produto(produto):
    return Produto.objects.select_for_update().get(pk=produto.pk)


@transaction.atomic
def criar_produto(*, vendedor, dados):
    return Produto.objects.create(vendedor=vendedor, **dados)


@transaction.atomic
def atualizar_produto(*, produto, dados):
    produto = _bloquear_produto(produto)
    if produto.status == Produto.Status.VENDIDO:
        raise ValidationError("Produtos vendidos não podem ser alterados.")
    for campo, valor in dados.items():
        setattr(produto, campo, valor)
    produto.save(update_fields=[*dados.keys(), "atualizado_em"])
    return produto


@transaction.atomic
def excluir_produto(*, produto):
    produto = _bloquear_produto(produto)
    if produto.status == Produto.Status.RESERVADO:
        raise ValidationError("Produtos reservados em uma negociação não podem ser excluídos.")
    arquivos = [foto.arquivo.name for foto in produto.fotos.all()]
    produto.delete()
    # Ofertas guardam cópias próprias das fotos, então os originais podem ser apagados.
    transaction.on_commit(lambda: _apagar_arquivos(arquivos))


@transaction.atomic
def alterar_status_produto(*, produto, novo_status):
    produto = _bloquear_produto(produto)
    if novo_status not in TRANSICOES_STATUS[produto.status]:
        raise ValidationError("Transição de status do produto inválida.")
    produto.status = novo_status
    produto.save(update_fields=["status", "atualizado_em"])
    return produto


@transaction.atomic
def alterar_status_produto_pelo_vendedor(*, produto, novo_status):
    from quero.negociacao.models import Negociacao

    produto = _bloquear_produto(produto)
    em_negociacao = Negociacao.objects.filter(
        oferta__produto=produto,
        status=Negociacao.Status.EM_ANDAMENTO,
    ).exists()
    if em_negociacao:
        raise ValidationError("O status de um produto em negociação acompanha a negociação.")
    return alterar_status_produto(produto=produto, novo_status=novo_status)


def validar_foto(arquivo):
    limite_mb = settings.PRODUTO_FOTO_TAMANHO_MAXIMO_MB
    if arquivo.size > limite_mb * 1024 * 1024:
        raise ValidationError(f"O arquivo {arquivo.name} excede o limite de {limite_mb} MB.")
    try:
        with Image.open(arquivo) as imagem:
            formato = imagem.format
            imagem.verify()
    except Exception as exc:
        raise ValidationError(f"O arquivo {arquivo.name} não é uma imagem válida.") from exc
    finally:
        arquivo.seek(0)
    if formato not in settings.PRODUTO_FOTO_FORMATOS:
        formatos = ", ".join(settings.PRODUTO_FOTO_FORMATOS)
        raise ValidationError(f"O arquivo {arquivo.name} deve estar em um dos formatos: {formatos}.")


@transaction.atomic
def adicionar_fotos(*, produto, arquivos):
    produto = _bloquear_produto(produto)
    if produto.status == Produto.Status.VENDIDO:
        raise ValidationError("Produtos vendidos não podem ser alterados.")
    if not arquivos:
        raise ValidationError("Envie ao menos uma foto.")
    limite = settings.PRODUTO_FOTOS_MAXIMO
    if produto.fotos.count() + len(arquivos) > limite:
        raise ValidationError(f"Cada produto pode ter no máximo {limite} fotos.")
    erros = []
    for arquivo in arquivos:
        try:
            validar_foto(arquivo)
        except ValidationError as exc:
            erros.extend(exc.messages)
    if erros:
        raise ValidationError(erros)

    ordem = (produto.fotos.aggregate(maior=Max("ordem"))["maior"] or 0) + 1
    salvas = []
    try:
        for deslocamento, arquivo in enumerate(arquivos):
            foto = FotoProduto(produto=produto, arquivo=arquivo, ordem=ordem + deslocamento)
            salvas.append(foto)
            foto.save()
        produto.save(update_fields=["atualizado_em"])
    except Exception:
        # A transação desfaz os registros; os arquivos já gravados precisam ser removidos à parte.
        _apagar_arquivos([foto.arquivo.name for foto in salvas if foto.arquivo._committed])
        raise
    return salvas


@transaction.atomic
def remover_foto(*, foto):
    produto = _bloquear_produto(foto.produto)
    if produto.status == Produto.Status.VENDIDO:
        raise ValidationError("Produtos vendidos não podem ser alterados.")
    nome = foto.arquivo.name
    foto.delete()
    produto.save(update_fields=["atualizado_em"])
    transaction.on_commit(lambda: _apagar_arquivos([nome]))


def copiar_foto_para_snapshot(produto):
    """Copia a foto de capa para um caminho próprio da oferta, imune a alterações no catálogo."""
    capa = produto.fotos.first()
    if capa is None:
        return ""
    extensao = posixpath.splitext(capa.arquivo.name)[1]
    with capa.arquivo.open("rb") as origem:
        return default_storage.save(f"ofertas/snapshots/{uuid.uuid4()}{extensao}", origem)


def _apagar_arquivos(nomes):
    for nome in nomes:
        if nome:
            default_storage.delete(nome)

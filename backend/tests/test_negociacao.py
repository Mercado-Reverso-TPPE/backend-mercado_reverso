from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.negociacao.models import Negociacao
from quero.notificacoes.catalogo import TipoNotificacao
from quero.notificacoes.models import Notificacao
from quero.reputacao.models import Avaliacao


def acao(cliente_api, usuario, negociacao, sufixo=""):
    cliente_api.force_authenticate(user=usuario)
    return cliente_api.post(f"/api/v1/negociacoes/{negociacao.pk}/conclusao{sufixo}")


def solicitar(cliente_api, negociacao):
    return acao(cliente_api, negociacao.oferta.vendedor, negociacao)


def confirmar(cliente_api, negociacao):
    return acao(cliente_api, negociacao.oferta.anuncio.comprador, negociacao, "/confirmacao")


def recusar(cliente_api, negociacao):
    return acao(cliente_api, negociacao.oferta.anuncio.comprador, negociacao, "/recusa")


def vencer_prazo(negociacao, settings):
    negociacao.conclusao_solicitada_em = timezone.now() - timedelta(
        hours=settings.NEGOCIACAO_PRAZO_CONFIRMACAO_HORAS, minutes=1
    )
    negociacao.save(update_fields=["conclusao_solicitada_em"])


def assert_estados(negociacao, *, negociacao_status, anuncio_status, produto_status):
    negociacao.refresh_from_db()
    assert negociacao.status == negociacao_status
    assert Anuncio.objects.get(pk=negociacao.oferta.anuncio_id).status == anuncio_status
    assert Produto.objects.get(pk=negociacao.oferta.produto_id).status == produto_status


@pytest.mark.django_db
def test_conclusao_bilateral_encerra_anuncio_e_vende_produto(
    cliente_api, negociacao, django_capture_on_commit_callbacks
):
    resposta = solicitar(cliente_api, negociacao)
    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["conclusao_solicitada_em"] is not None
    assert resposta.data["prazo_confirmacao_em"] is not None

    with django_capture_on_commit_callbacks(execute=True):
        resposta = confirmar(cliente_api, negociacao)

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["status"] == Negociacao.Status.CONCLUIDA
    assert resposta.data["conclusao_automatica"] is False
    assert resposta.data["avaliacao"] == {"disponivel": True, "enviada": False}
    assert_estados(
        negociacao,
        negociacao_status=Negociacao.Status.CONCLUIDA,
        anuncio_status=Anuncio.Status.ENCERRADO,
        produto_status=Produto.Status.VENDIDO,
    )
    assert negociacao.confirmada_em is not None and negociacao.concluida_em is not None
    convites = Notificacao.objects.filter(negociacao=negociacao, tipo=TipoNotificacao.NEGOCIACAO_CONCLUIDA)
    assert set(convites.values_list("usuario_id", flat=True)) == {
        negociacao.oferta.vendedor_id,
        negociacao.oferta.anuncio.comprador_id,
    }


@pytest.mark.django_db
def test_somente_o_vendedor_solicita_e_somente_o_comprador_responde(cliente_api, negociacao):
    comprador, vendedor = negociacao.oferta.anuncio.comprador, negociacao.oferta.vendedor

    assert acao(cliente_api, comprador, negociacao).status_code == status.HTTP_403_FORBIDDEN
    assert solicitar(cliente_api, negociacao).status_code == status.HTTP_200_OK
    assert acao(cliente_api, vendedor, negociacao, "/confirmacao").status_code == status.HTTP_403_FORBIDDEN
    assert acao(cliente_api, vendedor, negociacao, "/recusa").status_code == status.HTTP_403_FORBIDDEN
    assert_estados(
        negociacao,
        negociacao_status=Negociacao.Status.EM_ANDAMENTO,
        anuncio_status=Anuncio.Status.EM_NEGOCIACAO,
        produto_status=Produto.Status.RESERVADO,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("sufixo", ["", "/confirmacao", "/recusa"])
def test_terceiros_nao_alteram_a_negociacao(cliente_api, negociacao, terceiro, sufixo):
    assert acao(cliente_api, terceiro, negociacao, sufixo).status_code == status.HTTP_404_NOT_FOUND
    assert cliente_api.get(f"/api/v1/negociacoes/{negociacao.pk}").status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_confirmacao_e_recusa_exigem_solicitacao_pendente(cliente_api, negociacao):
    assert confirmar(cliente_api, negociacao).status_code == status.HTTP_400_BAD_REQUEST
    assert recusar(cliente_api, negociacao).status_code == status.HTTP_400_BAD_REQUEST
    assert solicitar(cliente_api, negociacao).status_code == status.HTTP_200_OK
    assert solicitar(cliente_api, negociacao).status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_recusa_restaura_negociacao_sem_alterar_anuncio_e_produto(cliente_api, negociacao):
    solicitar(cliente_api, negociacao)

    resposta = recusar(cliente_api, negociacao)

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["conclusao_solicitada_em"] is None
    assert_estados(
        negociacao,
        negociacao_status=Negociacao.Status.EM_ANDAMENTO,
        anuncio_status=Anuncio.Status.EM_NEGOCIACAO,
        produto_status=Produto.Status.RESERVADO,
    )
    assert not Notificacao.objects.exists()
    assert solicitar(cliente_api, negociacao).status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_prazo_vencido_conclui_automaticamente_pelo_comando(negociacao, settings):
    vencer_prazo(negociacao, settings)

    call_command("concluir_negociacoes_expiradas")

    assert_estados(
        negociacao,
        negociacao_status=Negociacao.Status.CONCLUIDA,
        anuncio_status=Anuncio.Status.ENCERRADO,
        produto_status=Produto.Status.VENDIDO,
    )
    assert negociacao.confirmada_em is None


@pytest.mark.django_db
def test_prazo_nao_vencido_nao_conclui(negociacao, settings):
    negociacao.conclusao_solicitada_em = timezone.now() - timedelta(
        hours=settings.NEGOCIACAO_PRAZO_CONFIRMACAO_HORAS - 1
    )
    negociacao.save(update_fields=["conclusao_solicitada_em"])

    call_command("concluir_negociacoes_expiradas")

    negociacao.refresh_from_db()
    assert negociacao.status == Negociacao.Status.EM_ANDAMENTO


@pytest.mark.django_db
def test_recusa_apos_prazo_e_rejeitada_e_conclusao_automatica_persiste(cliente_api, negociacao, settings):
    vencer_prazo(negociacao, settings)

    resposta = recusar(cliente_api, negociacao)

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST
    assert "automaticamente" in str(resposta.data)
    negociacao.refresh_from_db()
    assert negociacao.status == Negociacao.Status.CONCLUIDA


@pytest.mark.django_db
def test_consulta_aplica_conclusao_automatica_vencida(cliente_api, negociacao, settings):
    vencer_prazo(negociacao, settings)
    cliente_api.force_authenticate(user=negociacao.oferta.vendedor)

    resposta = cliente_api.get(f"/api/v1/negociacoes/{negociacao.pk}")

    assert resposta.data["status"] == Negociacao.Status.CONCLUIDA
    assert resposta.data["conclusao_automatica"] is True


@pytest.mark.django_db
def test_negociacao_concluida_e_imutavel(cliente_api, negociacao):
    solicitar(cliente_api, negociacao)
    confirmar(cliente_api, negociacao)

    for resposta in (
        solicitar(cliente_api, negociacao),
        confirmar(cliente_api, negociacao),
        recusar(cliente_api, negociacao),
    ):
        assert resposta.status_code == status.HTTP_400_BAD_REQUEST

    negociacao.refresh_from_db()
    negociacao.status = Negociacao.Status.EM_ANDAMENTO
    with pytest.raises(ValidationError, match="imutáveis"):
        negociacao.save()


def _concluir(cliente_api, negociacao):
    solicitar(cliente_api, negociacao)
    confirmar(cliente_api, negociacao)
    negociacao.refresh_from_db()
    return negociacao


@pytest.mark.django_db
def test_historico_lista_apenas_negociacoes_encerradas_das_partes(cliente_api, negociacao, terceiro):
    vendedor, comprador = negociacao.oferta.vendedor, negociacao.oferta.anuncio.comprador
    cliente_api.force_authenticate(user=vendedor)
    assert cliente_api.get("/api/v1/historico").data["results"] == []
    assert cliente_api.get(f"/api/v1/historico/{negociacao.pk}").status_code == status.HTTP_404_NOT_FOUND

    _concluir(cliente_api, negociacao)

    for usuario, papel in ((vendedor, "vendedor"), (comprador, "comprador")):
        cliente_api.force_authenticate(user=usuario)
        resultados = cliente_api.get("/api/v1/historico").data["results"]
        assert [(r["id"], r["papel"]) for r in resultados] == [(str(negociacao.pk), papel)]

    cliente_api.force_authenticate(user=terceiro)
    assert cliente_api.get("/api/v1/historico").data["results"] == []
    assert cliente_api.get(f"/api/v1/historico/{negociacao.pk}").status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filtros", "encontra"),
    [
        ({"papel": "vendedor"}, True),
        ({"papel": "comprador"}, False),
        ({"status": "concluida"}, True),
        ({"status": "cancelada"}, False),
        ({"papel": "vendedor", "status": "concluida"}, True),
    ],
)
def test_filtros_do_historico(cliente_api, negociacao, filtros, encontra):
    _concluir(cliente_api, negociacao)
    cliente_api.force_authenticate(user=negociacao.oferta.vendedor)

    resultados = cliente_api.get("/api/v1/historico", filtros).data["results"]

    assert bool(resultados) is encontra


@pytest.mark.django_db
@pytest.mark.parametrize("filtros", [{"papel": "admin"}, {"status": "em_andamento"}])
def test_filtros_invalidos_do_historico(cliente_api, usuario, filtros):
    cliente_api.force_authenticate(user=usuario)

    assert cliente_api.get("/api/v1/historico", filtros).status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_historico_e_somente_leitura(cliente_api, negociacao, metodo):
    negociacao = _concluir(cliente_api, negociacao)

    for url in ("/api/v1/historico", f"/api/v1/historico/{negociacao.pk}"):
        assert getattr(cliente_api, metodo)(url, {}, format="json").status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_detalhe_do_historico_traz_valores_e_mensagens(cliente_api, negociacao):
    oferta = negociacao.oferta
    cliente_api.force_authenticate(user=oferta.vendedor)
    cliente_api.post(f"/api/v1/conversas/{oferta.pk}/mensagens", {"texto": "Entrego no sábado"}, format="json")
    _concluir(cliente_api, negociacao)
    cliente_api.force_authenticate(user=oferta.anuncio.comprador)

    resposta = cliente_api.get(f"/api/v1/historico/{negociacao.pk}")

    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["valor_final"] == "1400.00"
    assert resposta.data["preco_inicial"] == "1500.00"
    assert [p["tipo_evento"] for p in resposta.data["precos"]] == ["enviada"]
    assert [m["texto"] for m in resposta.data["mensagens"]] == ["Entrego no sábado"]
    assert resposta.data["contraparte"]["nome"] == oferta.vendedor.nome


@pytest.mark.django_db
def test_estado_da_avaliacao_reflete_avaliacao_enviada(cliente_api, negociacao):
    negociacao = _concluir(cliente_api, negociacao)
    comprador = negociacao.oferta.anuncio.comprador
    Avaliacao.objects.create(negociacao=negociacao, autor=comprador, avaliado=negociacao.oferta.vendedor, nota=5)

    cliente_api.force_authenticate(user=comprador)
    assert cliente_api.get(f"/api/v1/historico/{negociacao.pk}").data["avaliacao"] == {
        "disponivel": False,
        "enviada": True,
    }
    cliente_api.force_authenticate(user=negociacao.oferta.vendedor)
    assert cliente_api.get(f"/api/v1/historico/{negociacao.pk}").data["avaliacao"] == {
        "disponivel": True,
        "enviada": False,
    }

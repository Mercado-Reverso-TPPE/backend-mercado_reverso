import uuid

import pytest
from django.core.exceptions import ValidationError
from rest_framework import status

from quero.anuncios.models import Anuncio
from quero.moderacao.models import AcaoModeracao
from quero.negociacao.models import Negociacao
from quero.ofertas.models import EventoNegociacao, Oferta
from quero.ofertas.services import enviar_oferta


def url_mensagens(oferta):
    return f"/api/v1/conversas/{oferta.pk}/mensagens"


def enviar(cliente_api, usuario, oferta, texto="Olá!"):
    cliente_api.force_authenticate(user=usuario)
    return cliente_api.post(url_mensagens(oferta), {"texto": texto}, format="json")


@pytest.mark.django_db
def test_partes_trocam_mensagens_na_conversa_da_oferta(cliente_api, oferta):
    comprador = oferta.anuncio.comprador
    assert enviar(cliente_api, oferta.vendedor, oferta, "Posso entregar amanhã.").status_code == status.HTTP_201_CREATED
    assert enviar(cliente_api, comprador, oferta, "Combinado!").status_code == status.HTTP_201_CREATED  

    resposta = cliente_api.get(url_mensagens(oferta))

    assert resposta.status_code == status.HTTP_200_OK
    mensagens = resposta.data["results"]
    assert [m["texto"] for m in mensagens] == ["Posso entregar amanhã.", "Combinado!"]
    assert [m["minha"] for m in mensagens] == [False, True]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("metodo", "sufixo"),
    [("get", "mensagens"), ("post", "mensagens"), ("post", "leitura"), ("post", "denuncias")],
)
def test_terceiros_nao_acessam_a_conversa(cliente_api, oferta, terceiro, metodo, sufixo):
    cliente_api.force_authenticate(user=terceiro)

    resposta = getattr(cliente_api, metodo)(
        f"/api/v1/conversas/{oferta.pk}/{sufixo}", {"texto": "Oi", "motivo": "Spam"}, format="json"
    )

    assert resposta.status_code == status.HTTP_403_FORBIDDEN
    assert not EventoNegociacao.objects.filter(tipo_evento=EventoNegociacao.TipoEvento.MENSAGEM).exists()


@pytest.mark.django_db
def test_conversa_inexistente_retorna_404(cliente_api, terceiro):
    cliente_api.force_authenticate(user=terceiro)

    assert cliente_api.get(f"/api/v1/conversas/{uuid.uuid4()}/mensagens").status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.parametrize("metodo", ["put", "patch", "delete"])
def test_mensagens_nao_podem_ser_editadas_ou_excluidas(cliente_api, oferta, metodo):
    enviar(cliente_api, oferta.vendedor, oferta, "Original")

    resposta = getattr(cliente_api, metodo)(url_mensagens(oferta), {"texto": "Alterada"}, format="json")

    assert resposta.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert EventoNegociacao.objects.get(tipo_evento=EventoNegociacao.TipoEvento.MENSAGEM).texto == "Original"


@pytest.mark.django_db
@pytest.mark.parametrize("texto", ["", "   "])
def test_mensagem_vazia_e_rejeitada(cliente_api, oferta, texto):
    assert enviar(cliente_api, oferta.vendedor, oferta, texto).status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_polling_retorna_apenas_mensagens_novas(cliente_api, oferta):
    primeira = enviar(cliente_api, oferta.vendedor, oferta, "Primeira").data
    enviar(cliente_api, oferta.vendedor, oferta, "Segunda")

    resposta = cliente_api.get(url_mensagens(oferta), {"apos": primeira["id"]})

    assert [m["texto"] for m in resposta.data["results"]] == ["Segunda"]
    assert cliente_api.get(url_mensagens(oferta), {"apos": "abc"}).status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_contagem_e_marcacao_de_mensagens_nao_lidas(cliente_api, oferta, terceiro):
    comprador = oferta.anuncio.comprador
    enviar(cliente_api, oferta.vendedor, oferta, "Uma")
    enviar(cliente_api, oferta.vendedor, oferta, "Duas")

    assert cliente_api.get("/api/v1/conversas/nao-lidas").data == {"total": 0}

    cliente_api.force_authenticate(user=terceiro)
    assert cliente_api.get("/api/v1/conversas/nao-lidas").data == {"total": 0}
    assert cliente_api.get("/api/v1/conversas").data["results"] == []

    cliente_api.force_authenticate(user=comprador)
    assert cliente_api.get("/api/v1/conversas/nao-lidas").data == {"total": 2}
    conversa = cliente_api.get("/api/v1/conversas").data["results"][0]
    assert conversa["id"] == str(oferta.pk)
    assert conversa["mensagens_nao_lidas"] == 2
    assert conversa["papel"] == "comprador"
    assert conversa["contraparte"]["nome"] == oferta.vendedor.nome
    assert conversa["somente_leitura"] is False

    resposta = cliente_api.post(f"/api/v1/conversas/{oferta.pk}/leitura")

    assert resposta.data == {"marcadas": 2}
    assert cliente_api.get("/api/v1/conversas/nao-lidas").data == {"total": 0}
    assert not EventoNegociacao.objects.filter(tipo_evento="mensagem", lida_em__isnull=True).exists()


@pytest.mark.django_db
def test_mensagens_nao_aparecem_no_historico_de_precos_da_oferta(cliente_api, oferta):
    enviar(cliente_api, oferta.vendedor, oferta, "Mensagem de chat")

    resposta = cliente_api.get("/api/v1/ofertas/meus")

    assert [e["tipo_evento"] for e in resposta.data["results"][0]["historico"]] == ["enviada"]


def _retirar(oferta):
    oferta.status = Oferta.Status.RETIRADA
    oferta.save(update_fields=["status"])


def _recusar(oferta):
    oferta.status = Oferta.Status.RECUSADA
    oferta.save(update_fields=["status"])


def _encerrar_anuncio(oferta):
    oferta.anuncio.status = Anuncio.Status.ENCERRADO
    oferta.anuncio.save(update_fields=["status"])


def _encerrar_negociacao(status_final):
    def encerrar(oferta):
        Negociacao.objects.create(oferta=oferta, valor_final="1400.00", status=status_final)

    return encerrar


@pytest.mark.django_db
@pytest.mark.parametrize(
    "encerrar",
    [
        _retirar,
        _recusar,
        _encerrar_anuncio,
        _encerrar_negociacao(Negociacao.Status.CONCLUIDA),
        _encerrar_negociacao(Negociacao.Status.CANCELADA),
    ],
)
def test_conversa_encerrada_fica_somente_leitura(cliente_api, oferta, encerrar):
    enviar(cliente_api, oferta.vendedor, oferta, "Antes do encerramento")
    encerrar(oferta)

    resposta = enviar(cliente_api, oferta.vendedor, oferta, "Depois do encerramento")

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST
    assert "somente para leitura" in str(resposta.data)
    assert [m["texto"] for m in cliente_api.get(url_mensagens(oferta)).data["results"]] == ["Antes do encerramento"]
    assert cliente_api.get("/api/v1/conversas").data["results"][0]["somente_leitura"] is True


@pytest.mark.django_db
def test_conversa_continua_aberta_durante_negociacao(cliente_api, negociacao):
    assert enviar(cliente_api, negociacao.oferta.vendedor, negociacao.oferta).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_bloqueio_impede_mensagens_sem_apagar_historico(cliente_api, oferta):
    comprador = oferta.anuncio.comprador
    enviar(cliente_api, oferta.vendedor, oferta, "Antes do bloqueio")

    cliente_api.force_authenticate(user=comprador)
    resposta = cliente_api.post(
        "/api/v1/bloqueios", {"usuario_id": str(oferta.vendedor.pk), "motivo": "Insistente"}, format="json"
    )
    assert resposta.status_code == status.HTTP_201_CREATED
    assert cliente_api.get("/api/v1/bloqueios").data[0]["usuario_id"] == str(oferta.vendedor.pk)

    for autor in (oferta.vendedor, comprador):
        resposta = enviar(cliente_api, autor, oferta, "Depois do bloqueio")
        assert resposta.status_code == status.HTTP_400_BAD_REQUEST
        assert "bloqueio" in str(resposta.data)
    assert [m["texto"] for m in cliente_api.get(url_mensagens(oferta)).data["results"]] == ["Antes do bloqueio"]

    cliente_api.force_authenticate(user=comprador)
    assert cliente_api.delete(f"/api/v1/bloqueios/{oferta.vendedor.pk}").status_code == status.HTTP_204_NO_CONTENT
    assert AcaoModeracao.objects.get().estado == AcaoModeracao.Estado.REVOGADA
    assert enviar(cliente_api, oferta.vendedor, oferta, "Depois do desbloqueio").status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_vendedor_bloqueado_nao_envia_novas_ofertas_ao_comprador(cliente_api, anuncio, categoria, vendedor_no_raio):
    cliente_api.force_authenticate(user=anuncio.comprador)
    cliente_api.post("/api/v1/bloqueios", {"usuario_id": str(vendedor_no_raio.pk)}, format="json")

    with pytest.raises(ValidationError, match="bloqueio"):
        enviar_oferta(
            vendedor=vendedor_no_raio,
            anuncio_id=anuncio.pk,
            dados={"descricao": "Oferta", "estado_conservacao": Oferta.EstadoConservacao.NOVO, "preco": "10.00"},
        )


@pytest.mark.django_db
def test_validacoes_de_bloqueio(cliente_api, usuario, vendedor):
    cliente_api.force_authenticate(user=usuario)

    def bloquear(alvo_id):
        return cliente_api.post("/api/v1/bloqueios", {"usuario_id": str(alvo_id)}, format="json")

    assert bloquear(usuario.pk).status_code == status.HTTP_400_BAD_REQUEST
    assert bloquear(uuid.uuid4()).status_code == status.HTTP_400_BAD_REQUEST
    assert bloquear(vendedor.pk).status_code == status.HTTP_201_CREATED
    assert bloquear(vendedor.pk).status_code == status.HTTP_400_BAD_REQUEST
    assert cliente_api.delete(f"/api/v1/bloqueios/{vendedor.pk}").status_code == status.HTTP_204_NO_CONTENT
    assert cliente_api.delete(f"/api/v1/bloqueios/{vendedor.pk}").status_code == status.HTTP_400_BAD_REQUEST
    assert bloquear(vendedor.pk).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_denuncia_de_conversa_registra_acao_de_moderacao(cliente_api, oferta):
    mensagem = enviar(cliente_api, oferta.vendedor, oferta, "Mensagem ofensiva").data
    comprador = oferta.anuncio.comprador
    cliente_api.force_authenticate(user=comprador)
    url = f"/api/v1/conversas/{oferta.pk}/denuncias"

    resposta = cliente_api.post(url, {"motivo": "Linguagem ofensiva", "mensagem_id": mensagem["id"]}, format="json")

    assert resposta.status_code == status.HTTP_201_CREATED
    denuncia = AcaoModeracao.objects.get()
    assert denuncia.tipo == AcaoModeracao.Tipo.DENUNCIA_CONVERSA
    assert denuncia.estado == AcaoModeracao.Estado.ABERTA
    assert denuncia.alvo == oferta.vendedor
    assert denuncia.evento_id == mensagem["id"]
    assert EventoNegociacao.objects.filter(pk=mensagem["id"]).exists()

    duplicada = cliente_api.post(url, {"motivo": "De novo"}, format="json")
    assert duplicada.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dados", "erro"),
    [
        ({"motivo": "   "}, "motivo"),
        ({"motivo": "Spam", "mensagem_id": 999_999}, "não pertence"),
    ],
)
def test_denuncia_valida_motivo_e_mensagem(cliente_api, oferta, dados, erro):
    cliente_api.force_authenticate(user=oferta.anuncio.comprador)

    resposta = cliente_api.post(f"/api/v1/conversas/{oferta.pk}/denuncias", dados, format="json")

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST
    assert erro in str(resposta.data)
    assert not AcaoModeracao.objects.exists()


@pytest.mark.django_db
def test_nao_e_possivel_denunciar_a_propria_mensagem(cliente_api, oferta):
    mensagem = enviar(cliente_api, oferta.vendedor, oferta, "Minha").data

    resposta = cliente_api.post(
        f"/api/v1/conversas/{oferta.pk}/denuncias", {"motivo": "Teste", "mensagem_id": mensagem["id"]}, format="json"
    )

    assert resposta.status_code == status.HTTP_400_BAD_REQUEST

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import override_settings
from django.utils import timezone
from datetime import timedelta

from quero.anuncios.models import Anuncio
from quero.catalogo.models import Produto
from quero.contas.models import Usuario
from quero.negociacao.models import Negociacao
from quero.ofertas.models import EventoNegociacao, Oferta
from quero.ofertas.serializers import EventoNegociacaoSerializer
from quero.ofertas.services import (
    aceitar_oferta,
    cancelar_negociacao,
    editar_oferta,
    enviar_contraproposta,
    enviar_oferta,
    recusar_oferta,
    retirar_oferta,
    responder_contraproposta,
)


def _criar_oferta(anuncio, vendedor, preco="120.00", produto_id=None):
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])
    dados = {
        "descricao": "Produto para troca",
        "estado_conservacao": Oferta.EstadoConservacao.SEMINOVO,
        "preco": Decimal(preco),
    }
    if produto_id:
        dados["produto_id"] = produto_id
    return enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)


def _outro_vendedor(anuncio, email="outro-vendedor@example.com"):
    vendedor = Usuario.objects.create_user(email=email, password="senha-valida-123", nome="Outro vendedor")
    vendedor.ponto = anuncio.comprador.ponto
    vendedor.save(update_fields=["ponto"])
    return vendedor


@pytest.mark.django_db
@override_settings(CONTRAPROPOSTA_LIMITE_RODADAS=2, CONTRAPROPOSTA_PRAZO_HORAS=24)
def test_limite_compartilhado_e_aceite_de_contraproposta_inicia_negociacao(anuncio, vendedor):
    oferta = _criar_oferta(anuncio, vendedor)
    primeiro = enviar_contraproposta(
        oferta_id=oferta.pk,
        autor=anuncio.comprador,
        preco=Decimal("110.00"),
    )
    responder_contraproposta(
        oferta_id=oferta.pk,
        usuario=vendedor,
        acao="contrapropor",
        preco=Decimal("105.00"),
    )

    primeiro.refresh_from_db()
    oferta.refresh_from_db()
    rodada_aberta = oferta.eventos.get(
        tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA,
        rodada=2,
    )
    assert primeiro.resultado == EventoNegociacao.Resultado.SUBSTITUIDA
    assert oferta.preco == Decimal("120.00")
    assert oferta.status == Oferta.Status.EM_NEGOCIACAO
    assert rodada_aberta.resultado == EventoNegociacao.Resultado.PENDENTE

    with pytest.raises(ValidationError, match="limite"):
        responder_contraproposta(
            oferta_id=oferta.pk,
            usuario=anuncio.comprador,
            acao="contrapropor",
            preco=Decimal("100.00"),
        )
    rodada_aberta.refresh_from_db()
    assert rodada_aberta.respondida_em is None

    negociacao = responder_contraproposta(
        oferta_id=oferta.pk,
        usuario=anuncio.comprador,
        acao="aceitar",
    )
    assert negociacao == oferta
    negociacao = Negociacao.objects.get(oferta=oferta)
    assert negociacao.valor_final == Decimal("105.00")
    assert negociacao.status == Negociacao.Status.EM_ANDAMENTO
    anuncio.refresh_from_db()
    oferta.refresh_from_db()
    assert anuncio.status == Anuncio.Status.EM_NEGOCIACAO
    assert oferta.status == Oferta.Status.ACEITA
    assert oferta.preco == Decimal("105.00")


@pytest.mark.django_db
@override_settings(CONTRAPROPOSTA_LIMITE_RODADAS=1, CONTRAPROPOSTA_PRAZO_HORAS=1)
def test_expiracao_preserva_preco_e_permite_nova_contraproposta(anuncio, vendedor):
    oferta = _criar_oferta(anuncio, vendedor, preco="150.00")
    contraproposta = enviar_contraproposta(
        oferta_id=oferta.pk,
        autor=anuncio.comprador,
        preco=Decimal("130.00"),
    )
    EventoNegociacao.objects.filter(pk=contraproposta.pk).update(expira_em=timezone.now() - timedelta(seconds=1))

    result = responder_contraproposta(
        oferta_id=oferta.pk,
        usuario=vendedor,
        acao="aceitar",
    )
    assert result is None
    contraproposta.refresh_from_db()
    oferta.refresh_from_db()
    assert contraproposta.resultado == EventoNegociacao.Resultado.EXPIRADA
    assert oferta.preco == Decimal("150.00")
    assert oferta.status == Oferta.Status.EM_NEGOCIACAO

    with pytest.raises(ValidationError, match="limite"):
        enviar_contraproposta(
            oferta_id=oferta.pk,
            autor=vendedor,
            preco=Decimal("140.00"),
        )


@pytest.mark.django_db
def test_permissoes_e_recusa_de_contraproposta_preservam_oferta(anuncio, vendedor):
    oferta = _criar_oferta(anuncio, vendedor)
    outsider = _outro_vendedor(anuncio)
    with pytest.raises(ValidationError, match="não participa"):
        enviar_contraproposta(oferta_id=oferta.pk, autor=outsider, preco=Decimal("110.00"))

    contraproposta = enviar_contraproposta(
        oferta_id=oferta.pk,
        autor=anuncio.comprador,
        preco=Decimal("110.00"),
    )
    with pytest.raises(ValidationError, match="destinatário"):
        responder_contraproposta(
            oferta_id=oferta.pk,
            usuario=anuncio.comprador,
            acao="aceitar",
        )
    responder_contraproposta(
        oferta_id=oferta.pk,
        usuario=vendedor,
        acao="recusar",
        justificativa="Preço muito baixo.",
    )
    contraproposta.refresh_from_db()
    oferta.refresh_from_db()
    assert contraproposta.resultado == EventoNegociacao.Resultado.RECUSADA
    assert oferta.preco == Decimal("120.00")
    assert oferta.status == Oferta.Status.EM_NEGOCIACAO
    justificativa_evento = oferta.eventos.get(
        tipo_evento=EventoNegociacao.TipoEvento.CONTRAPROPOSTA_RECUSADA
    )
    serialized_author = EventoNegociacaoSerializer(
        justificativa_evento,
        context={"request": type("Request", (), {"user": vendedor})()},
    ).data
    serialized_recipient = EventoNegociacaoSerializer(
        justificativa_evento,
        context={"request": type("Request", (), {"user": anuncio.comprador})()},
    ).data
    assert serialized_author["justificativa"] == ""
    assert serialized_recipient["justificativa"] == "Preço muito baixo."


@pytest.mark.django_db
def test_recusa_de_oferta_mantem_motivo_privado_ao_destinatario(anuncio, vendedor):
    oferta = _criar_oferta(anuncio, vendedor)
    with pytest.raises(ValidationError, match="Somente o comprador"):
        recusar_oferta(oferta_id=oferta.pk, comprador=vendedor, justificativa="não")

    recusada = recusar_oferta(
        oferta_id=oferta.pk,
        comprador=anuncio.comprador,
        justificativa="Não atende ao orçamento.",
    )
    assert recusada.status == Oferta.Status.RECUSADA
    evento = recusada.eventos.get(tipo_evento=EventoNegociacao.TipoEvento.RECUSADA)
    autor = EventoNegociacaoSerializer(
        evento,
        context={"request": type("Request", (), {"user": anuncio.comprador})()},
    ).data
    destinatario = EventoNegociacaoSerializer(
        evento,
        context={"request": type("Request", (), {"user": vendedor})()},
    ).data
    assert autor["justificativa"] == ""
    assert destinatario["justificativa"] == "Não atende ao orçamento."


@pytest.mark.django_db
def test_aceite_recusa_concorrentes_e_cancelamento_reserva_produto(
    anuncio, vendedor, categoria
):
    produto = Produto.objects.create(
        vendedor=vendedor,
        categoria=categoria,
        nome="Notebook",
        descricao="Notebook seminovo",
        estado_conservacao=Produto.EstadoConservacao.SEMINOVO,
        preco=Decimal("120.00"),
    )
    vencedora = _criar_oferta(anuncio, vendedor, produto_id=produto.pk)
    concorrente = _criar_oferta(anuncio, _outro_vendedor(anuncio), preco="100.00")

    with pytest.raises(ValidationError, match="Somente o comprador"):
        aceitar_oferta(oferta_id=vencedora.pk, comprador=vendedor)
    negociacao = aceitar_oferta(oferta_id=vencedora.pk, comprador=anuncio.comprador)
    concorrente.refresh_from_db()
    produto.refresh_from_db()
    assert concorrente.status == Oferta.Status.RECUSADA
    assert concorrente.eventos.filter(tipo_evento=EventoNegociacao.TipoEvento.RECUSADA).exists()
    assert produto.status == Produto.Status.RESERVADO
    with pytest.raises(ValidationError, match="anúncios ativos"):
        _criar_oferta(anuncio, _outro_vendedor(anuncio, "terceiro-vendedor@example.com"))
    with pytest.raises(ValidationError, match="não pode mais ser alterada"):
        editar_oferta(oferta=vencedora, vendedor=vendedor, dados={"preco": Decimal("99.00")})
    with pytest.raises(ValidationError, match="não pode mais ser retirada"):
        retirar_oferta(oferta=vencedora, vendedor=vendedor)

    with pytest.raises(ValidationError, match="não participa"):
        cancelar_negociacao(negociacao_id=negociacao.pk, usuario=_outro_vendedor(anuncio, "outsider@example.com"))
    cancelada = cancelar_negociacao(negociacao_id=negociacao.pk, usuario=anuncio.comprador)
    produto.refresh_from_db()
    anuncio.refresh_from_db()
    assert cancelada.status == Negociacao.Status.CANCELADA
    assert produto.status == Produto.Status.DISPONIVEL
    assert anuncio.status == Anuncio.Status.ATIVO

    nova = _criar_oferta(anuncio, vendedor, preco="115.00")
    vencedora.refresh_from_db()
    assert nova.status == Oferta.Status.ENVIADA
    assert vencedora.status == Oferta.Status.ACEITA


@pytest.mark.django_db(transaction=True)
def test_aceites_concorrentes_nao_criam_duas_negociacoes(anuncio, vendedor):
    primeira = _criar_oferta(anuncio, vendedor)
    segunda = _criar_oferta(anuncio, _outro_vendedor(anuncio), preco="100.00")
    barreira = Barrier(2)

    def aceitar(oferta_id):
        try:
            barreira.wait(timeout=10)
            try:
                aceitar_oferta(oferta_id=oferta_id, comprador=anuncio.comprador)
                return "aceita"
            except ValidationError:
                return "rejeitada"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(aceitar, (primeira.pk, segunda.pk)))

    assert resultados.count("aceita") == 1
    assert Negociacao.objects.filter(anuncio=anuncio).count() == 1
    anuncio.refresh_from_db()
    assert anuncio.status == Anuncio.Status.EM_NEGOCIACAO

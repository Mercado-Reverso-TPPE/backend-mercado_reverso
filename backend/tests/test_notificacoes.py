import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIRequestFactory, force_authenticate

from quero.notificacoes.catalogo import TipoNotificacao
from quero.notificacoes.controllers import (
    ContagemNaoLidasView,
    MarcarNotificacaoLidaView,
    NotificacoesView,
    PreferenciasNotificacaoView,
)
from quero.notificacoes.models import EventoNotificacao, Notificacao, PreferenciaNotificacao
from quero.notificacoes.services import emitir_notificacao
from quero.ofertas.models import EventoNegociacao, Oferta


@pytest.mark.django_db
def test_agrupa_eventos_sem_descartar_contexto_ou_duplicar_retentativas(usuario):
    argumentos = {
        "usuario": usuario,
        "tipo": TipoNotificacao.OFERTA_RECEBIDA,
        "titulo": "Nova oferta recebida",
        "mensagem": "Você recebeu uma nova oferta.",
        "agrupamento": "ofertas:anuncio-1",
    }

    emitir_notificacao(
        **argumentos,
        chave_evento="evento-1",
        contexto={"oferta_id": "oferta-1"},
    )
    emitir_notificacao(
        **argumentos,
        chave_evento="evento-2",
        contexto={"oferta_id": "oferta-2"},
    )
    emitir_notificacao(
        **argumentos,
        chave_evento="evento-1",
        contexto={"oferta_id": "oferta-1"},
    )

    assert Notificacao.objects.filter(usuario=usuario).count() == 1
    notificacao = Notificacao.objects.get(usuario=usuario)
    assert notificacao.contexto == [
        {"oferta_id": "oferta-1"},
        {"oferta_id": "oferta-2"},
    ]
    assert EventoNotificacao.objects.filter(usuario=usuario).count() == 2


@pytest.mark.django_db
def test_listagem_e_marcacao_de_leitura_isoladas_por_usuario(usuario):
    outro_usuario = type(usuario).objects.create_user(
        email="outra-pessoa@example.com",
        password="Senha-forte-123!",
        nome="Outra Pessoa",
    )
    propria = Notificacao.objects.create(
        usuario=usuario,
        tipo=TipoNotificacao.OFERTA_RECEBIDA,
        titulo="Oferta",
        mensagem="Sua notificação.",
    )
    alheia = Notificacao.objects.create(
        usuario=outro_usuario,
        tipo=TipoNotificacao.OFERTA_RECEBIDA,
        titulo="Privada",
        mensagem="Não deve aparecer.",
    )
    factory = APIRequestFactory()

    request = factory.get("/api/v1/notificacoes")
    force_authenticate(request, user=usuario)
    response = NotificacoesView.as_view()(request)
    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [str(propria.pk)]

    request = factory.patch(f"/api/v1/notificacoes/{alheia.pk}/lida")
    force_authenticate(request, user=usuario)
    response = MarcarNotificacaoLidaView.as_view()(request, notificacao_id=alheia.pk)
    assert response.status_code == 404
    assert alheia.lida_em is None

    request = factory.patch(f"/api/v1/notificacoes/{propria.pk}/lida")
    force_authenticate(request, user=usuario)
    response = MarcarNotificacaoLidaView.as_view()(request, notificacao_id=propria.pk)
    assert response.status_code == 200
    assert response.data["lida_em"] is not None


@pytest.mark.django_db
def test_notificacao_de_mensagem_nao_expoe_texto_privado(anuncio, vendedor, django_capture_on_commit_callbacks):
    oferta = Oferta.objects.create(
        anuncio=anuncio,
        vendedor=vendedor,
        descricao="Produto",
        estado_conservacao=Oferta.EstadoConservacao.USADO_BOM,
        preco="80.00",
    )
    with django_capture_on_commit_callbacks(execute=True):
        EventoNegociacao.objects.create(
            oferta=oferta,
            autor=vendedor,
            status=oferta.status,
            tipo_evento=EventoNegociacao.TipoEvento.MENSAGEM,
            texto="texto privado que não deve ir para a notificação",
        )

    notificacao = Notificacao.objects.get(usuario=anuncio.comprador)
    assert notificacao.tipo == TipoNotificacao.MENSAGEM_RECEBIDA
    assert "texto privado" not in notificacao.mensagem
    assert "texto privado" not in str(notificacao.contexto)
    assert not Notificacao.objects.filter(usuario=vendedor).exists()


@pytest.mark.django_db
def test_contagem_nao_lida_e_preferencias_tem_valor_padrao(usuario):
    for indice in range(2):
        Notificacao.objects.create(
            usuario=usuario,
            tipo=TipoNotificacao.OFERTA_RECEBIDA,
            titulo=f"Oferta {indice}",
            mensagem="Nova oferta.",
        )
    factory = APIRequestFactory()
    request = factory.get("/api/v1/notificacoes/nao-lidas")
    force_authenticate(request, user=usuario)
    response = ContagemNaoLidasView.as_view()(request)
    assert response.data == {"nao_lidas": 2}

    request = factory.get("/api/v1/preferencias/notificacoes")
    force_authenticate(request, user=usuario)
    response = PreferenciasNotificacaoView.as_view()(request)
    preferencias = {(item["tipo"], item["canal"]): item["habilitada"] for item in response.data["preferencias"]}
    assert preferencias[(TipoNotificacao.OFERTA_RECEBIDA, "email")] is True
    assert preferencias[(TipoNotificacao.SEGURANCA_CONTA, "aplicativo")] is True


@pytest.mark.django_db
def test_preferencias_podem_desativar_email_mas_nao_alertas_de_seguranca(usuario):
    factory = APIRequestFactory()
    request = factory.patch(
        "/api/v1/preferencias/notificacoes",
        {"preferencias": [{"tipo": TipoNotificacao.OFERTA_RECEBIDA, "canal": "email", "habilitada": False}]},
        format="json",
    )
    force_authenticate(request, user=usuario)
    response = PreferenciasNotificacaoView.as_view()(request)
    assert response.status_code == 200
    assert (
        PreferenciaNotificacao.objects.get(
            usuario=usuario,
            tipo=TipoNotificacao.OFERTA_RECEBIDA,
            canal="email",
        ).habilitada
        is False
    )

    request = factory.patch(
        "/api/v1/preferencias/notificacoes",
        {"preferencias": [{"tipo": TipoNotificacao.SEGURANCA_CONTA, "canal": "email", "habilitada": False}]},
        format="json",
    )
    force_authenticate(request, user=usuario)
    response = PreferenciasNotificacaoView.as_view()(request)
    assert response.status_code == 400
    assert not PreferenciaNotificacao.objects.filter(
        usuario=usuario,
        tipo=TipoNotificacao.SEGURANCA_CONTA,
        habilitada=False,
    ).exists()

    with pytest.raises(IntegrityError), transaction.atomic():
        PreferenciaNotificacao.objects.create(
            usuario=usuario,
            tipo=TipoNotificacao.SEGURANCA_CONTA,
            canal=PreferenciaNotificacao.Canal.EMAIL,
            habilitada=False,
        )


@pytest.mark.django_db(transaction=True)
def test_email_desativado_nao_impede_alerta_de_seguranca(usuario, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "quero.notificacoes.services.send_mail",
        lambda **kwargs: chamadas.append(kwargs) or 1,
    )
    PreferenciaNotificacao.objects.create(
        usuario=usuario,
        tipo=TipoNotificacao.OFERTA_RECEBIDA,
        canal=PreferenciaNotificacao.Canal.EMAIL,
        habilitada=False,
    )
    emitir_notificacao(
        usuario=usuario,
        tipo=TipoNotificacao.OFERTA_RECEBIDA,
        titulo="Oferta",
        mensagem="Nova oferta.",
        chave_evento="oferta-sem-email",
    )
    emitir_notificacao(
        usuario=usuario,
        tipo=TipoNotificacao.SEGURANCA_CONTA,
        titulo="Segurança",
        mensagem="Atividade da conta.",
        chave_evento="seguranca-1",
    )

    assert len(chamadas) == 1
    assert chamadas[0]["subject"] == "Segurança"
    assert Notificacao.objects.filter(usuario=usuario).count() == 2


@pytest.mark.django_db(transaction=True)
def test_falha_de_email_e_registrada_sem_desfazer_notificacao(usuario, monkeypatch, caplog):
    def falha_email(**kwargs):
        raise RuntimeError("SMTP indisponível")

    monkeypatch.setattr("quero.notificacoes.services.send_mail", falha_email)

    resultado = emitir_notificacao(
        usuario=usuario,
        tipo=TipoNotificacao.OFERTA_RECEBIDA,
        titulo="Nova oferta",
        mensagem="Há uma oferta nova.",
        chave_evento="oferta-1",
    )
    repetir = emitir_notificacao(
        usuario=usuario,
        tipo=TipoNotificacao.OFERTA_RECEBIDA,
        titulo="Nova oferta",
        mensagem="Há uma oferta nova.",
        chave_evento="oferta-1",
    )

    assert resultado is not None
    assert repetir is None
    assert Notificacao.objects.filter(usuario=usuario).count() == 1
    assert "Falha ao enviar e-mail de notificação" in caplog.text


@pytest.mark.django_db
def test_alerta_de_troca_de_email_vai_para_o_endereco_anterior(usuario, mailoutbox, django_capture_on_commit_callbacks):
    from django.core import signing

    from quero.contas.services import confirmar_alteracao_email

    email_anterior = usuario.email
    token = signing.dumps(
        {"usuario_id": str(usuario.pk), "email_atual": email_anterior, "novo_email": "novo@example.com"},
        salt="quero.alteracao-email",
    )

    with django_capture_on_commit_callbacks(execute=True):
        confirmar_alteracao_email(token=token)

    assert [mensagem.to for mensagem in mailoutbox] == [[email_anterior]]


@pytest.mark.django_db
def test_vendedor_inativo_nao_recebe_anuncio_compativel(
    categoria, usuario_com_localizacao, vendedor, django_capture_on_commit_callbacks
):
    from quero.anuncios.services import criar_anuncio
    from quero.catalogo.models import Produto

    vendedor.ponto = usuario_com_localizacao.ponto
    vendedor.is_active = False
    vendedor.save(update_fields=["ponto", "is_active"])
    Produto.objects.create(
        vendedor=vendedor,
        categoria=categoria,
        nome="Notebook",
        descricao="Notebook",
        estado_conservacao=Produto.EstadoConservacao.SEMINOVO,
        preco="100.00",
    )

    with django_capture_on_commit_callbacks(execute=True):
        criar_anuncio(
            comprador=usuario_com_localizacao,
            dados={"titulo": "Procuro notebook", "categoria": categoria, "descricao": "Para estudo"},
        )

    assert not Notificacao.objects.filter(usuario=vendedor).exists()

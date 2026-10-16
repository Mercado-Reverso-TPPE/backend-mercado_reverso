from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from rest_framework import status

from quero.contas.models import AlteracaoEmailPendente, Localizacao, Usuario
from quero.contas.services import (
    acesso_bloqueado,
    confirmar_alteracao_email,
    confirmar_redefinicao_senha,
    registrar_falha_login,
    solicitar_alteracao_email,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("latitude", "longitude", "codigo"),
    [
        ("-23.55", "-46.63", status.HTTP_201_CREATED),
        ("91", "0", status.HTTP_400_BAD_REQUEST),
        ("0", "181", status.HTTP_400_BAD_REQUEST),
        ("-23.55", None, status.HTTP_400_BAD_REQUEST),
    ],
)
def test_cadastro_valida_coordenadas(cliente_api, latitude, longitude, codigo):
    dados = {
        "nome": "Nova Pessoa",
        "email": f"cadastro-{latitude}-{longitude}@example.com",
        "senha": "Senha-forte-123!",
    }
    if latitude is not None:
        dados["latitude"] = latitude
    if longitude is not None:
        dados["longitude"] = longitude

    resposta = cliente_api.post("/api/v1/usuarios", dados, format="json")

    assert resposta.status_code == codigo
    assert Usuario.objects.count() == (1 if codigo == status.HTTP_201_CREATED else 0)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dados_localizacao", "consulta_esperada"),
    [
        ({"cep": "01001-000"}, {"cep": "01001-000", "cidade": "", "uf": ""}),
        ({"cidade": "São Paulo", "uf": "SP"}, {"cep": "", "cidade": "São Paulo", "uf": "SP"}),
    ],
)
def test_cadastro_geocodifica_cep_ou_cidade_sem_chamar_servico_externo(
    cliente_api, dados_localizacao, consulta_esperada
):
    ponto = Point(-46.6333, -23.5505, srid=4326)
    with patch("quero.contas.serializers.geocodificar", return_value=(ponto, "01001-000", "São Paulo", "SP")) as geocodificar:
        resposta = cliente_api.post(
            "/api/v1/usuarios",
            {
                "nome": "Pessoa Geolocalizada",
                "email": "geo@example.com",
                "senha": "Senha-forte-123!",
                **dados_localizacao,
            },
            format="json",
        )

    assert resposta.status_code == status.HTTP_201_CREATED
    geocodificar.assert_called_once_with(**consulta_esperada)
    assert Usuario.objects.get(email="geo@example.com").localizacao.ponto == ponto


@pytest.mark.django_db
@pytest.mark.parametrize("email_existe", [True, False])
def test_login_responde_com_mensagem_generica_para_credenciais_invalidas(cliente_api, usuario, email_existe):
    email = usuario.email if email_existe else "inexistente@example.com"

    resposta = cliente_api.post(
        "/api/v1/sessoes",
        {"email": email, "password": "senha-incorreta"},
        format="json",
    )

    assert resposta.status_code == status.HTTP_401_UNAUTHORIZED
    assert resposta.data["detail"] == "E-mail ou senha inválidos."


@pytest.mark.django_db
@pytest.mark.parametrize(("limite", "falhas", "bloqueado"), [(2, 1, False), (2, 2, True), (3, 2, False)])
def test_bloqueio_de_login_respeita_limite_configurado(usuario, limite, falhas, bloqueado):
    from django.test import override_settings

    with override_settings(LOGIN_MAX_TENTATIVAS=limite):
        for _ in range(falhas):
            registrar_falha_login(usuario.email)

        assert acesso_bloqueado(usuario.email) is bloqueado


@pytest.mark.django_db
@pytest.mark.parametrize("email", ["pessoa@example.com", "nao-existe@example.com"])
def test_pedido_de_redefinicao_nao_revela_se_email_existe(cliente_api, usuario, email):
    resposta = cliente_api.post("/api/v1/senha/redefinir", {"email": email}, format="json")

    assert resposta.status_code == status.HTTP_202_ACCEPTED
    assert resposta.data == {"detail": "Se a conta existir, enviaremos um link de redefinição."}


@pytest.mark.django_db
@pytest.mark.parametrize("uso", ["token_valido", "token_alterado", "token_expirado"])
def test_redefinicao_de_senha_so_aceita_token_valido(usuario, uso):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.exceptions import ValidationError
    from django.test import override_settings

    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    if uso == "token_alterado":
        token = "token-invalido"
    if uso == "token_expirado":
        agora = datetime.now()
        with override_settings(PASSWORD_RESET_TIMEOUT=1):
            with patch.object(default_token_generator, "_now", return_value=agora + timedelta(seconds=2)):
                with pytest.raises(ValidationError):
                    confirmar_redefinicao_senha(uid=uid, token=token, nova_senha="Nova-senha-forte-456!")
        return

    if uso == "token_valido":
        confirmar_redefinicao_senha(uid=uid, token=token, nova_senha="Nova-senha-forte-456!")
        usuario.refresh_from_db()
        assert usuario.check_password("Nova-senha-forte-456!")
    else:
        with pytest.raises(ValidationError):
            confirmar_redefinicao_senha(uid=uid, token=token, nova_senha="Nova-senha-forte-456!")


@pytest.mark.django_db
def test_troca_de_email_requer_token_e_token_so_pode_ser_usado_uma_vez(usuario):
    from django.core.exceptions import ValidationError

    solicitar_alteracao_email(usuario=usuario, novo_email="novo@example.com")
    token = mail.outbox[-1].body.split("token=", 1)[1].split()[0]
    assert AlteracaoEmailPendente.objects.filter(usuario=usuario).exists()

    confirmar_alteracao_email(token=token)
    usuario.refresh_from_db()
    assert usuario.email == "novo@example.com"
    with pytest.raises(ValidationError):
        confirmar_alteracao_email(token=token)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(-23.6, -46.7), (-22.9, -43.2)],
)
def test_atualizar_perfil_com_coordenadas_reposiciona_anuncios(
    cliente_api, usuario_com_localizacao, anuncio, latitude, longitude
):
    cliente_api.force_authenticate(usuario_com_localizacao)
    dados = {"localizacao": {"latitude": latitude, "longitude": longitude}}
    resposta = cliente_api.patch("/api/v1/perfil", dados, format="json")

    assert resposta.status_code == status.HTTP_200_OK
    anuncio.refresh_from_db()
    assert anuncio.ponto == Point(longitude, latitude, srid=4326)
    assert usuario_com_localizacao.localizacao.ponto == anuncio.ponto

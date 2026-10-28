import pytest
from django.urls import reverse


@pytest.mark.parametrize(("logado", "status_esperado"), [(True, 200), (False, 401)])
def test_api_navegavel_aceita_sessao_em_desenvolvimento(client, usuario, logado, status_esperado):
    if logado:
        client.force_login(usuario)

    resposta = client.get("/api/v1/", HTTP_ACCEPT="text/html")

    assert resposta.status_code == status_esperado


def test_api_navegavel_tem_pagina_de_login(client, usuario):
    resposta = client.post(
        reverse("rest_framework:login"),
        {"username": usuario.email, "password": "Senha-forte-123!", "next": "/api/v1/"},
    )

    assert resposta.status_code == 302
    assert resposta.url == "/api/v1/"

import pytest
from django.contrib import admin
from django.urls import reverse

from quero.anuncios.models import Anuncio
from quero.contas.models import Usuario

MODELOS_REGISTRADOS = [
    (model._meta.app_label, model._meta.model_name)
    for model in admin.site._registry
    if model._meta.app_label not in {"auth", "token_blacklist"}
]


@pytest.fixture
def cliente_admin(client, db):
    superusuario = Usuario.objects.create_superuser(
        email="admin@example.com",
        password="Senha-forte-123!",
        nome="Administração",
    )
    client.force_login(superusuario)
    return client


@pytest.mark.parametrize(("app_label", "model_name"), MODELOS_REGISTRADOS)
def test_listagem_do_admin_abre(cliente_admin, app_label, model_name):
    resposta = cliente_admin.get(reverse(f"admin:{app_label}_{model_name}_changelist"))

    assert resposta.status_code == 200


def test_cadastro_de_usuario_pelo_admin(cliente_admin):
    resposta = cliente_admin.post(
        reverse("admin:contas_usuario_add"),
        {"email": "Nova@Example.com", "nome": "Nova", "password1": "Senha-forte-123!", "password2": "Senha-forte-123!"},
    )

    assert resposta.status_code == 302
    assert Usuario.objects.get(email="nova@example.com").check_password("Senha-forte-123!")


def test_admin_recusa_email_repetido_sem_diferenciar_maiusculas(cliente_admin, usuario):
    resposta = cliente_admin.post(
        reverse("admin:contas_usuario_add"),
        {
            "email": "PESSOA@example.com",
            "nome": "Outra",
            "password1": "Senha-forte-123!",
            "password2": "Senha-forte-123!",
        },
    )

    assert resposta.status_code == 200
    assert Usuario.objects.filter(email__iexact="pessoa@example.com").count() == 1


def test_anuncio_encerrado_nao_pode_ser_excluido_pelo_admin(cliente_admin, anuncio):
    anuncio.status = Anuncio.Status.ENCERRADO
    anuncio.save()

    resposta = cliente_admin.get(reverse("admin:anuncios_anuncio_delete", args=[anuncio.pk]))

    assert resposta.status_code == 403

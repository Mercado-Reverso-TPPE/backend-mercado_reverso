from django.apps import apps


def test_schema_de_dominio_tem_no_maximo_16_modelos():
    apps_de_dominio = {
        "contas",
        "anuncios",
        "ofertas",
        "catalogo",
        "negociacao",
        "descoberta",
        "notificacoes",
        "reputacao",
        "moderacao",
    }
    modelos = [
        model
        for model in apps.get_models(include_auto_created=False)
        if model._meta.app_label in apps_de_dominio and not model._meta.proxy
    ]

    assert len(modelos) == 16

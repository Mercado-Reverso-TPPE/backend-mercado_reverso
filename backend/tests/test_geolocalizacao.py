import json
from unittest.mock import patch
from urllib.error import URLError

import pytest
from django.core.exceptions import ValidationError
from rest_framework import status

from quero.contas.geocoding import localizar
from quero.core.models import Municipio, normalizar_nome

BRASILIA = 5300108


class RespostaFalsa:
    def __init__(self, corpo):
        self.corpo = json.dumps(corpo).encode()

    def read(self):
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def viacep(corpo):
    return patch("quero.contas.geocoding.urlopen", return_value=RespostaFalsa(corpo))


@pytest.mark.django_db
def test_migration_carrega_todos_os_municipios_do_ibge():
    assert Municipio.objects.count() == 5571
    assert Municipio.objects.filter(capital=True).count() == 27
    brasilia = Municipio.objects.get(pk=BRASILIA)
    assert (brasilia.nome, brasilia.uf) == ("Brasília", "DF")
    assert brasilia.ponto.y == pytest.approx(-15.78, abs=0.01)


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("São João del-Rei", "sao joao del rei"),
        ("  BRASÍLIA ", "brasilia"),
        ("Alta Floresta D'Oeste", "alta floresta d'oeste"),
    ],
)
def test_normalizar_nome(nome, esperado):
    assert normalizar_nome(nome) == esperado


@pytest.mark.django_db
def test_cidade_e_resolvida_no_banco_sem_servico_externo():
    with patch("quero.contas.geocoding.urlopen") as rede:
        ponto, cep, cidade, uf = localizar(cidade="brasilia", uf="df")

    rede.assert_not_called()
    assert (cep, cidade, uf) == ("", "Brasília", "DF")
    assert ponto == Municipio.objects.get(pk=BRASILIA).ponto


@pytest.mark.django_db
def test_cidade_homonima_exige_o_estado():
    with pytest.raises(ValidationError, match="Informe o estado"):
        localizar(cidade="Bom Jesus")
    assert localizar(cidade="Bom Jesus", uf="RS")[3] == "RS"


@pytest.mark.django_db
def test_cidade_inexistente():
    with pytest.raises(ValidationError, match="Não encontramos a cidade"):
        localizar(cidade="Cidade Inventada", uf="SP")


@pytest.mark.django_db
def test_cep_vira_municipio_pelo_codigo_ibge_e_fica_em_cache():
    with viacep({"cep": "72510-413", "localidade": "Brasília", "uf": "DF", "ibge": str(BRASILIA)}) as rede:
        primeiro = localizar(cep="72510413", cidade="Brasília", uf="DF")
        segundo = localizar(cep="72510-413")

    assert rede.call_count == 1
    assert primeiro[1:] == segundo[1:] == ("72510-413", "Brasília", "DF")
    assert primeiro[0] == Municipio.objects.get(pk=BRASILIA).ponto


@pytest.mark.django_db
def test_cep_inexistente_tambem_fica_em_cache():
    with viacep({"erro": "true"}) as rede:
        for _ in range(2):
            with pytest.raises(ValidationError, match="Não encontramos esse CEP"):
                localizar(cep="00000-000")
    assert rede.call_count == 1


@pytest.mark.django_db
def test_cep_de_outro_estado_e_recusado():
    with viacep({"ibge": "3550308"}), pytest.raises(ValidationError, match="São Paulo/SP, não de RJ"):
        localizar(cep="01001-000", uf="RJ")


@pytest.mark.django_db
def test_cep_com_formato_invalido_nem_consulta():
    with patch("quero.contas.geocoding.urlopen") as rede, pytest.raises(ValidationError, match="8 dígitos"):
        localizar(cep="1234")
    rede.assert_not_called()


@pytest.mark.django_db
def test_servico_de_cep_fora_do_ar():
    with (
        patch("quero.contas.geocoding.urlopen", side_effect=URLError("sem rede")),
        pytest.raises(ValidationError, match="serviço de CEP está indisponível"),
    ):
        localizar(cep="72510-413")


@pytest.mark.django_db
def test_perfil_salva_a_localizacao_pela_cidade(cliente_api, usuario):
    cliente_api.force_authenticate(user=usuario)

    resposta = cliente_api.patch(
        "/api/v1/perfil", {"localizacao": {"cep": "", "cidade": "Brasília", "uf": "DF"}}, format="json"
    )

    assert resposta.status_code == status.HTTP_200_OK, resposta.data
    usuario.refresh_from_db()
    assert (usuario.cidade, usuario.uf) == ("Brasília", "DF")
    assert usuario.ponto.y == pytest.approx(-15.78, abs=0.01)

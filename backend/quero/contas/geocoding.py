"""
Localização de referência a partir de CEP ou cidade.

As coordenadas vêm da tabela ``Municipio`` (PostGIS), carregada com os
municípios do IBGE e o ponto da sede de cada um: cidade e UF são resolvidas
no próprio banco, sem serviço externo.

O CEP precisa ser traduzido para um município, e não existe base pública de
CEP com coordenadas. Por isso só essa etapa consulta o ViaCEP
(``CEP_SERVICO_URL``), que devolve o código IBGE do município; o ponto sai da
tabela local. As respostas do ViaCEP ficam em cache por 30 dias.

A precisão é a da sede do município: suficiente para o raio dos anúncios,
que é medido em quilômetros.
"""

import json
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from quero.core.models import Municipio, normalizar_nome

CACHE_CEP_SEGUNDOS = 30 * 24 * 60 * 60


def _so_digitos(cep):
    return re.sub(r"\D", "", cep or "")


def _formatar_cep(digitos):
    return f"{digitos[:5]}-{digitos[5:]}"


def _consultar_cep(digitos):
    """Código IBGE do município do CEP, ou ``None`` quando o CEP não existe."""
    chave = f"cep:v1:{digitos}"
    em_cache = cache.get(chave)
    if em_cache is not None:
        return em_cache or None

    url = f"{settings.CEP_SERVICO_URL.rstrip('/')}/{digitos}/json/"
    request = Request(url, headers={"User-Agent": settings.GEOCODER_USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            dados = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValidationError("O serviço de CEP está indisponível. Tente novamente ou informe a cidade.") from exc

    codigo = None if dados.get("erro") else str(dados.get("ibge") or "")
    # Guarda também a ausência ("") para não repetir a consulta de um CEP inexistente.
    cache.set(chave, codigo or "", timeout=CACHE_CEP_SEGUNDOS)
    return codigo or None


def municipio_da_cidade(cidade, uf=""):
    """O município com esse nome (sem diferenciar acento nem maiúsculas), na UF quando informada."""
    municipios = Municipio.objects.filter(nome_busca=normalizar_nome(cidade))
    if uf:
        municipios = municipios.filter(uf=uf.upper())
    encontrados = list(municipios[:2])
    if not encontrados:
        local = f"{cidade.strip()}/{uf.upper()}" if uf else cidade.strip()
        raise ValidationError(f"Não encontramos a cidade {local}. Confira o nome e o estado.")
    if len(encontrados) > 1:
        raise ValidationError("Há mais de uma cidade com esse nome. Informe o estado.")
    return encontrados[0]


def localizar(*, cep="", cidade="", uf=""):
    """Devolve ``(ponto, cep, cidade, uf)`` a partir do CEP ou, sem ele, da cidade."""
    digitos, cidade, uf = _so_digitos(cep), cidade.strip(), uf.strip().upper()
    if not digitos and not cidade:
        raise ValidationError("Informe um CEP ou uma cidade para localizar o endereço.")
    if digitos and len(digitos) != 8:
        raise ValidationError("O CEP precisa ter 8 dígitos.")

    if digitos:
        codigo = _consultar_cep(digitos)
        municipio = Municipio.objects.filter(pk=codigo).first() if codigo else None
        if municipio is None:
            raise ValidationError("Não encontramos esse CEP. Confira os números ou informe só a cidade.")
        if uf and uf != municipio.uf:
            raise ValidationError(f"Esse CEP é de {municipio.nome}/{municipio.uf}, não de {uf}.")
        return municipio.ponto, _formatar_cep(digitos), municipio.nome, municipio.uf

    municipio = municipio_da_cidade(cidade, uf)
    return municipio.ponto, "", municipio.nome, municipio.uf

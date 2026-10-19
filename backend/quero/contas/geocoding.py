import hashlib
import json
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError


def _chave_localizacao(*, cep, cidade, uf):
    endereco = "|".join((cep.strip().casefold(), cidade.strip().casefold(), uf.strip().casefold()))
    return hashlib.sha256(endereco.encode("utf-8")).hexdigest()


def _parametros_busca(*, cep, cidade, uf):
    parametros = {"format": "jsonv2", "limit": 1, "country": "Brazil", "countrycodes": "br"}
    if cep:
        parametros["postalcode"] = cep
    else:
        parametros["q"] = ", ".join(parte for parte in (cidade, uf, "Brasil") if parte)
    return parametros


def _buscar_no_nominatim(*, cep, cidade, uf):
    url_base = settings.GEOCODER_URL.rstrip("/")
    url = f"{url_base}/search?{urlencode(_parametros_busca(cep=cep, cidade=cidade, uf=uf))}"
    request = Request(url, headers={"User-Agent": settings.GEOCODER_USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            resultados = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValidationError("O serviço de localização está indisponível. Tente novamente.") from exc

    if not resultados:
        raise ValidationError("Não foi possível localizar o CEP ou a cidade informada.")

    resultado = resultados[0]
    endereco = resultado.get("address", {})
    codigo_uf = endereco.get("ISO3166-2-lvl4", "").removeprefix("BR-")
    cidade_encontrada = (cidade or endereco.get("city") or endereco.get("town") or endereco.get("village") or endereco.get("municipality") or "").strip()
    uf_encontrada = (uf or codigo_uf).upper()
    cep_encontrado = (cep or endereco.get("postcode", "")).strip()
    ponto = Point(float(resultado["lon"]), float(resultado["lat"]), srid=4326)
    return ponto, cep_encontrado, cidade_encontrada, uf_encontrada


def localizar(*, cep="", cidade="", uf=""):
    cep, cidade, uf = cep.strip(), cidade.strip(), uf.strip().upper()
    if not cep and not cidade:
        raise ValidationError("Informe um CEP ou uma cidade para localizar o endereço.")

    chave = _chave_localizacao(cep=cep, cidade=cidade, uf=uf)
    chave_cache = f"geocodificacao:v1:{chave}"
    resultado_cache = cache.get(chave_cache)
    if resultado_cache:
        return (
            Point(resultado_cache["longitude"], resultado_cache["latitude"], srid=4326),
            resultado_cache["cep"],
            resultado_cache["cidade"],
            resultado_cache["uf"],
        )

    limite_cache = "geocodificador:nominatim:intervalo"
    while not cache.add(limite_cache, True, timeout=1):
        time.sleep(0.05)

    resultado_cache = cache.get(chave_cache)
    if resultado_cache:
        return (
            Point(resultado_cache["longitude"], resultado_cache["latitude"], srid=4326),
            resultado_cache["cep"],
            resultado_cache["cidade"],
            resultado_cache["uf"],
        )

    try:
        ponto, cep, cidade, uf = _buscar_no_nominatim(cep=cep, cidade=cidade, uf=uf)
    except ValidationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("O serviço de localização retornou uma resposta inválida.") from exc

    cache.set(
        chave_cache,
        {"longitude": ponto.x, "latitude": ponto.y, "cep": cep, "cidade": cidade, "uf": uf},
        timeout=30 * 24 * 60 * 60,
    )
    return ponto, cep, cidade, uf

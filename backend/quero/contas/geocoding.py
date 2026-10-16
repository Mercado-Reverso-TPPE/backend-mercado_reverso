import hashlib
import json
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import GeocodificacaoCache, LimiteGeocodificador


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
    cache = GeocodificacaoCache.objects.filter(chave=chave).first()
    if cache:
        return cache.ponto, cache.cep, cache.cidade, cache.uf

    erro = None
    resultado = None
    with transaction.atomic():
        limite, _ = LimiteGeocodificador.objects.get_or_create(nome="nominatim")
        limite = LimiteGeocodificador.objects.select_for_update().get(nome=limite.nome)
        cache = GeocodificacaoCache.objects.filter(chave=chave).first()
        if cache:
            return cache.ponto, cache.cep, cache.cidade, cache.uf

        agora = timezone.now()
        if limite.ultima_consulta_em:
            intervalo = (agora - limite.ultima_consulta_em).total_seconds()
            if intervalo < 1:
                time.sleep(1 - intervalo)
        limite.ultima_consulta_em = timezone.now()
        limite.save(update_fields=["ultima_consulta_em"])

        # O lock global serializa chamadas e respeita o limite do serviço público.
        try:
            resultado = _buscar_no_nominatim(cep=cep, cidade=cidade, uf=uf)
        except ValidationError as exc:
            erro = exc
        except (KeyError, TypeError, ValueError) as exc:
            erro = ValidationError("O serviço de localização retornou uma resposta inválida.")
            erro.__cause__ = exc
        if resultado:
            ponto, cep, cidade, uf = resultado
            GeocodificacaoCache.objects.create(chave=chave, ponto=ponto, cep=cep, cidade=cidade, uf=uf)

    if erro:
        raise erro
    return ponto, cep, cidade, uf

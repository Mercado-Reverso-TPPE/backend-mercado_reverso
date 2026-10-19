import hashlib
from datetime import timedelta
import logging
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.cache import cache
from django.core import signing
from django.db import transaction
from django.utils.encoding import force_str
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes

from .models import Usuario

logger = logging.getLogger(__name__)


def _hash_email(email):
    email_normalizado = email.strip().casefold()
    return hashlib.sha256(email_normalizado.encode("utf-8")).hexdigest()


def acesso_bloqueado(email):
    chave = f"login:bloqueado:{_hash_email(email)}"
    bloqueado_ate = cache.get(chave)
    if bloqueado_ate is None:
        return False
    if bloqueado_ate > timezone.now():
        return True
    cache.delete(chave)
    cache.delete(f"login:falhas:{_hash_email(email)}")
    return False


def registrar_falha_login(email):
    hash_email = _hash_email(email)
    chave_falhas = f"login:falhas:{hash_email}"
    chave_bloqueio = f"login:bloqueado:{hash_email}"
    if acesso_bloqueado(email):
        return
    cache.add(chave_falhas, 0, timeout=None)
    try:
        falhas = cache.incr(chave_falhas)
    except ValueError:
        cache.set(chave_falhas, 1, timeout=None)
        falhas = 1
    if falhas >= settings.LOGIN_MAX_TENTATIVAS:
        prazo = timedelta(minutes=settings.LOGIN_BLOQUEIO_MINUTOS)
        cache.set(chave_bloqueio, timezone.now() + prazo, timeout=int(prazo.total_seconds()))
        cache.delete(chave_falhas)


def limpar_falhas_login(email):
    hash_email = _hash_email(email)
    cache.delete(f"login:falhas:{hash_email}")
    cache.delete(f"login:bloqueado:{hash_email}")


def solicitar_redefinicao_senha(email):
    usuario = Usuario.objects.filter(email__iexact=email.strip()).first()
    if usuario is None:
        return

    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    partes_url = urlsplit(settings.PASSWORD_RESET_URL)
    query = dict(parse_qsl(partes_url.query))
    query.update({"uid": uid, "token": token})
    link = urlunsplit(partes_url._replace(query=urlencode(query)))
    mensagem = f"Use o link abaixo para cadastrar uma nova senha. Ele expira em {settings.PASSWORD_RESET_TIMEOUT // 60} minutos e pode ser usado uma vez:\n\n{link}"

    try:
        send_mail("Redefinição de senha — Quero.", mensagem, settings.DEFAULT_FROM_EMAIL, [usuario.email])
    except Exception:
        # A resposta HTTP permanece genérica para não revelar se a conta existe.
        logger.exception("Não foi possível enviar o e-mail de redefinição de senha.")


@transaction.atomic
def confirmar_redefinicao_senha(*, uid, token, nova_senha):
    try:
        id_usuario = force_str(urlsafe_base64_decode(uid))
        usuario = Usuario.objects.get(pk=id_usuario)
    except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist) as exc:
        raise ValidationError("O link de redefinição é inválido ou expirou.") from exc

    if not default_token_generator.check_token(usuario, token):
        raise ValidationError("O link de redefinição é inválido ou expirou.")

    password_validation.validate_password(nova_senha, user=usuario)
    usuario.set_password(nova_senha)
    usuario.save(update_fields=["password"])


@transaction.atomic
def atualizar_perfil(*, usuario, dados):
    dados = dados.copy()
    localizacao = dados.pop("localizacao", None)
    ponto = localizacao.pop("_ponto", None) if localizacao else None
    precisa_geocodificar = localizacao.pop("_geocodificar", False) if localizacao else False
    localizacao_mudou = False

    if localizacao is not None:
        alterou_endereco = any(
            valor != getattr(usuario, campo)
            for campo, valor in localizacao.items()
            if campo in ("cep", "cidade", "uf")
        )
        precisa_geocodificar = precisa_geocodificar or (
            ponto is None
            and alterou_endereco
            and bool(localizacao.get("cep", usuario.cep) or localizacao.get("cidade", usuario.cidade))
        )
        if precisa_geocodificar:
            from .geocoding import localizar

            ponto, cep, cidade, uf = localizar(
                cep=localizacao.get("cep", usuario.cep),
                cidade=localizacao.get("cidade", usuario.cidade),
                uf=localizacao.get("uf", usuario.uf),
            )
            localizacao.update({"cep": cep, "cidade": cidade, "uf": uf})

        localizacao_mudou = (
            (ponto is not None and ponto != usuario.ponto)
            or any(
                valor != getattr(usuario, campo)
                for campo, valor in localizacao.items()
                if campo in ("cep", "cidade", "uf")
            )
        )

    for campo, valor in dados.items():
        setattr(usuario, campo, valor)
    usuario.save()

    if localizacao is not None and localizacao_mudou:
        for campo in ("cep", "cidade", "uf"):
            if campo in localizacao:
                setattr(usuario, campo, localizacao[campo])
        if ponto is not None:
            usuario.ponto = ponto
        usuario.localizacao_atualizada_em = timezone.now()
        usuario.save(
            update_fields=["cep", "cidade", "uf", "ponto", "localizacao_atualizada_em"]
        )

        from quero.anuncios.models import Anuncio

        anuncios_abertos = Anuncio.objects.filter(
            comprador=usuario,
            status__in=(Anuncio.Status.ATIVO, Anuncio.Status.PAUSADO),
        )
        for anuncio in anuncios_abertos.iterator():
            anuncio.save(update_fields=["atualizado_em"])
    return usuario


@transaction.atomic
def solicitar_alteracao_email(*, usuario, novo_email):
    novo_email = novo_email.strip().lower()
    if Usuario.objects.filter(email__iexact=novo_email).exclude(pk=usuario.pk).exists():
        raise ValidationError("Este e-mail já está sendo usado por outra conta.")

    token = signing.dumps(
        {"usuario_id": str(usuario.pk), "email_atual": usuario.email, "novo_email": novo_email},
        salt="quero.alteracao-email",
    )
    partes_url = urlsplit(settings.EMAIL_CHANGE_URL)
    query = dict(parse_qsl(partes_url.query))
    query["token"] = token
    link = urlunsplit(partes_url._replace(query=urlencode(query)))
    try:
        enviados = send_mail(
            "Confirme seu novo e-mail — Quero.",
            f"Confirme a troca de e-mail pelo link abaixo. Ele expira em {settings.EMAIL_CHANGE_TIMEOUT // 3600} horas:\n\n{link}",
            settings.DEFAULT_FROM_EMAIL,
            [novo_email],
        )
    except Exception as exc:
        logger.exception("Não foi possível enviar a confirmação de alteração de e-mail.")
        raise ValidationError("Não foi possível enviar o e-mail de confirmação.") from exc
    if not enviados:
        raise ValidationError("Não foi possível enviar o e-mail de confirmação.")
    return token


@transaction.atomic
def confirmar_alteracao_email(*, token):
    try:
        dados = signing.loads(
            token,
            salt="quero.alteracao-email",
            max_age=settings.EMAIL_CHANGE_TIMEOUT,
        )
        usuario = Usuario.objects.select_for_update().get(pk=dados["usuario_id"])
        novo_email = dados["novo_email"]
        email_atual = dados["email_atual"]
    except (signing.BadSignature, signing.SignatureExpired, KeyError, TypeError, ValueError, Usuario.DoesNotExist) as exc:
        raise ValidationError("O link de confirmação é inválido ou expirou.") from exc

    if usuario.email != email_atual:
        raise ValidationError("O link de confirmação é inválido ou expirou.")
    if Usuario.objects.filter(email__iexact=novo_email).exclude(pk=usuario.pk).exists():
        raise ValidationError("Este e-mail já está sendo usado por outra conta.")

    usuario.email = novo_email
    usuario.save(update_fields=["email"])
    return usuario

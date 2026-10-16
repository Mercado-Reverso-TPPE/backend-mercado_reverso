import hashlib
from datetime import timedelta
import logging
import secrets
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_str
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes

from .models import AlteracaoEmailPendente, Localizacao, TentativaLogin, Usuario

logger = logging.getLogger(__name__)


def _hash_email(email):
    email_normalizado = email.strip().casefold()
    return hashlib.sha256(email_normalizado.encode("utf-8")).hexdigest()


def acesso_bloqueado(email):
    tentativa = TentativaLogin.objects.filter(email_hash=_hash_email(email)).first()
    return tentativa is not None and tentativa.esta_bloqueada


@transaction.atomic
def registrar_falha_login(email):
    chave = _hash_email(email)
    tentativa, _ = TentativaLogin.objects.get_or_create(email_hash=chave)
    tentativa = TentativaLogin.objects.select_for_update().get(email_hash=chave)
    agora = timezone.now()

    if tentativa.bloqueado_ate and tentativa.bloqueado_ate <= agora:
        tentativa.falhas = 0
        tentativa.bloqueado_ate = None

    tentativa.falhas += 1
    if tentativa.falhas >= settings.LOGIN_MAX_TENTATIVAS:
        tentativa.bloqueado_ate = agora + timedelta(minutes=settings.LOGIN_BLOQUEIO_MINUTOS)
    tentativa.save(update_fields=["falhas", "bloqueado_ate", "atualizado_em"])


@transaction.atomic
def limpar_falhas_login(email):
    TentativaLogin.objects.filter(email_hash=_hash_email(email)).delete()


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

    if precisa_geocodificar:
        from .geocoding import localizar

        try:
            ponto, cep, cidade, uf = localizar(
                cep=localizacao.get("cep", getattr(getattr(usuario, "localizacao", None), "cep", "")),
                cidade=localizacao.get("cidade", getattr(getattr(usuario, "localizacao", None), "cidade", "")),
                uf=localizacao.get("uf", getattr(getattr(usuario, "localizacao", None), "uf", "")),
            )
        except ValidationError:
            raise
        localizacao.update({"cep": cep, "cidade": cidade, "uf": uf})

    for campo, valor in dados.items():
        setattr(usuario, campo, valor)
    usuario.save()

    if localizacao is not None and (localizacao or ponto is not None):
        localizacao_atual, criada = Localizacao.objects.get_or_create(
            usuario=usuario,
            defaults={**localizacao, "ponto": ponto},
        )
        localizacao_mudou = criada or localizacao_atual.ponto != ponto or any(
            getattr(localizacao_atual, campo) != valor for campo, valor in localizacao.items()
        )
        if not criada:
            for campo, valor in localizacao.items():
                setattr(localizacao_atual, campo, valor)
            localizacao_atual.ponto = ponto
            localizacao_atual.save()

        if localizacao_mudou:
            from quero.anuncios.models import Anuncio

            anuncios_abertos = Anuncio.objects.filter(
                comprador=usuario,
                status__in=(Anuncio.Status.ATIVO, Anuncio.Status.PAUSADO),
            )
            for anuncio in anuncios_abertos.iterator():
                anuncio.ponto = ponto
                anuncio.cidade = localizacao_atual.cidade
                anuncio.uf = localizacao_atual.uf
                anuncio.save(update_fields=["ponto", "cidade", "uf", "atualizado_em"])
    return usuario


@transaction.atomic
def solicitar_alteracao_email(*, usuario, novo_email):
    novo_email = novo_email.strip().lower()
    if Usuario.objects.filter(email__iexact=novo_email).exclude(pk=usuario.pk).exists():
        raise ValidationError("Este e-mail já está sendo usado por outra conta.")

    token = secrets.token_urlsafe(32)
    alteracao, _ = AlteracaoEmailPendente.objects.update_or_create(
        usuario=usuario,
        defaults={
            "novo_email": novo_email,
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "expira_em": timezone.now() + timedelta(seconds=settings.EMAIL_CHANGE_TIMEOUT),
        },
    )
    partes_url = urlsplit(settings.EMAIL_CHANGE_URL)
    query = dict(parse_qsl(partes_url.query))
    query["token"] = token
    link = urlunsplit(partes_url._replace(query=urlencode(query)))
    try:
        enviados = send_mail(
            "Confirme seu novo e-mail — Quero.",
            f"Confirme a troca de e-mail pelo link abaixo. Ele expira em 24 horas:\n\n{link}",
            settings.DEFAULT_FROM_EMAIL,
            [novo_email],
        )
    except Exception as exc:
        logger.exception("Não foi possível enviar a confirmação de alteração de e-mail.")
        raise ValidationError("Não foi possível enviar o e-mail de confirmação.") from exc
    if not enviados:
        raise ValidationError("Não foi possível enviar o e-mail de confirmação.")
    return alteracao


@transaction.atomic
def confirmar_alteracao_email(*, token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        alteracao = AlteracaoEmailPendente.objects.select_for_update().select_related("usuario").get(token_hash=token_hash)
    except AlteracaoEmailPendente.DoesNotExist as exc:
        raise ValidationError("O link de confirmação é inválido ou expirou.") from exc

    if alteracao.expira_em <= timezone.now():
        alteracao.delete()
        raise ValidationError("O link de confirmação é inválido ou expirou.")
    if Usuario.objects.filter(email__iexact=alteracao.novo_email).exclude(pk=alteracao.usuario_id).exists():
        raise ValidationError("Este e-mail já está sendo usado por outra conta.")

    usuario = alteracao.usuario
    usuario.email = alteracao.novo_email
    usuario.save(update_fields=["email"])
    alteracao.delete()
    return usuario

from django.contrib.auth import password_validation
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Usuario
from .services import acesso_bloqueado, atualizar_perfil, limpar_falhas_login, registrar_falha_login
from .geocoding import localizar as geocodificar


class LoginSerializer(TokenObtainPairSerializer):
    default_error_messages = {"no_active_account": "E-mail ou senha inválidos."}

    def validate(self, attrs):
        email = attrs.get(self.username_field, "")
        if acesso_bloqueado(email):
            raise AuthenticationFailed("E-mail ou senha inválidos.")
        try:
            dados = super().validate(attrs)
        except AuthenticationFailed as exc:
            registrar_falha_login(email)
            raise AuthenticationFailed("E-mail ou senha inválidos.") from exc
        limpar_falhas_login(email)
        return dados

class LocalizacaoSerializer(serializers.Serializer):
    cep = serializers.CharField(required=False, allow_blank=True, max_length=9)
    cidade = serializers.CharField(required=False, allow_blank=True, max_length=120)
    uf = serializers.CharField(required=False, allow_blank=True, max_length=2)
    longitude = serializers.FloatField(write_only=True, required=False)
    latitude = serializers.FloatField(write_only=True, required=False)

    def to_representation(self, instance):
        if instance.ponto is None:
            return None
        return {
            "cep": instance.cep,
            "cidade": instance.cidade,
            "uf": instance.uf,
            "longitude": instance.ponto.x,
            "latitude": instance.ponto.y,
        }

    def validate(self, attrs):
        lon = attrs.pop("longitude", None)
        lat = attrs.pop("latitude", None)
        if (lon is None) != (lat is None):
            raise serializers.ValidationError("Informe latitude e longitude em conjunto.")
        if lon is not None and not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise serializers.ValidationError("Coordenadas inválidas.")
        attrs["localizacao"] = {
            **attrs,
            "_ponto": Point(lon, lat, srid=4326) if lon is not None else None,
            "_geocodificar": lon is None and bool(attrs.get("cep") or attrs.get("cidade")),
        }
        return attrs

class CadastroSerializer(serializers.ModelSerializer):
    senha = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})
    longitude = serializers.FloatField(write_only=True, required=False)
    latitude = serializers.FloatField(write_only=True, required=False)
    cep = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=9)
    cidade = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=120)
    uf = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=2)

    class Meta:
        model = Usuario
        fields = ("id", "nome", "email", "senha", "telefone", "longitude", "latitude", "cep", "cidade", "uf")
        read_only_fields = ("id",)

    def validate_senha(self, value):
        password_validation.validate_password(value)
        return value

    def validate(self, attrs):
        lon, lat = attrs.get("longitude"), attrs.get("latitude")
        if (lon is None) != (lat is None):
            raise serializers.ValidationError("Informe latitude e longitude em conjunto.")
        if lon is not None and not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise serializers.ValidationError("Coordenadas inválidas.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        loc = {key: validated_data.pop(key) for key in ("longitude", "latitude", "cep", "cidade", "uf") if key in validated_data}
        password = validated_data.pop("senha")
        if "longitude" not in loc and (loc.get("cep") or loc.get("cidade")):
            try:
                ponto, cep, cidade, uf = geocodificar(cep=loc.get("cep", ""), cidade=loc.get("cidade", ""), uf=loc.get("uf", ""))
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages) from exc
            loc.update({"longitude": ponto.x, "latitude": ponto.y, "cep": cep, "cidade": cidade, "uf": uf})
        user = Usuario.objects.create_user(password=password, **validated_data)
        if "longitude" in loc and "latitude" in loc:
            user.ponto = Point(loc["longitude"], loc["latitude"], srid=4326)
            user.cep = loc.get("cep", "")
            user.cidade = loc.get("cidade", "")
            user.uf = loc.get("uf", "").upper()
            user.localizacao_atualizada_em = timezone.now()
            user.save(update_fields=["ponto", "cep", "cidade", "uf", "localizacao_atualizada_em"])
        return user

class PerfilSerializer(serializers.ModelSerializer):
    localizacao = LocalizacaoSerializer(required=False, source="*")

    class Meta:
        model = Usuario
        fields = ("id", "nome", "email", "telefone", "foto", "reputacao", "localizacao")
        read_only_fields = ("id", "email", "reputacao")

    @transaction.atomic
    def update(self, instance, validated_data):
        try:
            return atualizar_perfil(usuario=instance, dados=validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class SolicitarRedefinicaoSenhaSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ConfirmarRedefinicaoSenhaSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    nova_senha = serializers.CharField(write_only=True, min_length=10, style={"input_type": "password"})


class SolicitarAlteracaoEmailSerializer(serializers.Serializer):
    novo_email = serializers.EmailField()


class ConfirmarAlteracaoEmailSerializer(serializers.Serializer):
    token = serializers.CharField()

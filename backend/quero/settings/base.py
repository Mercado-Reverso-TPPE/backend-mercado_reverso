import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.environ.get("SECRET_KEY", "unsafe-local-development-key")
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "quero.core",
    "quero.contas",
    "quero.anuncios",
    "quero.ofertas",
    "quero.catalogo",
    "quero.negociacao",
    "quero.descoberta",
    "quero.notificacoes",
    "quero.reputacao",
    "quero.moderacao",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "quero.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "quero.wsgi.application"
ASGI_APPLICATION = "quero.asgi.application"
DATABASES = {
    "default": dj_database_url.config(
        default="postgis://quero:quero@db:5432/quero", conn_max_age=600, engine="django.contrib.gis.db.backends.postgis"
    )
}
CACHE_REDIS_URL = os.getenv("REDIS_URL", "").strip()
if CACHE_REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "quero-default-cache",
        }
    }
AUTH_USER_MODEL = "contas.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/hour", "user": "1000/day", "login": "5/minute"},
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
]
RAIO_PADRAO_KM = int(os.getenv("RAIO_PADRAO_KM", "20"))
RAIO_MAXIMO_KM = int(os.getenv("RAIO_MAXIMO_KM", "200"))
PESOS_RECOMENDACAO = {
    "categoria": int(os.getenv("PESO_RECOMENDACAO_CATEGORIA", "40")),
    "palavras_chave": int(os.getenv("PESO_RECOMENDACAO_PALAVRAS_CHAVE", "25")),
    "preco": int(os.getenv("PESO_RECOMENDACAO_PRECO", "20")),
    "distancia": int(os.getenv("PESO_RECOMENDACAO_DISTANCIA", "15")),
}
RECOMENDACOES_MAXIMO_TENTATIVAS = int(os.getenv("RECOMENDACOES_MAXIMO_TENTATIVAS", "5"))
NEGOCIACAO_PRAZO_CONFIRMACAO_HORAS = int(os.getenv("NEGOCIACAO_PRAZO_CONFIRMACAO_HORAS", "72"))
LOGIN_MAX_TENTATIVAS = int(os.getenv("LOGIN_MAX_TENTATIVAS", "5"))
LOGIN_BLOQUEIO_MINUTOS = int(os.getenv("LOGIN_BLOQUEIO_MINUTOS", "15"))
GEOCODER_URL = os.getenv("GEOCODER_URL", "https://nominatim.openstreetmap.org")
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "Quero/1.0 (geocodificacao de cadastro)")
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))
PASSWORD_RESET_URL = os.getenv("PASSWORD_RESET_URL", "http://localhost:3000/redefinir-senha")
EMAIL_CHANGE_TIMEOUT = int(os.getenv("EMAIL_CHANGE_TIMEOUT", "86400"))
EMAIL_CHANGE_URL = os.getenv("EMAIL_CHANGE_URL", "http://localhost:3000/confirmar-email")
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Quero. <nao-responda@quero.local>")
MEDIA_URL = os.getenv("MEDIA_URL", "media/")
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT") or BASE_DIR / "media")
PRODUTO_FOTOS_MAXIMO = int(os.getenv("PRODUTO_FOTOS_MAXIMO", "6"))
PRODUTO_FOTO_TAMANHO_MAXIMO_MB = int(os.getenv("PRODUTO_FOTO_TAMANHO_MAXIMO_MB", "5"))
PRODUTO_FOTO_FORMATOS = ("JPEG", "PNG", "WEBP")
CONTRAPROPOSTA_LIMITE_RODADAS = int(os.getenv("CONTRAPROPOSTA_LIMITE_RODADAS", "5"))
CONTRAPROPOSTA_PRAZO_HORAS = int(os.getenv("CONTRAPROPOSTA_PRAZO_HORAS", "48"))

import os

from .base import *

DEBUG = True
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# Permite navegar pela API no navegador com o login do /admin/ ou de /api-auth/login/; produção aceita apenas JWT.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        *REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
        "rest_framework.authentication.SessionAuthentication",
    ],
}

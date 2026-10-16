from .base import *  # noqa: F403
import os

DEBUG = True
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

"""
Django settings for Oficina AI.
"""

import sys
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

environ.Env.read_env(BASE_DIR / ".env")

# Fonte de verdade: arquivo VERSION (manter alinhado com pyproject.toml e CHANGELOG).
try:
    APP_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
except OSError:
    APP_VERSION = "0.0.0"

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://127.0.0.1:8000")

# Em produção (HTTPS atrás do proxy), deriva origens CSRF a partir dos hosts
# se CSRF_TRUSTED_ORIGINS não foi preenchido — evita 403 no login (mobile/desktop).
_csrf_origins = {o.rstrip("/") for o in CSRF_TRUSTED_ORIGINS if o}
for host in ALLOWED_HOSTS:
    host = (host or "").strip()
    if not host or host == "*":
        continue
    if host in ("localhost", "127.0.0.1"):
        _csrf_origins.update({f"http://{host}", f"http://{host}:8000"})
    else:
        _csrf_origins.add(f"https://{host}")
_public = PUBLIC_BASE_URL.rstrip("/")
if _public.startswith(("http://", "https://")):
    _csrf_origins.add(_public)
CSRF_TRUSTED_ORIGINS = sorted(_csrf_origins)

# Proxy reverso (EasyPanel / Traefik / Caddy): HTTPS e host corretos
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SAMESITE = "Lax"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "django_htmx",
    # Local
    "apps.accounts",
    "apps.core",
    "apps.orcamentos",
    "apps.ordens",
    "apps.financeiro",
    "apps.agentes",
    "apps.portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.oficina_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}
# Reusa conexão no processo (evita ~2s de TLS a cada request no Neon).
# Em serverless (Vercel etc.) use CONN_MAX_AGE=0 no .env.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["OPTIONS"] = {
    **DATABASES["default"].get("OPTIONS", {}),
    "connect_timeout": 10,
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.CaseInsensitiveModelBackend",
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media: Cloudflare R2 / S3-compatible quando bucket estiver definido; senão filesystem local
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="auto")
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
AWS_S3_ENDPOINT_URL = env(
    "AWS_S3_ENDPOINT_URL", default=""
)  # https://<ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_S3_CUSTOM_DOMAIN = env(
    "AWS_S3_CUSTOM_DOMAIN", default=""
)  # ex.: media.seudominio.com ou pub-xxx.r2.dev
# Aceita valor colado com https:// do painel R2
if AWS_S3_CUSTOM_DOMAIN:
    AWS_S3_CUSTOM_DOMAIN = (
        AWS_S3_CUSTOM_DOMAIN.removeprefix("https://").removeprefix("http://").rstrip("/")
    )
# Com domínio público R2, use False; com bucket privado, True (URLs assinadas)
AWS_QUERYSTRING_AUTH = env.bool(
    "AWS_QUERYSTRING_AUTH",
    default=not bool(env("AWS_S3_CUSTOM_DOMAIN", default="")),
)
AWS_DEFAULT_ACL = None
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
AWS_S3_FILE_OVERWRITE = False
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")

USE_S3 = bool(AWS_STORAGE_BUCKET_NAME)

if USE_S3:
    s3_options = {
        "bucket_name": AWS_STORAGE_BUCKET_NAME,
        "region_name": AWS_S3_REGION_NAME,
        "access_key": AWS_ACCESS_KEY_ID or None,
        "secret_key": AWS_SECRET_ACCESS_KEY or None,
        "default_acl": AWS_DEFAULT_ACL,
        "file_overwrite": AWS_S3_FILE_OVERWRITE,
        "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        "signature_version": AWS_S3_SIGNATURE_VERSION,
        "addressing_style": AWS_S3_ADDRESSING_STYLE,
        "querystring_auth": AWS_QUERYSTRING_AUTH,
    }
    if AWS_S3_ENDPOINT_URL:
        s3_options["endpoint_url"] = AWS_S3_ENDPOINT_URL
    if AWS_S3_CUSTOM_DOMAIN:
        s3_options["custom_domain"] = AWS_S3_CUSTOM_DOMAIN
        s3_options["querystring_auth"] = AWS_QUERYSTRING_AUTH

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": s3_options,
        },
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage.StaticFilesStorage"
                if DEBUG
                else "whitenoise.storage.CompressedManifestStaticFilesStorage"
            ),
        },
    }
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    elif AWS_S3_ENDPOINT_URL:
        # Fallback; com querystring_auth o storage.url() assina a URL
        MEDIA_URL = f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{AWS_STORAGE_BUCKET_NAME}/"
    else:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage.StaticFilesStorage"
                if DEBUG
                else "whitenoise.storage.CompressedManifestStaticFilesStorage"
            ),
        },
    }
    MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

# Base FIPE local (cascata marca → modelo → ano no cadastro de veículo)
FIPE_DB_PATH = env("FIPE_DB_PATH", default=str(BASE_DIR / "data" / "fipe.db"))

# Limite por upload (fotos do orçamento / OS)
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024  # 15 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
# Normalização de fotos: jpg/png/webp → quadrado 1280 → WebP (fallback JPEG) ≤ 500 KB
MAX_FOTO_UPLOAD_BYTES = 8 * 1024 * 1024
FOTO_LADO_PX = 1280
MAX_FOTO_SAIDA_BYTES = 500 * 1024
FOTO_QUALIDADE = 80

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# LLM / Agents
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4.1-mini")
OPENAI_TRANSCRIPTION_MODEL = env("OPENAI_TRANSCRIPTION_MODEL", default="whisper-1")
LLM_ENABLED = bool(OPENAI_API_KEY)

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_BEAT_SCHEDULE = {
    "resumo-diario-dono": {
        "task": "agentes.enviar_resumo_diario",
        "schedule": crontab(hour=7, minute=0),
    },
}

# E-mail (resumo diário; console em DEBUG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="oficina-ai@localhost")
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)

# WhatsApp Cloud API (Meta)
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", default="oficina-ai-verify")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_DEFAULT_OFICINA_ID = env("WHATSAPP_DEFAULT_OFICINA_ID", default="")
WHATSAPP_DRY_RUN = env.bool("WHATSAPP_DRY_RUN", default=True)
# App Secret do app Meta: valida X-Hub-Signature-256 no webhook. Obrigatório fora
# do dry-run — o webhook aciona tools que criam orçamento e mudam status de OS.
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", default="")

# Integração n8n + Evolution API. As credenciais da Evolution pertencem ao n8n;
# o Django recebe somente eventos normalizados e envia comandos assinados.
N8N_INBOUND_SECRET = env("N8N_INBOUND_SECRET", default="")
N8N_OUTBOUND_SECRET = env("N8N_OUTBOUND_SECRET", default="")
N8N_OUTBOUND_URL = env("N8N_OUTBOUND_URL", default="")
N8N_EVOLUTION_INSTANCE = env("N8N_EVOLUTION_INSTANCE", default="")
N8N_WEBHOOK_MAX_AGE_SECONDS = env.int("N8N_WEBHOOK_MAX_AGE_SECONDS", default=300)
N8N_MAX_MEDIA_BYTES = env.int("N8N_MAX_MEDIA_BYTES", default=8 * 1024 * 1024)

# Testes: SQLite em memória + storage local (sem tocar Neon/R2)
if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    AWS_STORAGE_BUCKET_NAME = ""
    USE_S3 = False
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    MEDIA_URL = "/media/"
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    CELERY_TASK_ALWAYS_EAGER = True
    LLM_ENABLED = False
    OPENAI_API_KEY = ""

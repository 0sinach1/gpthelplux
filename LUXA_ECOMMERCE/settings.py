"""Django settings for the LUXA e-commerce project.

The original repository was missing this module, which prevented every
management command from starting.  These settings provide safe local defaults
while allowing production values to be supplied from environment variables.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "django-insecure-local-development-key-change-me"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "testserver", ".luxa.ng", ".luxabrand.com"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=env("ALLOWED_HOSTS"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_hosts",
    "axes",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "MAIN.apps.MainConfig",
    "pages.apps.PagesConfig",
    "register.apps.RegisterConfig",
    "couriers.apps.CouriersConfig",
    "escrow.apps.EscrowConfig",
    "luxa_crave.apps.LuxaCraveConfig",
]

MIDDLEWARE = [
    "django_hosts.middleware.HostsRequestMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "django_hosts.middleware.HostsResponseMiddleware",
]

ROOT_URLCONF = "LUXA_ECOMMERCE.urls"
ROOT_HOSTCONF = "LUXA_ECOMMERCE.hosts"
DEFAULT_HOST = "default"
PARENT_HOST = env("PARENT_HOST", default="localhost:8000")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "MAIN.context_processors.cart_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "LUXA_ECOMMERCE.wsgi.application"
ASGI_APPLICATION = "LUXA_ECOMMERCE.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/index/"
LOGOUT_REDIRECT_URL = "/index/"

ACCOUNT_ADAPTER = "MAIN.adapters.MyAccountAdapter"
SOCIALACCOUNT_ADAPTER = "MAIN.adapters.MySocialAccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[LUXA] "
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@luxa.ng")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
COURIER_FEE = env.int("COURIER_FEE", default=500)

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

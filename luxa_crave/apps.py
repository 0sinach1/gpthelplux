from django.apps import AppConfig


class LuxaCraveConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "luxa_crave"

    def ready(self):
        import luxa_crave.signals  # noqa: F401

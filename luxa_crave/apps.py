from django.apps import AppConfig


class LuxaCraveConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'luxa_crave'

    def ready(self):
            # This is the "on switch" that connects your signals
            import luxa_crave.signals
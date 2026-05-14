from django.apps import AppConfig


class EscrowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'escrow'

    def ready(self):
        import escrow.signals  # This loads the signals
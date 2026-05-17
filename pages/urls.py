from django.urls import path

from . import views

urlpatterns = [
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("help/", views.help, name="help"),
    path("ordertrack/", views.ordertrack, name="ordertrack"),
    path("size/", views.size, name="size"),
    path("ship/", views.ship, name="ship"),
    path("faq/", views.faq, name="faq"),
    path("returns/", views.returns, name="returns"),
    path("vendoragreement/", views.vendag, name="vendag"),
]
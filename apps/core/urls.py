from django.urls import path

from apps.core.views import contact, home, rights


app_name = "core"


urlpatterns = [
    path("", home, name="home"),
    path("derechos/", rights, name="rights"),
    path("contacto/", contact, name="contact"),
]

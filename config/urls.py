from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("orcamentos/", include("apps.orcamentos.urls")),
    path("ordens/", include("apps.ordens.urls")),
    path("financeiro/", include("apps.financeiro.urls")),
    path("agentes/", include("apps.agentes.urls")),
    path("p/", include("apps.portal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

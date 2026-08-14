from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("busca/", views.busca, name="busca"),
    path("clientes/", views.cliente_list, name="clientes"),
    path("clientes/novo/", views.cliente_create, name="cliente_create"),
    path("veiculos/", views.veiculo_list, name="veiculos"),
    path("veiculos/novo/", views.veiculo_create, name="veiculo_create"),
    path("veiculos/<int:pk>/editar/", views.veiculo_edit, name="veiculo_edit"),
    path("veiculos/fipe/modelos/", views.fipe_modelos, name="fipe_modelos"),
    path("veiculos/fipe/anos/", views.fipe_anos, name="fipe_anos"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("catalogo/servicos/novo/", views.servico_create, name="servico_create"),
    path("catalogo/servicos/<int:pk>/editar/", views.servico_edit, name="servico_edit"),
    path("catalogo/pecas/novo/", views.peca_create, name="peca_create"),
    path("catalogo/pecas/<int:pk>/editar/", views.peca_edit, name="peca_edit"),
    path("fornecedores/", views.fornecedor_list, name="fornecedores"),
    path("fornecedores/novo/", views.fornecedor_create, name="fornecedor_create"),
    path("fornecedores/<int:pk>/editar/", views.fornecedor_edit, name="fornecedor_edit"),
    path("compras/", views.compra_list, name="compras"),
    path("compras/nova/", views.compra_create, name="compra_create"),
    path("importar/", views.importar_csv, name="importar_csv"),
    path("relatorios/", views.relatorios, name="relatorios"),
    path("comissoes/", views.comissoes, name="comissoes"),
    path("equipe/", views.equipe, name="equipe"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("manifest.webmanifest", views.pwa_manifest, name="pwa_manifest"),
    path("sw.js", views.pwa_service_worker, name="pwa_sw"),
]

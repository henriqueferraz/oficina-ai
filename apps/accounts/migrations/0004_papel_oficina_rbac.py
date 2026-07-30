# Generated manually for PapelOficina RBAC

import django.db.models.deletion
from django.db import migrations, models


def forwards_seed_and_map(apps, schema_editor):
    Oficina = apps.get_model("core", "Oficina")
    PapelOficina = apps.get_model("accounts", "PapelOficina")
    PerfilUsuario = apps.get_model("accounts", "PerfilUsuario")

    todas = [
        "ordens",
        "orcamentos",
        "clientes",
        "veiculos",
        "catalogo",
        "fornecedores",
        "compras",
        "financeiro",
        "relatorios",
        "importar",
        "agente",
        "equipe",
        "configuracoes",
        "painel_caixa",
        "painel_ordens_recentes",
        "painel_estoque",
        "recebe_comissao",
    ]
    defaults = {
        "dono": {
            "nome": "Administrador",
            "eh_administrador": True,
            "permissoes": list(todas),
        },
        "recepcao": {
            "nome": "Recepção",
            "eh_administrador": False,
            "permissoes": [
                "ordens",
                "orcamentos",
                "clientes",
                "veiculos",
                "catalogo",
                "fornecedores",
                "compras",
                "importar",
                "agente",
                "equipe",
                "painel_caixa",
                "painel_ordens_recentes",
                "painel_estoque",
            ],
        },
        "mecanico": {
            "nome": "Mecânico",
            "eh_administrador": False,
            "permissoes": ["ordens", "orcamentos", "equipe", "recebe_comissao"],
        },
        "financeiro": {
            "nome": "Financeiro",
            "eh_administrador": False,
            "permissoes": [
                "ordens",
                "orcamentos",
                "clientes",
                "veiculos",
                "catalogo",
                "fornecedores",
                "compras",
                "financeiro",
                "relatorios",
                "importar",
                "agente",
                "equipe",
                "painel_caixa",
                "painel_ordens_recentes",
                "painel_estoque",
            ],
        },
    }

    for oficina in Oficina.objects.all():
        por_slug = {}
        for slug, cfg in defaults.items():
            papel, _ = PapelOficina.objects.get_or_create(
                oficina_id=oficina.id,
                slug=slug,
                defaults={
                    "nome": cfg["nome"],
                    "eh_administrador": cfg["eh_administrador"],
                    "permissoes": list(cfg["permissoes"]),
                    "ativo": True,
                },
            )
            por_slug[slug] = papel

        for perfil in PerfilUsuario.objects.filter(oficina_id=oficina.id):
            slug_antigo = perfil.papel_antigo or "recepcao"
            if slug_antigo not in por_slug:
                slug_antigo = "recepcao"
            perfil.papel = por_slug[slug_antigo]
            perfil.save(update_fields=["papel"])


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_papel_administrador"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PapelOficina",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=50)),
                ("nome", models.CharField(max_length=80)),
                ("eh_administrador", models.BooleanField(default=False)),
                ("permissoes", models.JSONField(blank=True, default=list)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "oficina",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="papeis",
                        to="core.oficina",
                    ),
                ),
            ],
            options={
                "verbose_name": "Papel da oficina",
                "verbose_name_plural": "Papéis da oficina",
                "ordering": ["-eh_administrador", "nome"],
            },
        ),
        migrations.AddConstraint(
            model_name="papeloficina",
            constraint=models.UniqueConstraint(fields=("oficina", "slug"), name="uniq_papel_oficina_slug"),
        ),
        migrations.RenameField(
            model_name="perfilusuario",
            old_name="papel",
            new_name="papel_antigo",
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="papel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="perfis",
                to="accounts.papeloficina",
            ),
        ),
        migrations.RunPython(forwards_seed_and_map, backwards_noop),
        migrations.RemoveField(
            model_name="perfilusuario",
            name="papel_antigo",
        ),
    ]

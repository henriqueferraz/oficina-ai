"""Backfill token_publico em OS e orçamentos existentes."""

from django.db import migrations


def _gerar():
    from apps.core.tokens import gerar_token

    return gerar_token()


def backfill_tokens(apps, schema_editor):
    OrdemServico = apps.get_model("ordens", "OrdemServico")
    Orcamento = apps.get_model("orcamentos", "Orcamento")
    for model in (OrdemServico, Orcamento):
        for obj in model.objects.filter(token_publico=""):
            obj.token_publico = _gerar()
            obj.save(update_fields=["token_publico"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ordens", "0002_ordemservico_estoque_baixado"),
        ("orcamentos", "0003_orcamento_token_publico"),
        ("core", "0003_semana5_6_diferenciacao"),
    ]

    operations = [
        migrations.RunPython(backfill_tokens, noop),
    ]

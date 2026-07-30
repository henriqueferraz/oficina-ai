from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_semana5_6_diferenciacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="oficina",
            name="bairro",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="oficina",
            name="cep",
            field=models.CharField(blank=True, max_length=9),
        ),
        migrations.AddField(
            model_name="oficina",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="oficinas/logos/%Y/%m/"),
        ),
    ]

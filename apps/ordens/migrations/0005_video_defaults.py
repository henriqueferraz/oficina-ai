from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ordens", "0004_ordem_video_e_limite_fotos"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ordemservico",
            name="video_titulo",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AlterField(
            model_name="ordemservico",
            name="video_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Link do vídeo (YouTube, Vimeo ou outro stream).",
            ),
        ),
        migrations.RunSQL(
            sql=[
                "UPDATE ordens_ordemservico SET video_titulo = '' WHERE video_titulo IS NULL;",
                "UPDATE ordens_ordemservico SET video_url = '' WHERE video_url IS NULL;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

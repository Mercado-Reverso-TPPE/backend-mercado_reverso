from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("anuncios", "0004_recomendacoes_async_queue"),
        ("descoberta", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="recomendacao",
            name="explicacao",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

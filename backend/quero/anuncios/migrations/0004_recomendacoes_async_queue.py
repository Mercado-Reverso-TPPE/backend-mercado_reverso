from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0003_raio_por_localizacao_de_referencia")]

    operations = [
        migrations.AddField(
            model_name="anuncio",
            name="recomendacoes_solicitadas_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="anuncio",
            name="recomendacoes_processando_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="anuncio",
            name="recomendacoes_calculadas_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="anuncio",
            name="recomendacoes_tentar_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="anuncio",
            name="recomendacoes_tentativas",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="anuncio",
            name="recomendacoes_ultimo_erro",
            field=models.TextField(blank=True),
        ),
    ]

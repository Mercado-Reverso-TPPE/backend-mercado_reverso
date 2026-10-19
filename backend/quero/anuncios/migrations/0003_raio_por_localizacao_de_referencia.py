from django.db import migrations, models
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):
    dependencies = [
        ("anuncios", "0002_categoria_e_cidade"),
        ("contas", "0003_normalizar_usuario_y_cache"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                UPDATE anuncios_anuncio AS anuncio
                SET alcance = ST_Buffer(usuario.ponto, anuncio.raio_m)
                FROM contas_usuario AS usuario
                WHERE anuncio.comprador_id = usuario.id
                  AND usuario.ponto IS NOT NULL
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RemoveIndex(model_name="anuncio", name="anuncio_ponto_gist"),
        migrations.RemoveField(model_name="anuncio", name="cidade"),
        migrations.RemoveField(model_name="anuncio", name="uf"),
        migrations.RemoveField(model_name="anuncio", name="ponto"),
    ]

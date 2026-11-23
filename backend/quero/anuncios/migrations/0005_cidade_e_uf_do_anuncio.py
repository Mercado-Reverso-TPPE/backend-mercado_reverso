from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def copiar_localizacao_do_comprador(apps, schema_editor):
    Anuncio = apps.get_model("anuncios", "Anuncio")
    Usuario = apps.get_model("contas", "Usuario")
    comprador = Usuario.objects.filter(pk=OuterRef("comprador_id"))
    Anuncio.objects.update(
        cidade=Subquery(comprador.values("cidade")[:1]),
        uf=Subquery(comprador.values("uf")[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("anuncios", "0004_recomendacoes_async_queue"),
        ("contas", "0004_alter_usuario_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="anuncio",
            name="cidade",
            field=models.CharField(blank=True, editable=False, max_length=120),
        ),
        migrations.AddField(
            model_name="anuncio",
            name="uf",
            field=models.CharField(blank=True, editable=False, max_length=2),
        ),
        migrations.AddIndex(
            model_name="anuncio",
            index=models.Index(fields=["status", "uf"], name="anuncio_status_uf"),
        ),
        migrations.RunPython(copiar_localizacao_do_comprador, migrations.RunPython.noop),
    ]

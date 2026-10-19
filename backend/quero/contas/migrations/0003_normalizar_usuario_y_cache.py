from django.contrib.gis.db import models as gis_models
from django.db import migrations, models


def copiar_localizaciones_a_usuario(apps, schema_editor):
    Usuario = apps.get_model("contas", "Usuario")
    Localizacao = apps.get_model("contas", "Localizacao")
    database = schema_editor.connection.alias
    for localizacao in Localizacao.objects.using(database).iterator():
        Usuario.objects.using(database).filter(pk=localizacao.usuario_id).update(
            ponto=localizacao.ponto,
            cep=localizacao.cep,
            cidade=localizacao.cidade,
            uf=localizacao.uf,
            localizacao_atualizada_em=localizacao.atualizada_em,
        )


class Migration(migrations.Migration):
    dependencies = [("contas", "0002_auth_geocoding_and_email")]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="ponto",
            field=gis_models.PointField(blank=True, null=True, geography=True, srid=4326),
        ),
        migrations.AddField(
            model_name="usuario",
            name="cep",
            field=models.CharField(blank=True, max_length=9),
        ),
        migrations.AddField(
            model_name="usuario",
            name="cidade",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="usuario",
            name="uf",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="usuario",
            name="localizacao_atualizada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(copiar_localizaciones_a_usuario, migrations.RunPython.noop),
        migrations.RemoveField(model_name="usuario", name="reputacao"),
        migrations.DeleteModel(name="Localizacao"),
        migrations.DeleteModel(name="TentativaLogin"),
        migrations.DeleteModel(name="GeocodificacaoCache"),
        migrations.DeleteModel(name="LimiteGeocodificador"),
        migrations.DeleteModel(name="AlteracaoEmailPendente"),
    ]

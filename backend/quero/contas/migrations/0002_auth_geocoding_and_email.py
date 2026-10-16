from django.conf import settings
from django.db import migrations, models
import django.contrib.gis.db.models.fields
import django.db.models.deletion


def criar_limite_nominatim(apps, schema_editor):
    LimiteGeocodificador = apps.get_model("contas", "LimiteGeocodificador")
    LimiteGeocodificador.objects.get_or_create(nome="nominatim")


class Migration(migrations.Migration):
    dependencies = [("contas", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="TentativaLogin",
            fields=[
                ("email_hash", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("falhas", models.PositiveSmallIntegerField(default=0)),
                ("bloqueado_ate", models.DateTimeField(blank=True, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="GeocodificacaoCache",
            fields=[
                ("chave", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("ponto", django.contrib.gis.db.models.fields.PointField(geography=True, srid=4326)),
                ("cep", models.CharField(blank=True, max_length=9)),
                ("cidade", models.CharField(blank=True, max_length=120)),
                ("uf", models.CharField(blank=True, max_length=2)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="LimiteGeocodificador",
            fields=[
                ("nome", models.CharField(max_length=40, primary_key=True, serialize=False)),
                ("ultima_consulta_em", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="AlteracaoEmailPendente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("novo_email", models.EmailField(max_length=254, unique=True)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expira_em", models.DateTimeField()),
                ("criada_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="alteracao_email_pendente", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(criar_limite_nominatim, migrations.RunPython.noop),
    ]

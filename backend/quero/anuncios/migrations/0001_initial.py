import uuid
from django.conf import settings
from django.contrib.postgres.indexes import GistIndex
from django.db import migrations, models
import django.contrib.gis.db.models.fields
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("core", "0001_enable_postgis"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="Anuncio", fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("titulo", models.CharField(max_length=160)), ("categoria", models.CharField(max_length=100)), ("descricao", models.TextField()),
        ("preco_min", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        ("preco_max", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        ("raio_m", models.PositiveIntegerField()), ("ponto", django.contrib.gis.db.models.fields.PointField(srid=4326, geography=True)),
        ("alcance", django.contrib.gis.db.models.fields.PolygonField(editable=False, null=True, srid=4326, geography=True)),
        ("status", models.CharField(choices=[("ativo", "Ativo"), ("pausado", "Pausado"), ("em_negociacao", "Em negociação"), ("encerrado", "Encerrado")], default="ativo", max_length=20)),
        ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
        ("comprador", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="anuncios", to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ("-criado_em",)}),
        migrations.AddIndex(model_name="anuncio", index=GistIndex(fields=["alcance"], name="anuncio_alcance_gist")),
        migrations.AddIndex(model_name="anuncio", index=GistIndex(fields=["ponto"], name="anuncio_ponto_gist")),
        migrations.AddIndex(model_name="anuncio", index=models.Index(fields=["status", "categoria"], name="anuncio_status_categoria")),
    ]

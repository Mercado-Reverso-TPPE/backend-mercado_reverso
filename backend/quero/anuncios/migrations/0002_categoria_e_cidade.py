from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


NOMES_CATEGORIA = (
    ("Eletrônicos", "eletronicos"),
    ("Veículos", "veiculos"),
    ("Informática", "informatica"),
    ("Games", "games"),
    ("Esportes", "esportes"),
    ("Casa & Jardim", "casa-jardim"),
    ("Instrumentos", "instrumentos"),
    ("Outros", "outros"),
)


def preencher_catalogo(apps, schema_editor):
    Categoria = apps.get_model("anuncios", "Categoria")
    Anuncio = apps.get_model("anuncios", "Anuncio")
    categorias = {}
    for nome, slug in NOMES_CATEGORIA:
        categorias[slug] = Categoria.objects.create(nome=nome, slug=slug)

    for anuncio in Anuncio.objects.all().iterator():
        slug = slugify(anuncio.categoria or "")
        categoria = categorias.get(slug, categorias["outros"])
        anuncio.categoria_nova_id = categoria.pk
        location = getattr(anuncio.comprador, "localizacao", None)
        if location:
            anuncio.cidade = location.cidade
            anuncio.uf = location.uf
        anuncio.save(update_fields=["categoria_nova", "cidade", "uf"])


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Categoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=80, unique=True)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("ativa", models.BooleanField(default=True)),
            ],
            options={"ordering": ("nome",), "verbose_name_plural": "categorias"},
        ),
        migrations.AddField(model_name="anuncio", name="cidade", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="anuncio", name="uf", field=models.CharField(blank=True, max_length=2)),
        migrations.AddField(
            model_name="anuncio",
            name="categoria_nova",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="anuncios", to="anuncios.categoria"),
        ),
        migrations.RunPython(preencher_catalogo, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name="anuncio", name="anuncio_status_categoria"),
        migrations.RemoveField(model_name="anuncio", name="categoria"),
        migrations.RenameField(model_name="anuncio", old_name="categoria_nova", new_name="categoria"),
        migrations.AlterField(
            model_name="anuncio",
            name="categoria",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="anuncios", to="anuncios.categoria"),
        ),
        migrations.AddIndex(model_name="anuncio", index=models.Index(fields=["status", "categoria"], name="anuncio_status_categoria")),
    ]

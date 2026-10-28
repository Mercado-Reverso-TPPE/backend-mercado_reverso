import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


def preencher_anuncio(apps, schema_editor):
    Negociacao = apps.get_model("negociacao", "Negociacao")
    for negociacao in Negociacao.objects.select_related("oferta").all().iterator():
        negociacao.anuncio_id = negociacao.oferta.anuncio_id
        negociacao.save(update_fields=["anuncio"])


class Migration(migrations.Migration):

    dependencies = [
        ("anuncios", "0003_raio_por_localizacao_de_referencia"),
        ("negociacao", "0001_initial"),
        ("ofertas", "0004_counteroffer_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="negociacao",
            name="anuncio",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="negociacoes",
                to="anuncios.anuncio",
            ),
        ),
        migrations.RunPython(preencher_anuncio, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="negociacao",
            name="anuncio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="negociacoes",
                to="anuncios.anuncio",
            ),
        ),
        migrations.AddConstraint(
            model_name="negociacao",
            constraint=models.UniqueConstraint(
                condition=Q(status="em_andamento"),
                fields=("anuncio",),
                name="uma_negociacao_ativa_por_anuncio",
            ),
        ),
    ]
